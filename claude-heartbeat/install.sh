#!/bin/bash
# Installs the heartbeat hook and wires it into ~/.claude/settings.json.
# Safe to re-run: existing heartbeat entries are replaced, other hooks untouched.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SETTINGS="$HOME/.claude/settings.json"
HOOK="$HOME/.claude/hooks/heartbeat.sh"

mkdir -p "$HOME/.claude/hooks"
install -m 755 "$HERE/hook.sh" "$HOOK"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "$SETTINGS.bak-heartbeat"

# Async for the chatty events so a turn never waits on the hook; Stop and
# SessionEnd are sync so the final state is written before exit.
jq --arg cmd "$HOOK" '
  def entry(async): {hooks: [{type: "command", command: $cmd, timeout: 10} + (if async then {async: true} else {} end)]};
  def drop: map(select(any(.hooks[]?; .command == $cmd) | not));
  reduce (["SessionStart","UserPromptSubmit","PreToolUse","PostToolUse"] | .[]) as $e (.;
    .hooks[$e] = ((.hooks[$e] // []) | drop) + [entry(true)])
  | reduce (["Stop","SessionEnd"] | .[]) as $e (.;
    .hooks[$e] = ((.hooks[$e] // []) | drop) + [entry(false)])
' "$SETTINGS.bak-heartbeat" > "$SETTINGS"

echo "Hook installed. Backup: $SETTINGS.bak-heartbeat"
echo "Restart running Claude sessions, then link the plugin (see README)."
