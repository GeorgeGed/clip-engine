#!/usr/bin/env bash
# Is the whole thing up? One command, five answers.
#
#   ./service/status.sh
#
# The chain is: the Mac is awake -> the site is listening -> it is the
# runner -> the tunnel is connected -> the public hostname answers. Any
# one of those being false is the site being down, and they fail in ways
# that look alike from outside, so each gets its own line.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${TUNNEL_HOST:-clips.ult-orb.com}"
PORT="${CLIP_FACTORY_PORT:-8808}"
LABEL=com.clipfactory.site
ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mDOWN\033[0m  %s\n' "$1"; }
warn() { printf '  \033[33m??\033[0m    %s\n' "$1"; }

echo "── the Mac"
if pmset -g custom 2>/dev/null | sed -n '/^AC Power:/,/^Battery/p' | grep -qE "^ sleep +0"; then
  ok "set never to sleep on mains"
else
  held=$(pmset -g 2>/dev/null | grep -c "sleep prevented by")
  [ "$held" -gt 0 ] && warn "will sleep when idle; something is holding it awake by accident" \
                    || bad "will sleep when idle — see ./service/awake.sh"
fi

echo "── surviving a reboot"
# A LaunchAgent lives in gui/$UID and Apple is explicit that an agent
# "executes only while that user is logged in". So without auto-login the
# site does NOT come back from a reboot — it comes back from a LOGIN. That
# matters here because a reboot is not hypothetical: automatic macOS updates
# restart the machine on their own schedule.
if sysadminctl -autologin status 2>&1 | grep -qi "is ON"; then
  ok "automatic login is on — the agent starts without anyone at the keyboard"
else
  bad "automatic login is OFF — after a reboot this stays down until you log in"
fi
if defaults read /Library/Preferences/com.apple.SoftwareUpdate \
     AutomaticallyInstallMacOSUpdates 2>/dev/null | grep -q 1; then
  pend=$(softwareupdate --list --no-scan 2>&1 | grep -c "Action: restart")
  if [ "${pend:-0}" -gt 0 ]; then
    bad "$pend macOS update(s) pending that RESTART — an unattended outage is queued"
  else
    warn "macOS installs updates automatically; a restart can happen unattended"
  fi
fi
# kcpassword is how macOS stores the auto-login password, obfuscated. One
# left behind from a previous enablement is both a stale secret and a trap:
# setting autoLoginUser without rewriting it logs nobody in.
if [ -f /etc/kcpassword ] && ! sysadminctl -autologin status 2>&1 | grep -qi "is ON"; then
  warn "/etc/kcpassword exists but auto-login is off — a leftover, and stale"
fi

echo "── the site"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  st=$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | awk '/^\tstate = /{print $3}')
  [ "$st" = "running" ] && ok "LaunchAgent running" || bad "LaunchAgent is '$st'"
else
  pgrep -qf "web/server.py" && warn "running, but by hand — it will not come back after a reboot" \
                            || bad "not running (./service/install.sh)"
fi
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://127.0.0.1:$PORT/api/doctor")
case "$code" in
  200) ok "answering on :$PORT, no key set" ;;
  401) ok "answering on :$PORT, key required" ;;
  000) bad "nothing listening on :$PORT" ;;
  *)   warn "answering on :$PORT with $code" ;;
esac

echo "── the runner"
if [ -f web/.runner.lock ]; then
  holder=$(cat web/.runner.lock 2>/dev/null)
  pid=$(printf '%s' "$holder" | sed -E 's/.*pid ([0-9]+).*/\1/')
  kill -0 "$pid" 2>/dev/null && ok "$holder" || warn "stale lock from $holder"
else
  warn "no lock file — nothing has claimed the runner yet"
fi

echo "── Resolve"
# ASK THE SITE, NOT THE PROCESS TABLE. Two reasons: the process is called
# `Resolve`, not "DaVinci Resolve", so the obvious pgrep silently never
# matches — and more importantly a running Resolve with External Scripting
# set to None is just as useless as a closed one. `/api/doctor` connects to
# the scripting API, which is the thing that has to work.
doc=$(curl -s --max-time 20 -H "X-Clip-Key: ${CLIP_FACTORY_TOKEN:-}" \
        "http://127.0.0.1:$PORT/api/doctor" 2>/dev/null)
case "$doc" in
  *'"ok": true'*)  ok "scriptable — $(printf '%s' "$doc" | sed -E 's/.*"notes": \["([^"]*)".*/\1/')" ;;
  *'"ok": false'*) bad "reachable but not ready — $(printf '%s' "$doc" | sed -E 's/.*"notes": \["([^"]*)".*/\1/')" ;;
  *'key required'*) warn "cannot ask: set CLIP_FACTORY_TOKEN to check Resolve" ;;
  *)               warn "no answer from the site, so Resolve is unknown" ;;
esac

echo "── the tunnel"
if pgrep -qf "cloudflared.*tunnel"; then
  pgrep -fl "cloudflared.*tunnel" | head -1 | grep -q -- "--url" \
    && warn "a QUICK tunnel is up — random hostname, changes every run" \
    || ok "named tunnel process running"
else
  bad "cloudflared is not running"
fi

echo "── $HOST"
ns=$(dig +short NS ult-orb.com | head -1)
case "$ns" in
  *cloudflare*) ok "zone is on Cloudflare ($ns)" ;;
  *)            bad "zone is still on $ns — see service/MIGRATION.md" ;;
esac
# No `|| echo 000` — curl already writes 000 for a failed request, and the
# fallback concatenated onto it, printing "000000".
pub=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$HOST/" 2>/dev/null)
case "$pub" in
  401|200) ok "public hostname answers ($pub)" ;;
  000)     bad "public hostname does not resolve or does not answer" ;;
  530|502) bad "Cloudflare reached, the origin did not ($pub)" ;;
  *)       warn "public hostname returned $pub" ;;
esac
