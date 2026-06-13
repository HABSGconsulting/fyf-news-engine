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
    """Returns the blob SHA of an existing file, or None if it doesn't exist."""
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


def _put_file(repo: str, path: str, content: str, message: str, branch: str = "main") -> None:
    """Create or update a single file in the repo."""
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload: dict = {
        "message": message,
        "content": encoded,
        "branch": branch,
    }
    existing_sha = _get_file_sha(repo, path, branch)
    if existing_sha:
        payload["sha"] = existing_sha

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_headers(), method="PUT")
    with urllib.request.urlopen(req) as resp:
        resp.read()


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
        time.sleep(0.3)  # gentle rate limiting
        print(f"  ✓ published: {path}")
