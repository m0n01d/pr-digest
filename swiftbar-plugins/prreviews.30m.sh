#!/bin/bash
# <xbar.title>PR Review Drafter</xbar.title>
# <xbar.version>v2.0</xbar.version>
# <xbar.desc>PRs waiting on your review: View, or kick a one-off auto code review. On-demand only.</xbar.desc>
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
exec "$REPO/review-drafter/menubar.sh" "$@"
