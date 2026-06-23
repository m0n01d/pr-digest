#!/usr/bin/env python3
"""Daily digest of open GitHub PRs that need your attention.

Fetches, via the GitHub REST search API:
  * open PRs where you are a requested reviewer (review-requested:@me)
  * open PRs assigned to you            (assignee:@me)

De-duplicates the two lists, prints a terminal digest grouped by repo, and
writes the same digest to a timestamped file under ./digests/.

Auth: reads a GitHub token from the GITHUB_TOKEN environment variable
(loaded from a .env file via python-dotenv if present). Never hardcoded.

The fetch/auth logic lives in gh_prs.py so this CLI and the SwiftBar menu bar
plugin share one implementation.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from gh_prs import DigestError, collect_prs, get_token, load_env

DIGEST_DIR = Path(__file__).resolve().parent / "digests"


def render(prs: list[dict]) -> str:
    """Build the digest text (used for both terminal and file output)."""
    now = datetime.now().astimezone()
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"  GitHub PR Digest — {now:%A, %B %d, %Y  %H:%M %Z}")
    lines.append("=" * 60)

    if not prs:
        lines.append("")
        lines.append("No PRs need your attention.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"  {len(prs)} PR(s) need your attention")
    lines.append("=" * 60)

    by_repo: dict[str, list[dict]] = defaultdict(list)
    for pr in prs:
        by_repo[pr["repo"]].append(pr)

    for repo in sorted(by_repo):
        repo_prs = sorted(by_repo[repo], key=lambda p: p["age_days"], reverse=True)
        lines.append("")
        lines.append(f"{repo}  ({len(repo_prs)})")
        lines.append("-" * 60)
        for pr in repo_prs:
            age = "today" if pr["age_days"] == 0 else f"{pr['age_days']}d open"
            lines.append(f"  #{pr['number']}  {pr['title']}")
            lines.append(f"      by {pr['author']}  ·  {age}")
            lines.append(f"      {pr['url']}")
    lines.append("")
    return "\n".join(lines)


def write_digest_file(text: str) -> Path:
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = DIGEST_DIR / f"pr-digest-{stamp}.txt"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def main() -> int:
    load_env()  # pull GITHUB_TOKEN from .env if present; real env wins.
    try:
        token = get_token()
        prs = collect_prs(token)
    except DigestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    digest = render(prs)
    print(digest)

    try:
        path = write_digest_file(digest)
        print(f"(saved to {path})")
    except OSError as exc:
        print(f"warning: could not write digest file: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
