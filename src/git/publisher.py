"""publisher.py — commits and pushes generated files to fyf-news-site via GitHub API."""
import os
import base64
import json
import time
import urllib.request
import urllib.error
from config.settings import NEWS_SITE_REPO


GITHUB_TOKEN = os.environ.get("NEWS_SITE_DEPLOY_KEY", "")
API_BASE = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def _get_file_sha(repo: str, path: str, branch: str = "main") -> str | None:
    url = f"{API_BASE}/repos/{repo}/contents/{path}?ref={branch}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _put_file(repo: str, path: str, content: str, message: str, branch: str = "main", retries: int = 3) -> None:
    """Create or update a single file with exponential backoff on failure."""
    for attempt in range(retries):
        try:
            url = f"{API_BASE}/repos/{repo}/contents/{path}"
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            payload: dict = {"message": message, "content": encoded, "branch": branch}
            existing_sha = _get_file_sha(repo, path, branch)
            if existing_sha:
                payload["sha"] = existing_sha
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=_headers(), method="PUT")
            with urllib.request.urlopen(req) as resp:
                resp.read()
            return
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
    raise RuntimeError(f"Failed to publish {path} after {retries} retries")


def publish_files(files: dict[str, str], run_label: str, branch: str = "main") -> None:
    """
    Push a dict of {relative_path: content} to fyf-news-site.
    Uses individual PUT calls (no git CLI needed).
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("NEWS_SITE_DEPLOY_KEY secret is not set.")

    for path, content in files.items():
        message = f"pipeline: {run_label} — {path.split('/')[-1]}"
        _put_file(NEWS_SITE_REPO, path, content, message, branch)
        time.sleep(0.3)
        print(f"  ✓ published: {path}")
