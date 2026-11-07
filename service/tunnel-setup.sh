#!/usr/bin/env bash
# Create the named tunnel and point clips.ult-orb.com at it.
#
#   ./service/tunnel-setup.sh
#
# Run this AFTER ult-orb.com is on Cloudflare's nameservers (see
# service/MIGRATION.md). It is idempotent: an existing tunnel or route is
# reused, not duplicated.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
NAME="${TUNNEL_NAME:-clip-factory}"
HOST="${TUNNEL_HOST:-$(cat "$REPO/service/HOST" 2>/dev/null || echo clips.example.com)}"
PORT="${CLIP_FACTORY_PORT:-8808}"
CFDIR="$HOME/.cloudflared"

command -v cloudflared >/dev/null || { echo "cloudflared is not installed"; exit 1; }

if [ ! -f "$CFDIR/cert.pem" ]; then
  cat <<'MSG'
Not logged in to Cloudflare yet. Run this first — it opens a browser, you
pick the ult-orb.com zone, and it writes ~/.cloudflared/cert.pem:

    cloudflared tunnel login

The zone has to be on Cloudflare's nameservers already or it will not be
listed. Then run this script again.
MSG
  exit 1
fi

# -- the tunnel
if cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$NAME"; then
  echo "tunnel '$NAME' already exists"
else
  echo "creating tunnel '$NAME'"
  cloudflared tunnel create "$NAME"
fi
UUID=$(cloudflared tunnel list 2>/dev/null | awk -v n="$NAME" '$2==n {print $1}' | head -1)
[ -n "$UUID" ] || { echo "could not determine the tunnel id"; exit 1; }
echo "  id $UUID"

CREDS="$CFDIR/$UUID.json"
[ -f "$CREDS" ] || { echo "no credentials file at $CREDS"; exit 1; }

# -- the config
#
# THE CATCH-ALL IS REQUIRED. cloudflared refuses a config whose last ingress
# rule has a hostname; without `- service: http_status:404` it will not
# start, and the error names the rule rather than the omission.
#
# originRequest timeouts: the default connect timeout is fine, but a clip is
# tens of megabytes and a clips.zip is hundreds, so the read side gets room.
# `noTLSVerify` is irrelevant here — the origin is plain http on loopback.
cat > "$CFDIR/config.yml" <<CFG
# written by service/tunnel-setup.sh — edit there, not here
tunnel: $UUID
credentials-file: $CREDS

# A RENDER MUST NOT BE INTERRUPTED BY A SELF-UPDATE. cloudflared auto-updates
# and RESTARTS itself by default; a Resolve build takes minutes and the site
# is behind this process the whole time.
no-autoupdate: true

loglevel: info
logfile: $HOME/Library/Logs/cloudflared.log

ingress:
  - hostname: $HOST
    service: http://127.0.0.1:$PORT
    originRequest:
      # A 40MB mp4 streamed to a <video>, and a clips.zip that can be
      # hundreds of MB, both have to finish.
      connectTimeout: 30s
      tcpKeepAlive: 30s
      noHappyEyeballs: true
      httpHostHeader: $HOST
  # Required. Anything that is not the hostname above gets a flat 404
  # rather than reaching the site at all.
  - service: http_status:404
CFG
echo "  config $CFDIR/config.yml"

# -- the DNS record
echo "routing $HOST -> $NAME"
if cloudflared tunnel route dns "$NAME" "$HOST" 2>&1 | tee /tmp/route.out | grep -qiE "already|exists"; then
  echo "  the record already exists — leaving it alone"
  cat /tmp/route.out | sed 's/^/    /'
fi

cat <<MSG

  Validate the config:   cloudflared tunnel ingress validate
  Try it in the foreground: cloudflared tunnel run $NAME
  Install it as a service:  sudo cloudflared service install

  Then $HOST is the address, permanently.
MSG
