"""publisher.py — commits all generated files to fyf-news-site in ONE atomic commit.

Uses the GitHub Git Data API (blob → tree → commit → ref update) so that an
entire pipeline run — whether it produces 1 file or 20 — always results in
exactly ONE commit and therefore ONE Cloudflare Pages deployment trigger.

Previous behaviour: individual PUT per file → N commits → N deployments queued.
"""
import os
import base64
import json
import time
import urllib.request
import urllib.error
from config.settings import NEWS_SITE_REPO


GITHUB_TOKEN = os.environ.get("NEWS_SITE_DEPLOY_KEY", "")
API_BASE     = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def _api(method: str, path: str, payload: dict | None = None, retries: int = 3) -> dict:
    """Generic GitHub API call with exponential backoff."""
    url = f"{API_BASE}{path}"
    for attempt in range(retries):
        try:
            body = json.dumps(payload).encode("utf-8") if payload else None
            req  = urllib.request.Request(url, data=body, headers=_headers(), method=method)
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  ⚠ Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  ⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"API call {method} {path} failed after {retries} retries")


def _create_blob(repo: str, content: str) -> str:
    """Upload file content as a Git blob. Returns blob SHA."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    result  = _api("POST", f"/repos/{repo}/git/blobs", {
        "content":  encoded,
        "encoding": "base64",
    })
    return result["sha"]


def publish_files(files: dict[str, str], run_label: str, branch: str = "main") -> None:
    """
    Push all files in a single atomic Git commit to fyf-news-site.

    Args:
        files:      {relative_path: file_content} for every file to publish.
        run_label:  Short label used in the commit message (e.g. '2026-06-15T12:00 IST').
        branch:     Target branch (default: main).

    One commit is always created, regardless of how many files are in the dict.
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("NEWS_SITE_DEPLOY_KEY secret is not set.")

    if not files:
        print("  ℹ publish_files: nothing to publish.")
        return

    repo = NEWS_SITE_REPO

    # ------------------------------------------------------------------ #
    # Step 1: Resolve current HEAD commit SHA and its tree SHA
    # ------------------------------------------------------------------ #
    ref_data        = _api("GET", f"/repos/{repo}/git/ref/heads/{branch}")
    head_commit_sha = ref_data["object"]["sha"]

    commit_data     = _api("GET", f"/repos/{repo}/git/commits/{head_commit_sha}")
    base_tree_sha   = commit_data["tree"]["sha"]

    # ------------------------------------------------------------------ #
    # Step 2: Create a Git blob for every file
    # ------------------------------------------------------------------ #
    print(f"  • Creating {len(files)} blob(s)...")
    tree_entries = []
    for path, content in files.items():
        blob_sha = _create_blob(repo, content)
        tree_entries.append({
            "path":  path,
            "mode":  "100644",   # regular file
            "type":  "blob",
            "sha":   blob_sha,
        })
        print(f"    blob ✓ {path}")

    # ------------------------------------------------------------------ #
    # Step 3: Create a new tree on top of the existing tree
    # ------------------------------------------------------------------ #
    new_tree = _api("POST", f"/repos/{repo}/git/trees", {
        "base_tree": base_tree_sha,
        "tree":      tree_entries,
    })
    new_tree_sha = new_tree["sha"]

    # ------------------------------------------------------------------ #
    # Step 4: Create one commit pointing to the new tree
    # ------------------------------------------------------------------ #
    file_count   = len(files)
    commit_msg   = (
        f"pipeline({run_label}): publish {file_count} file(s)\n\n"
        + "\n".join(f"  + {p}" for p in files)
    )
    new_commit   = _api("POST", f"/repos/{repo}/git/commits", {
        "message": commit_msg,
        "tree":    new_tree_sha,
        "parents": [head_commit_sha],
    })
    new_commit_sha = new_commit["sha"]

    # ------------------------------------------------------------------ #
    # Step 5: Fast-forward branch ref to the new commit
    # ------------------------------------------------------------------ #
    _api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", {
        "sha":   new_commit_sha,
        "force": False,
    })

    print(f"  ✓ Published {file_count} file(s) in 1 commit: {new_commit_sha[:7]}")
