"""Shared GitHub PR fetching logic.

Used by both the CLI (pr_digest.py) and the SwiftBar menu bar plugin
(swiftbar_plugin.py). Holds auth, the search-API calls, error handling, and
result normalization in one place so the two front-ends stay in sync.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

API_ROOT = "https://api.github.com"
SEARCH_URL = f"{API_ROOT}/search/issues"
TIMEOUT = 30

# This file lives in the repo root; .env sits next to it.
REPO_DIR = Path(__file__).resolve().parent
ENV_PATH = REPO_DIR / ".env"

# The two searches that define "needs your attention".
QUERIES = {
    "Review requested": "is:open is:pr review-requested:@me",
    "Assigned to you": "is:open is:pr assignee:@me",
}


class DigestError(Exception):
    """A user-facing error with a clean message (no traceback needed)."""


def load_env() -> None:
    """Load GITHUB_TOKEN from the repo's .env (real env still wins).

    Uses an absolute path so it works no matter the caller's working
    directory — SwiftBar runs plugins from an arbitrary cwd.
    """
    load_dotenv(dotenv_path=ENV_PATH)


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise DigestError(
            "GITHUB_TOKEN is not set.\n"
            "  Set it in your environment or in a .env file (see .env.example).\n"
            "  The token needs read-only access to pull requests:\n"
            "    - fine-grained PAT: 'Pull requests: read'\n"
            "    - classic PAT:      'repo' scope"
        )
    return token


def search_prs(query: str, token: str) -> list[dict]:
    """Run one search query, following pagination, returning all items."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    items: list[dict] = []
    page = 1
    while True:
        url = f"{SEARCH_URL}?q={quote(query)}&per_page=100&page={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise DigestError(f"Network error talking to GitHub: {exc}") from exc

        _raise_for_api_errors(resp)

        payload = resp.json()
        batch = payload.get("items", [])
        items.extend(batch)

        # Search API caps total results at 1000; stop when we've drained the set.
        total = payload.get("total_count", 0)
        if len(batch) < 100 or len(items) >= min(total, 1000):
            break
        page += 1
    return items


def _raise_for_api_errors(resp: requests.Response) -> None:
    if resp.status_code == 200:
        return

    if resp.status_code == 401:
        raise DigestError(
            "Authentication failed (401). Your GITHUB_TOKEN is invalid or expired.\n"
            "  Generate a new token with read-only pull request access and update .env."
        )

    # Rate limiting shows up as 403 (or 429) with a depleted remaining count.
    remaining = resp.headers.get("X-RateLimit-Remaining")
    if resp.status_code in (403, 429) and remaining == "0":
        reset = resp.headers.get("X-RateLimit-Reset")
        when = ""
        if reset and reset.isdigit():
            reset_dt = datetime.fromtimestamp(int(reset), tz=timezone.utc).astimezone()
            when = f" Try again after {reset_dt:%Y-%m-%d %H:%M:%S %Z}."
        raise DigestError(f"GitHub rate limit exceeded.{when}")

    if resp.status_code == 403:
        raise DigestError(
            "Access forbidden (403). Your token may lack the required scope.\n"
            "  Needs read-only pull request access (fine-grained 'Pull requests: read'\n"
            "  or classic 'repo' scope)."
        )

    # Anything else: surface GitHub's own message if it gave one.
    try:
        message = resp.json().get("message", resp.text)
    except ValueError:
        message = resp.text
    raise DigestError(f"GitHub API error ({resp.status_code}): {message}")


def normalize(item: dict) -> dict:
    """Pull the fields we care about out of a search result item."""
    # repository_url looks like https://api.github.com/repos/<owner>/<repo>
    repo = item.get("repository_url", "").split("/repos/", 1)[-1] or "unknown/unknown"
    created = item.get("created_at")
    age_days = 0
    if created:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - created_dt).days
    return {
        "repo": repo,
        "number": item.get("number"),
        "title": (item.get("title") or "").strip(),
        "author": (item.get("user") or {}).get("login", "unknown"),
        "url": item.get("html_url", ""),
        "age_days": age_days,
        # Raw ISO string; used to detect "updated since you last looked".
        "updated_at": item.get("updated_at", ""),
    }


def collect_prs(token: str) -> list[dict]:
    """Run both searches and de-duplicate by PR URL."""
    by_url: dict[str, dict] = {}
    for query in QUERIES.values():
        for item in search_prs(query, token):
            pr = normalize(item)
            by_url.setdefault(pr["url"], pr)
    return list(by_url.values())
