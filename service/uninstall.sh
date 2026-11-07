#!/usr/bin/env bash
set -euo pipefail
LABEL=com.clipfactory.site
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "removed $LABEL"
