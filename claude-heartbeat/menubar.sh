#!/bin/bash
# <xbar.title>Claude Heartbeat</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.desc>Live activity of every Claude Code session: working, tool running, stalled, or idle. Goes red when a session goes quiet, shows when the internet is unreachable.</xbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
#
# Reads the per-session state files written by ~/.claude/hooks/heartbeat.sh.
# Status model:
#   working + last event PreToolUse            -> a tool is executing (long builds look like this; fine)
#   working + last event Post/Prompt, age<90s  -> Claude is actively generating       (green)
#   working, quiet 90s-5m                      -> long thinking OR a stalling request (yellow)
#   working, quiet >5m                         -> almost certainly stalled            (red)
#   idle                                       -> turn finished, waiting on you       (gray)
# Plus a network probe: if api.anthropic.com is unreachable, every "working" session
# is stuck by definition -> title gets the antenna prefix.

export LC_ALL=C
DIR="$HOME/.claude/heartbeat"
NOW=$(date +%s)
JQ=/usr/bin/jq
ME="$(cd "$(dirname "$0")" && pwd)/menubar.sh"

# Action modes: SwiftBar menu items call this same script back with an action
# argument, which sidesteps SwiftBar's shell-quoting limits for bash= items.
case "${1:-}" in
  copy-id)     printf '%s' "${2:-}" | pbcopy; exit 0 ;;
  copy-resume) printf 'claude --resume %s' "${2:-}" | pbcopy; exit 0 ;;
esac

fmt_age() {
  local s=$1
  if [ "$s" -lt 60 ]; then printf '%ds' "$s"
  elif [ "$s" -lt 3600 ]; then printf '%dm' "$((s / 60))"
  else printf '%dh%02dm' "$((s / 3600))" "$(((s % 3600) / 60))"
  fi
}

NET=up
nc -z -G 1 api.anthropic.com 443 >/dev/null 2>&1 || NET=down

# rows: "sev<TAB>session#<TAB>line#<TAB>menu line". Sorted by severity (desc)
# with session# and line# keeping each session's submenu attached to its row.
rows=""
sess_idx=0
worst=0
worst_age=0
have_any=0

for f in "$DIR"/*.json; do
  [ -e "$f" ] || continue
  # empty fields become "-" so consecutive tabs don't collapse under IFS
  IFS=$'\t' read -r ts status event tool cwd < <($JQ -r 'def nz: if . == null or . == "" then "-" else . end; [(.ts // 0), (.status | nz), (.event | nz), (.tool | nz), (.cwd | nz)] | @tsv' "$f" 2>/dev/null)
  [ -n "$ts" ] || continue
  [ "$tool" = "-" ] && tool=""
  [ "$cwd" = "-" ] && cwd=""
  age=$((NOW - ts))
  # a session that never sent SessionEnd (crash, force quit): drop after 24h
  if [ "$age" -gt 86400 ]; then rm -f "$f"; continue; fi
  have_any=1
  name=$(basename "${cwd:-?}")
  agef=$(fmt_age "$age")

  if [ "$status" = "idle" ]; then
    sev=1
    line="⚪ $name — idle, finished ${agef} ago | color=gray"
  elif [ "$event" = "PreToolUse" ]; then
    if [ "$age" -le 1800 ]; then sev=3; else sev=4; fi
    line="🔵 $name — ${tool:-tool} running for ${agef} | color=#4a90d9"
  elif [ "$age" -lt 90 ]; then
    sev=2
    line="🟢 $name — working (${tool:-responding} ${agef} ago) | color=green"
  elif [ "$age" -lt 300 ]; then
    sev=4
    line="🟡 $name — quiet for ${agef} (deep thinking or a slow link) | color=#c9a227"
  else
    sev=5
    line="🔴 $name — no activity for ${agef}, likely stalled | color=red"
  fi

  sess_idx=$((sess_idx + 1))
  sid=$(basename "$f" .json)
  rows+="${sev}	${sess_idx}	0	${line}"$'\n'
  rows+="${sev}	${sess_idx}	1	--${cwd:-unknown cwd} | color=gray size=11"$'\n'
  rows+="${sev}	${sess_idx}	2	--Last event: ${event}${tool:+ ($tool)}, ${agef} ago | color=gray size=11"$'\n'
  rows+="${sev}	${sess_idx}	3	-----"$'\n'
  if [ -n "$cwd" ]; then
    rows+="${sev}	${sess_idx}	4	--Open folder in Finder | bash=/usr/bin/open param0=${cwd} terminal=false"$'\n'
  fi
  rows+="${sev}	${sess_idx}	5	--Copy resume command | bash=${ME} param0=copy-resume param1=${sid} terminal=false"$'\n'
  rows+="${sev}	${sess_idx}	6	--Copy session id | bash=${ME} param0=copy-id param1=${sid} terminal=false"$'\n'
  if [ "$sev" -gt "$worst" ] || { [ "$sev" -eq "$worst" ] && [ "$age" -gt "$worst_age" ]; }; then
    worst=$sev
    worst_age=$age
  fi
done

wagef=$(fmt_age "$worst_age")
case $worst in
  5) title="🔴 $wagef" ;;
  4) title="🟡 $wagef" ;;
  3) title="🔵 $wagef" ;;
  2) title="🟢" ;;
  1) title="⚪" ;;
  *) title="⚪" ;;
esac
if [ "$NET" = "down" ] && [ "$worst" -ge 2 ]; then
  title="📡 ${title}"
fi

echo "$title"
echo "---"
if [ "$have_any" -eq 1 ]; then
  printf '%s' "$rows" | sort -t$'\t' -k1,1nr -k2,2n -k3,3n | cut -f4-
else
  echo "No Claude sessions tracked yet | color=gray"
  echo "State appears here once a session runs with the heartbeat hooks | color=gray size=11"
fi
echo "---"
if [ "$NET" = "up" ]; then
  echo "Internet: api.anthropic.com reachable ✓ | color=gray"
else
  echo "Internet: api.anthropic.com UNREACHABLE ✗ | color=red"
fi
echo "Refresh | refresh=true"
echo "Open heartbeat folder | bash=/usr/bin/open param0=$DIR terminal=false"
