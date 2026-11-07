#!/usr/bin/env bash
# Can the editor scrub a clip served from this URL?
#
#   ./worker/check-range.sh "https://<ref>.supabase.co/storage/v1/object/public/clips/x.mp4"
#   ./worker/check-range.sh "<url>" -H "Authorization: Bearer <token>"
#
# Anything after the URL is passed straight to curl, for a private bucket or
# a gated origin. Note a REDIRECT is not a pass: the first run of this hit
# our own key gate and got a 303, and reporting that as "Range broken" would
# have been wrong in the other direction.
#
# WHY THIS IS A SCRIPT AND NOT A NOTE. The editor plays 20-40MB mp4s by
# asking for byte ranges, so a storage layer that answers 200-with-the-whole-
# file instead of 206 does not fail — it just downloads 30MB on every seek
# and feels broken. That is the kind of thing nobody tests until it is in
# front of a client.
#
# Supabase's storage ORIGIN implements Range: `parseRangeHeader` in
# src/storage/range.ts handles bytes=N-M and suffix ranges, the renderer
# sets Accept-Ranges and Content-Range, and the adapter carries
# httpStatusCode through. Read from source, not assumed. What is NOT settled
# is the CDN in front of a public URL, which is the layer most likely to
# surprise — hence this.
set -uo pipefail
U="${1:-}"
[ -n "$U" ] || { echo "usage: $0 <url> [extra curl args]"; exit 2; }
shift
EXTRA=("$@")
ok(){ printf '  \033[32mOK\033[0m   %s\n' "$1"; }
bad(){ printf '  \033[31mNO\033[0m   %s\n' "$1"; FAIL=1; }
FAIL=0

echo "── headers for a 1KB range"
H=$(curl -sS -D - -o /dev/null --max-time 30 -r 0-1023 "${EXTRA[@]}" "$U" 2>&1)
code=$(printf '%s' "$H" | awk 'NR==1{print $2}')
case "$code" in
  206) ok "206 Partial Content" ;;
  30*) bad "status $code — a REDIRECT, not a Range answer. Follow it, or"
       bad "     authenticate with -H, and run this against the final URL." ;;
  *)   bad "status $code — expected 206" ;;
esac
printf '%s' "$H" | grep -qi '^content-range:' \
  && ok "Content-Range: $(printf '%s' "$H" | grep -i '^content-range:' | tr -d '\r' | cut -d' ' -f2-)" \
  || bad "no Content-Range"
printf '%s' "$H" | grep -qi '^accept-ranges: *bytes' \
  && ok "Accept-Ranges: bytes" || bad "no Accept-Ranges: bytes"
len=$(printf '%s' "$H" | grep -i '^content-length:' | tr -d '\r' | awk '{print $2}')
[ "${len:-0}" = "1024" ] && ok "Content-Length 1024 (the range, not the file)" \
  || bad "Content-Length ${len:-?} — a whole-file body means no Range"

echo "── a mid-file range must be the same bytes as the same slice of the whole file"
full=$(mktemp); part=$(mktemp)
curl -sS --max-time 180 "${EXTRA[@]}" -o "$full" "$U"
size=$(wc -c < "$full" | tr -d ' ')
if [ "${size:-0}" -gt 4096 ]; then
  mid=$((size / 2))
  curl -sS --max-time 60 -r "${mid}-$((mid + 2047))" "${EXTRA[@]}" -o "$part" "$U"
  a=$(dd if="$full" bs=1 skip="$mid" count=2048 2>/dev/null | shasum | cut -c1-16)
  b=$(shasum < "$part" | cut -c1-16)
  [ "$a" = "$b" ] && ok "mid-file 2KB slice byte-identical ($a)" \
                  || bad "mid-file slice DIFFERS: whole=$a range=$b"
else
  bad "file is only ${size:-0} bytes — use a real clip"
fi

echo "── caching, which decides whether a rebuilt clip serves stale"
cc=$(printf '%s' "$H" | grep -i '^cache-control:' | tr -d '\r' | cut -d' ' -f2-)
cf=$(printf '%s' "$H" | grep -iE '^(cf-cache-status|x-cache):' | tr -d '\r')
echo "  cache-control: ${cc:-(none)}"
echo "  cache header : ${cf:-(none)}"
echo "  A clip is REBUILT at the same key, so anything cacheable here means"
echo "  the editor can play a mix of old and new bytes. Upload rebuilds under"
echo "  a new path, or set no-store."
rm -f "$full" "$part"
echo
[ $FAIL -eq 0 ] && echo "  VERDICT: the editor can scrub this." \
                || echo "  VERDICT: Range is not working — serve clips from R2 or S3 instead."
exit $FAIL
