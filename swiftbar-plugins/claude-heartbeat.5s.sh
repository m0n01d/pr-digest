#!/bin/bash
# <xbar.title>Claude Heartbeat</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.desc>Live activity of every Claude Code session: working, tool running, stalled, or idle.</xbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
#
# Thin launcher. Self-locating, and resolves a symlink so the repo can live anywhere.
SELF="$0"
if [ -L "$SELF" ]; then
  T="$(readlink "$SELF")"
  case "$T" in /*) SELF="$T" ;; *) SELF="$(dirname "$SELF")/$T" ;; esac
fi
REPO="$(cd "$(dirname "$SELF")/.." && pwd)"
exec "$REPO/claude-heartbeat/menubar.sh" "$@"
