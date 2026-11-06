#!/usr/bin/env bash
# Clip Factory — the site and the render agent, together.
#
#   ./start.sh            local only, http://127.0.0.1:8808
#   ./start.sh --public   the same site on a public https URL
#
# THE SITE AND THE RENDERER ARE THE SAME MACHINE ON PURPOSE. Resolve serves
# its scripting API on its own GUI thread here, so nothing can render
# anywhere else — and a front end hosted apart from the renderer would only
# ever be a page saying "worker offline". A tunnel is the whole of hosting.
set -euo pipefail
cd "$(dirname "$0")"
PY=./.venv/bin/python
PORT="${CLIP_FACTORY_PORT:-8808}"

cleanup() { kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "── starting the site on :$PORT"
$PY web/server.py & SITE=$!
sleep 2

echo "── starting the render agent"
$PY worker/agent.py & AGENT=$!

if [ "${1:-}" = "--public" ]; then
  if ! command -v cloudflared >/dev/null; then
    echo
    echo "   cloudflared is not installed. One command, no account needed:"
    echo
    echo "       brew install cloudflared"
    echo
    echo "   Then run ./start.sh --public again."
  else
    echo "── opening a public URL (free, no account; it changes each run)"
    cloudflared tunnel --url "http://127.0.0.1:$PORT" 2>&1 \
      | grep --line-buffered -E "trycloudflare.com|ERR" &
  fi
fi

echo
echo "   http://127.0.0.1:$PORT"
echo "   Ctrl-C stops both."
wait $SITE
