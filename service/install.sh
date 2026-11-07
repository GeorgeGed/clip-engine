#!/usr/bin/env bash
# Install the site as a LaunchAgent so it comes back by itself.
#
#   ./service/install.sh
#   CLIP_FACTORY_TOKEN=… ./service/install.sh
#
# The agent runs as George, in his GUI session, because the build stage
# drives Resolve's scripting API and that needs a logged-in desktop. See
# service/README.md for why PATH is set explicitly — it is the difference
# between this working and every ffmpeg call failing.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
PY="$REPO/.venv/bin/python"
LABEL=com.clipfactory.site
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$REPO/jobs/_service"
PORT="${CLIP_FACTORY_PORT:-8808}"

[ -x "$PY" ] || { echo "no interpreter at $PY"; exit 1; }
mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"

# THE KEY HAS TO OUTLIVE THE SHELL THAT MADE IT. start.sh generates one per
# run, which is right for a throwaway quick tunnel and wrong for a service:
# a key that changes whenever the agent restarts is a bookmark that stops
# working for no visible reason. So it is generated once, kept in
# web/.site-key (gitignored, 0600) and reused on every re-install.
KEYFILE="$REPO/web/.site-key"
if [ -z "${CLIP_FACTORY_TOKEN:-}" ] && [ -f "$KEYFILE" ]; then
  CLIP_FACTORY_TOKEN="$(cat "$KEYFILE")"
fi
if [ -z "${CLIP_FACTORY_TOKEN:-}" ] && [ "${1:-}" != "--no-key" ]; then
  CLIP_FACTORY_TOKEN="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
fi
if [ -n "${CLIP_FACTORY_TOKEN:-}" ]; then
  printf '%s' "$CLIP_FACTORY_TOKEN" > "$KEYFILE"
  chmod 600 "$KEYFILE"
fi

# The PATH the job will get. Homebrew first, then the user's own bin, then
# the system — because `ffmpeg` and friends are called by bare name and
# launchd's default PATH has neither of the first two.
JOB_PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

tok_entry=""
if [ -n "${CLIP_FACTORY_TOKEN:-}" ]; then
  tok_entry="        <key>CLIP_FACTORY_TOKEN</key>
        <string>${CLIP_FACTORY_TOKEN}</string>"
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PY}</string>
        <string>${REPO}/web/server.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${REPO}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${JOB_PATH}</string>
        <!-- Without this the logs are EMPTY. Python block-buffers stdout
             when it is not a tty, and a service's stdout never is, so
             nothing reaches site.out.log until the buffer fills or the
             process dies — which for a server that stays up means never.
             Found by installing this agent and getting a blank log from a
             process that was demonstrably running. -->
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>CLIP_FACTORY_PORT</key>
        <string>${PORT}</string>
${tok_entry}
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>${LOGS}/site.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOGS}/site.err.log</string>
</dict>
</plist>
PLIST

# `bootstrap`, not the deprecated `load` — and bootout first so a re-install
# replaces rather than errors with "service already loaded".
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "installed $LABEL"
echo "  plist   $PLIST"
echo "  logs    $LOGS/site.{out,err}.log"
echo "  port    $PORT"
if [ -n "${CLIP_FACTORY_TOKEN:-}" ]; then
  echo "  key     $KEYFILE"
  echo
  echo "  http://127.0.0.1:$PORT/?k=$CLIP_FACTORY_TOKEN"
else
  echo "  key     none (local only)"
fi
