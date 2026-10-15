#!/bin/bash
# Claude Code heartbeat — stamps per-session activity into ~/.claude/heartbeat/<session>.json
# so the SwiftBar widget (menubar.sh in this folder) can show
# working / tool-running / stalled / idle per session. Reads hook JSON on stdin.
# Must never block or fail the turn: every path exits 0.
set -u
DIR="$HOME/.claude/heartbeat"
mkdir -p "$DIR" 2>/dev/null || exit 0

IN=$(cat 2>/dev/null) || IN='{}'
SID=$(printf '%s' "$IN" | /usr/bin/jq -r '.session_id // empty' 2>/dev/null)
SID=${SID//[^a-zA-Z0-9_-]/}
[ -n "$SID" ] || exit 0
EVENT=$(printf '%s' "$IN" | /usr/bin/jq -r '.hook_event_name // "unknown"' 2>/dev/null)
FILE="$DIR/$SID.json"

case "$EVENT" in
  SessionEnd)
    rm -f "$FILE"
    exit 0
    ;;
  Stop)
    STATUS=idle
    ;;
  SessionStart)
    STATUS=idle
    ;;
  *)
    STATUS=working
    ;;
esac

printf '%s' "$IN" | /usr/bin/jq -c \
  --arg status "$STATUS" \
  --arg ts "$(date +%s)" \
  '{ts: ($ts|tonumber),
    status: $status,
    event: (.hook_event_name // ""),
    tool: (.tool_name // ""),
    cwd: (.cwd // "")}' \
  > "$FILE.tmp" 2>/dev/null && mv "$FILE.tmp" "$FILE" 2>/dev/null
exit 0
