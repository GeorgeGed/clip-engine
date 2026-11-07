#!/usr/bin/env bash
# Clip Factory — the site and the render agent, together.
#
#   ./start.sh            local only, http://127.0.0.1:8808
#   ./start.sh --public   the same site on a public https URL, behind a key
#
# THE SITE AND THE RENDERER ARE THE SAME MACHINE ON PURPOSE. Resolve serves
# its scripting API on its own GUI thread here, so nothing can render
# anywhere else — and a front end hosted apart from the renderer would only
# ever be a page saying "worker offline". A tunnel is the whole of hosting.
#
# --public GENERATES A KEY, and that is not belt-and-braces. Binding to
# 127.0.0.1 stops protecting anything the moment a tunnel points at it: the
# tunnel's traffic arrives on the loopback socket exactly as a local
# browser's does. And the site is not a viewer — it queues jobs that drive
# Resolve on this Mac and serves finished clips. Pass CLIP_FACTORY_TOKEN to
# keep the same key across runs (the URL changes every run either way).
set -euo pipefail
cd "$(dirname "$0")"
PY=./.venv/bin/python
PORT="${CLIP_FACTORY_PORT:-8808}"
PUBLIC=0
[ "${1:-}" = "--public" ] && PUBLIC=1
TUNNEL_LOG="${TMPDIR:-/tmp}/clip-factory-tunnel.log"

if [ "$PUBLIC" = 1 ]; then
  if ! command -v cloudflared >/dev/null; then
    echo
    echo "   cloudflared is not installed. One command, no account needed:"
    echo "       brew install cloudflared"
    echo "   Carrying on locally."
    echo
    PUBLIC=0
  else
    export CLIP_FACTORY_TOKEN="${CLIP_FACTORY_TOKEN:-$($PY -c \
      'import secrets; print(secrets.token_urlsafe(24))')}"
  fi
fi

cleanup() { kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "── starting the site on :$PORT"
$PY web/server.py & SITE=$!
sleep 2

# THE SITE IS THE RUNNER HERE, so the agent is NOT started alongside it.
# Against the local SQLite both are runners — the site queues a job and
# leaves its row at `state='queued'`, which is exactly what the agent claims
# — and two processes driving one Resolve is the invariant this pipeline
# rests on. `web/runlock.py` refuses it outright now; this just avoids
# starting something that would immediately exit. The agent is for a SECOND
# Mac, or for a cloud control plane:
#
#     CLIP_WORKER_URL=https://… CLIP_WORKER_TOKEN=… ./.venv/bin/python worker/agent.py
#
if [ -n "${CLIP_WORKER_URL:-}" ]; then
  echo "── starting the render agent against $CLIP_WORKER_URL"
  $PY worker/agent.py & AGENT=$!
fi

PUBLIC_URL=""
if [ "$PUBLIC" = 1 ]; then
  echo "── opening a public URL (free, no account; it changes each run)"
  : > "$TUNNEL_LOG"
  cloudflared tunnel --url "http://127.0.0.1:$PORT" >>"$TUNNEL_LOG" 2>&1 &
  for _ in $(seq 1 40); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
                 "$TUNNEL_LOG" | head -1 || true)
    [ -n "$PUBLIC_URL" ] && break
    sleep 0.5
  done
fi

echo
if [ -n "$PUBLIC_URL" ]; then
  echo "   PUBLIC   $PUBLIC_URL/?k=$CLIP_FACTORY_TOKEN"
  echo "            (the whole link, key included — open it once and it"
  echo "             sets a cookie, so the key leaves the address bar)"
  echo "   key      $CLIP_FACTORY_TOKEN"
  echo
  echo "   local    http://127.0.0.1:$PORT/?k=$CLIP_FACTORY_TOKEN"
  echo "   tunnel log: $TUNNEL_LOG"
elif [ "$PUBLIC" = 1 ]; then
  echo "   the tunnel did not report a URL — see $TUNNEL_LOG"
  echo "   local    http://127.0.0.1:$PORT/?k=${CLIP_FACTORY_TOKEN:-}"
else
  echo "   http://127.0.0.1:$PORT"
fi
echo
echo "   Ctrl-C stops the site, the agent and the tunnel."
wait $SITE
