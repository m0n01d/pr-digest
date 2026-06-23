#!/usr/bin/env python3
"""SwiftBar plugin: render open GitHub PRs as a menu bar dropdown.

Output follows the SwiftBar/xbar plugin protocol:
  * lines before the first `---` become the menu bar title
  * lines after it become the dropdown

Run by the launcher in swiftbar-plugins/prdigest.1h.sh (hourly + on open).

Cache-first, so the menu opens instantly. A render reads the last-known PR list
from a local cache and prints it immediately (no network), then — if the cache
is stale or you just opened the menu — kicks a *detached* background fetch. That
fetch updates the cache and pokes SwiftBar to redraw via its URL scheme, so the
count/list refresh a beat later without ever blocking the menu. While a
user-opened fetch is in flight the menu bar icon shows a refresh glyph; the
count stays visible.

The "new" indicator (a red tray badge) lights up when a PR is brand-new or has
new activity (updated_at) since you last looked. It clears only when you
actually open the menu — SwiftBar sets SWIFTBAR_PLUGIN_REFRESH_REASON=MenuOpen
on click vs Schedule/Manual for the background timer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from gh_prs import DigestError, collect_prs, get_token, load_env

REPO_DIR = Path(__file__).resolve().parent
LAUNCHER = REPO_DIR / "swiftbar-plugins" / "prdigest.1h.sh"
PLUGIN_ID = "prdigest.1h.sh"  # unique id for swiftbar://refreshplugin
TITLE_MAX = 60

# Refetch when the cache is older than this (covers wake-from-sleep etc.).
STALE_TTL = 300
# On a user open, refetch unless we *just* fetched — also breaks any refresh loop.
MENU_DEBOUNCE = 5

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


# --------------------------------------------------------------------------- #
# State: a per-plugin dir holding seen.json (badge tracking) + cache.json.
# --------------------------------------------------------------------------- #
def state_dir() -> Path:
    base = os.environ.get("SWIFTBAR_PLUGIN_DATA_PATH", "").strip()
    directory = Path(base) if base else REPO_DIR / "state"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_seen() -> dict[str, str]:
    path = state_dir() / "seen.json"
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
        (state_dir() / "seen.json").write_text(json.dumps(seen), encoding="utf-8")
    except OSError:
        pass  # state is best-effort; never break the menu over it


def load_cache() -> dict | None:
    path = state_dir() / "cache.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError):
        return None


def save_cache(prs: list[dict], error: str | None) -> None:
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "prs": prs,
        "error": error,
    }
    try:
        (state_dir() / "cache.json").write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def cache_age(cache: dict | None) -> float | None:
    if not cache or not cache.get("fetched_at"):
        return None
    try:
        when = datetime.fromisoformat(cache["fetched_at"])
        return (datetime.now(timezone.utc) - when).total_seconds()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Fetching (network) — only ever runs in the detached --fetch child or on the
# very first render when there's no cache yet.
# --------------------------------------------------------------------------- #
def fetch_and_cache(trigger_redraw: bool) -> None:
    load_env()
    try:
        token = get_token()
        prs = collect_prs(token)
        save_cache(prs, error=None)
    except DigestError as exc:
        # Keep the last-good list; attach a one-line error so the menu can warn.
        prev = load_cache() or {}
        save_cache(prev.get("prs", []), error=str(exc).splitlines()[0])
    if trigger_redraw:
        trigger_refresh()


def trigger_refresh() -> None:
    try:
        subprocess.Popen(
            ["open", "-g", f"swiftbar://refreshplugin?plugin={PLUGIN_ID}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def kick_background_fetch() -> None:
    """Spawn a fully detached `--fetch` so the menu render returns now."""
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--fetch"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Rendering (SwiftBar protocol)
# --------------------------------------------------------------------------- #
def sanitize(text: str) -> str:
    """SwiftBar uses `|` to separate text from params, and lines are records."""
    return " ".join(text.split()).replace("|", "¦")


def truncate(text: str, limit: int = TITLE_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def is_new(pr: dict, seen: dict[str, str]) -> bool:
    prev = seen.get(pr["url"])
    return prev is None or pr["updated_at"] > prev


def emit(text: str = "", **params: str) -> None:
    if params:
        param_str = " ".join(f"{k}={v}" for k, v in params.items() if v != "")
        print(f"{text} | {param_str}" if param_str else text)
    else:
        print(text)


def render_menu(prs: list[dict], seen: dict[str, str], *, spinner: bool,
                error: str | None) -> None:
    new_prs = [pr for pr in prs if is_new(pr, seen)]
    count = len(prs)

    # --- menu bar title (single line) ---
    if spinner:
        emit(str(count) if count else "", sfimage="arrow.triangle.2.circlepath")
    elif error and not prs:
        emit(sfimage="exclamationmark.triangle", sfcolor="orange")
    elif count == 0:
        emit(sfimage="checkmark.circle", sfcolor="green")
    elif new_prs:
        emit(str(count), sfimage="tray.full.fill", sfcolor="red")
    else:
        emit(str(count), sfimage="tray.full")

    print("---")

    if error:
        emit("Couldn't refresh GitHub", sfimage="exclamationmark.triangle",
             sfcolor="orange", color="#d08770")
        emit(sanitize(error), color="#888888")
        emit("Retry", bash=f'"{LAUNCHER}"', param1="--fetch", terminal="false",
             sfimage="arrow.clockwise")
        print("---")

    if count == 0 and not error:
        emit("No PRs need your attention", color="#888888")
    elif count:
        emit(f"{count} PR(s) need your attention", color="#888888")

        if new_prs:
            print("---")
            emit("🆕 New / updated", color="#888888")
            for pr in sorted(new_prs, key=lambda p: p["age_days"], reverse=True):
                pr_line(pr, new=True)

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
    emit("Refresh now", bash=f'"{LAUNCHER}"', param1="--fetch", terminal="false",
         sfimage="arrow.clockwise")
    emit("Mark all as seen", bash=f'"{LAUNCHER}"', param1="--mark-seen",
         terminal="false", refresh="true", sfimage="eye")
    age = cache_label()
    emit(f"Updated {age}", color="#888888")


def cache_label() -> str:
    cache = load_cache()
    if not cache or not cache.get("fetched_at"):
        return "—"
    try:
        when = datetime.fromisoformat(cache["fetched_at"]).astimezone()
        return f"{when:%H:%M}"
    except ValueError:
        return "—"


def pr_line(pr: dict, new: bool) -> None:
    age = "today" if pr["age_days"] == 0 else f"{pr['age_days']}d"
    title = truncate(sanitize(pr["title"]))
    label = f"#{pr['number']}  {title}  ·  {pr['author']} · {age}"
    if new:
        emit(label, href=pr["url"], sfimage="circle.fill", sfcolor="red")
    else:
        emit(label, href=pr["url"])


# --------------------------------------------------------------------------- #
def main() -> int:
    args = sys.argv[1:]
    reason = os.environ.get("SWIFTBAR_PLUGIN_REFRESH_REASON", "")

    if os.environ.get("PR_DIGEST_DEMO"):
        render_menu(DEMO_PRS, DEMO_SEEN, spinner="--spinner" in args, error=None)
        return 0

    if "--fetch" in args:
        fetch_and_cache(trigger_redraw=True)
        return 0

    if "--mark-seen" in args:
        cache = load_cache() or {}
        save_seen(cache.get("prs", []))
        return 0

    # --- render mode: instant, from cache ---
    cache = load_cache()
    if cache is None:
        # First ever run: nothing cached, so fetch inline this once.
        fetch_and_cache(trigger_redraw=False)
        cache = load_cache() or {"prs": [], "error": None}

    prs = cache.get("prs", [])
    error = cache.get("error")
    age = cache_age(cache)

    should_fetch = (
        age is None
        or age > STALE_TTL
        or (reason == "MenuOpen" and age > MENU_DEBOUNCE)
    )
    if should_fetch:
        kick_background_fetch()

    spinner = should_fetch and reason == "MenuOpen"
    seen = load_seen()
    render_menu(prs, seen, spinner=spinner, error=error)

    # Clear the "new" badge only after you've actually opened the menu.
    if reason == "MenuOpen":
        save_seen(prs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
