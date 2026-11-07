#!/usr/bin/env bash
# Will this Mac still be awake to answer the URL?
#
#   ./service/awake.sh          # report, change nothing
#
# A permanent address is only as good as the machine behind it, and this one
# cannot be replaced by a server: the build stage drives Resolve's scripting
# API, which lives on a GUI thread in a logged-in desktop session. So the
# Mac being asleep is the site being down.
#
# This only REPORTS. Power settings are the user's machine, not ours.
set -uo pipefail
echo "=== this Mac ==="
echo "   model    $(sysctl -n hw.model 2>/dev/null)"
echo "   power    $(pmset -g batt 2>/dev/null | head -1)"
echo
echo "=== sleep settings now ==="
pmset -g custom 2>/dev/null | sed 's/^/   /' | grep -iE "sleep|standby|powernap|tcpkeep|disksleep|lid" | head -20
echo
echo "=== what matters, and why ==="
cat <<'TXT'
   sleep           minutes of idle before the SYSTEM sleeps. 0 = never.
                   Non-zero means the site goes dark on an idle Mac.
   displaysleep    the screen only. Harmless — leave it on.
   disksleep       harmless.
   tcpkeepalive    1 lets the Mac answer the network in standby. With it at
                   0 the tunnel drops the moment it sleeps.
   powernap        wakes periodically for background work. Does NOT keep a
                   service answering.

   A laptop with the LID CLOSED sleeps regardless of `sleep` unless it is on
   power AND has an external display, or you hold it awake explicitly.
TXT
echo
echo "=== to hold it awake for a session, without changing anything ==="
cat <<'TXT'
   caffeinate -dims          # until you Ctrl-C: no idle, disk or system sleep
   caffeinate -dims -t 28800 # eight hours, then back to normal

   -d display  -i idle  -m disk  -s system (only while on mains)  -u user-active
TXT
echo
echo "=== to make it permanent (YOUR machine, YOUR call — needs sudo) ==="
cat <<'TXT'
   sudo pmset -c sleep 0 tcpkeepalive 1     # -c = only when on mains power
TXT
echo "=== what is holding it awake RIGHT NOW ==="
# This is the line that explains why an aggressive `sleep` setting has not
# bitten yet: an app with a power assertion masks it. Quit the apps and the
# setting is what is left.
pmset -g 2>/dev/null | grep -E "sleep prevented by" | sed 's/^/   /' || echo "   nothing — the setting above is what you get"
echo
if pmset -g custom 2>/dev/null | sed -n '/^AC Power:/,/^Battery/p' | grep -qE "^ sleep +0"; then
  echo "   VERDICT: on mains this Mac is already set never to sleep."
else
  echo "   VERDICT: on mains this Mac is set to sleep when idle, so the URL"
  echo "            dies with it. Anything in the line above is masking that"
  echo "            by accident, not holding it open on purpose — quit those"
  echo "            apps and the setting is what is left. Set pmset, or run"
  echo "            caffeinate deliberately."
fi
