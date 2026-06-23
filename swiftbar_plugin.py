#!/usr/bin/env python3
"""SwiftBar plugin: render open GitHub PRs as a menu bar dropdown.

Output follows the SwiftBar/xbar plugin protocol:
  * lines before the first `---` become the menu bar title
  * lines after it become the dropdown

Run by the launcher in swiftbar-plugins/prdigest.1h.sh (hourly + on open).

The "new" indicator (a red tray badge) lights up when a PR is brand-new or has
new activity (updated_at) since you last looked. It clears only when you
actually open the menu — SwiftBar sets SWIFTBAR_PLUGIN_REFRESH_REASON=MenuOpen
on click vs Schedule/Manual for the background timer — so a background refresh
never silently dismisses it.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from gh_prs import DigestError, collect_prs, get_token, load_env

REPO_DIR = Path(__file__).resolve().parent
LAUNCHER = REPO_DIR / "swiftbar-plugins" / "prdigest.1h.sh"
TITLE_MAX = 60

# Fake data for screenshots/docs — set PR_DIGEST_DEMO=1 to render without a
# token or network call. Two of these count as "new" (see DEMO_SEEN).
DEMO_PRS = [
    {"repo": "acme/widgets", "number": 142, "author": "jdoe", "age_days": 2,
     "title": "Fix flaky checkout total when the cart is empty",
     "url": "https://github.com/acme/widgets/pull/142",
     "updated_at": "2026-06-23T09:00:00Z"},
    {"repo": "acme/widgets", "number": 137, "author": "rsmith", "age_days": 5,
     "title": "Add dark mode to the settings page",
     "url": "https://github.com/acme/widgets/pull/137",
     "updated_at": "2026-06-18T12:00:00Z"},
    {"repo": "acme/api", "number": 88, "author": "aturing", "age_days": 12,
     "title": "Migrate auth callers to tokenizer v3",
     "url": "https://github.com/acme/api/pull/88",
     "updated_at": "2026-06-22T17:30:00Z"},
]
# #137 already seen, so only #142 and #88 light up as new.
DEMO_SEEN = {"https://github.com/acme/widgets/pull/137": "2026-06-18T12:00:00Z"}


def state_path() -> Path:
    """Where seen-state lives: SwiftBar's per-plugin data dir, else ./state."""
    base = os.environ.get("SWIFTBAR_PLUGIN_DATA_PATH", "").strip()
    directory = Path(base) if base else REPO_DIR / "state"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "seen.json"


def load_seen() -> dict[str, str]:
    path = state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def save_seen(prs: list[dict]) -> None:
    seen = {pr["url"]: pr["updated_at"] for pr in prs}
    try:
        state_path().write_text(json.dumps(seen), encoding="utf-8")
    except OSError:
        pass  # state is best-effort; never break the menu over it


def sanitize(text: str) -> str:
    """SwiftBar uses `|` to separate text from params, and lines are records."""
    cleaned = " ".join(text.split())  # collapse whitespace/newlines
    return cleaned.replace("|", "¦")


def truncate(text: str, limit: int = TITLE_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def is_new(pr: dict, seen: dict[str, str]) -> bool:
    """New to the list, or updated since we last recorded it."""
    prev = seen.get(pr["url"])
    return prev is None or pr["updated_at"] > prev


def emit(text: str = "", **params: str) -> None:
    """Print one SwiftBar menu line: `text | k=v k=v`."""
    if params:
        param_str = " ".join(f"{k}={v}" for k, v in params.items() if v != "")
        print(f"{text} | {param_str}" if param_str else text)
    else:
        print(text)


def render_menu(prs: list[dict], seen: dict[str, str]) -> None:
    new_prs = [pr for pr in prs if is_new(pr, seen)]
    count = len(prs)

    # --- menu bar title (single line) ---
    if count == 0:
        emit(sfimage="checkmark.circle", sfcolor="green")
    elif new_prs:
        emit(str(count), sfimage="tray.full.fill", sfcolor="red")
    else:
        emit(str(count), sfimage="tray.full")

    print("---")

    if count == 0:
        emit("No PRs need your attention", color="#888888")
    else:
        emit(f"{count} PR(s) need your attention", color="#888888")

        if new_prs:
            print("---")
            emit("🆕 New / updated", color="#888888")
            for pr in sorted(new_prs, key=lambda p: p["age_days"], reverse=True):
                pr_line(pr, new=True)

        # Grouped by repo.
        by_repo: dict[str, list[dict]] = defaultdict(list)
        for pr in prs:
            by_repo[pr["repo"]].append(pr)
        for repo in sorted(by_repo):
            print("---")
            repo_prs = by_repo[repo]
            emit(f"{repo}  ({len(repo_prs)})", color="#888888")
            for pr in sorted(repo_prs, key=lambda p: p["age_days"], reverse=True):
                pr_line(pr, new=is_new(pr, seen))

    # --- footer actions ---
    print("---")
    emit("Refresh now", refresh="true", sfimage="arrow.clockwise")
    emit(
        "Mark all as seen",
        bash=f'"{LAUNCHER}"',
        param1="--mark-seen",
        terminal="false",
        refresh="true",
        sfimage="eye",
    )
    now = datetime.now().astimezone()
    emit(f"Updated {now:%H:%M}", color="#888888")


def pr_line(pr: dict, new: bool) -> None:
    age = "today" if pr["age_days"] == 0 else f"{pr['age_days']}d"
    title = truncate(sanitize(pr["title"]))
    label = f"#{pr['number']}  {title}  ·  {pr['author']} · {age}"
    if new:
        emit(label, href=pr["url"], sfimage="circle.fill", sfcolor="red")
    else:
        emit(label, href=pr["url"])


def render_error(exc: DigestError) -> None:
    """Friendly menu instead of a traceback when something's wrong."""
    emit("PR", sfimage="exclamationmark.triangle", sfcolor="orange")
    print("---")
    for line in str(exc).splitlines():
        emit(sanitize(line.strip()) or " ", color="#888888")
    print("---")
    emit("Open setup instructions", href=f"file://{REPO_DIR / 'README.md'}")
    emit("Retry", refresh="true", sfimage="arrow.clockwise")


def main() -> int:
    mark_seen_only = "--mark-seen" in sys.argv[1:]
    reason = os.environ.get("SWIFTBAR_PLUGIN_REFRESH_REASON", "")

    if os.environ.get("PR_DIGEST_DEMO"):
        render_menu(DEMO_PRS, DEMO_SEEN)
        return 0

    load_env()
    try:
        token = get_token()
        prs = collect_prs(token)
    except DigestError as exc:
        render_error(exc)
        return 0  # exit 0 so SwiftBar shows our menu, not its error UI

    if mark_seen_only:
        save_seen(prs)
        return 0

    seen = load_seen()
    render_menu(prs, seen)

    # Clear the "new" badge only after you've actually opened the menu.
    if reason == "MenuOpen":
        save_seen(prs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
