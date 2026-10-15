# Claude Heartbeat

A menu bar widget that shows whether each Claude Code session is working,
running a tool, stalled, or waiting on you. It works even when your network
dies mid-request, because the hook stamps locally and the widget notices when
the stamps stop.

| Icon | Meaning |
|---|---|
| 🔵 | A tool is running (long builds look like this) |
| 🟢 | Working, active in the last 90 seconds |
| 🟡 | Quiet for 90 seconds to 5 minutes: thinking, or a slow link |
| 🔴 | Quiet for more than 5 minutes: stalled |
| ⚪ | Turn finished, waiting on you |
| 📡 | Prefix: `api.anthropic.com` is unreachable |

Each session is a submenu: its folder, last event, open in Finder, copy the
`claude --resume` command, copy the session id.

## Install

Needs [SwiftBar](https://swiftbar.app), `jq`, and Claude Code.

1. Install the hook and wire it into `~/.claude/settings.json`:
   ```bash
   ./claude-heartbeat/install.sh
   ```
2. Point SwiftBar's plugin folder at this repo's `swiftbar-plugins/`, or symlink
   the launcher into your plugin folder:
   ```bash
   ln -s "$PWD/swiftbar-plugins/claude-heartbeat.5s.sh" "<your SwiftBar plugin folder>/"
   ```
3. Restart open Claude sessions so they pick up the hooks.

## Files

| File | Purpose |
|---|---|
| `hook.sh` | Claude Code hook. Writes `~/.claude/heartbeat/<session>.json`. Never blocks a turn. |
| `menubar.sh` | SwiftBar renderer. |
| `install.sh` | Copies the hook and edits `settings.json` (backup kept). |
| `../swiftbar-plugins/claude-heartbeat.5s.sh` | Thin SwiftBar launcher, 5 second refresh. |

To uninstall, remove the plugin link and delete the heartbeat entries from
`~/.claude/settings.json` (restore `settings.json.bak-heartbeat` if you have not
changed it since).
