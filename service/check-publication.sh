#!/usr/bin/env bash
# Is Ult Orb still exactly as it was?
#
#   ./service/check-publication.sh            # check it now
#   ./service/check-publication.sh --baseline # record what "fine" looks like
#
# THE POINT. Moving ult-orb.com's nameservers to Cloudflare is a change to a
# LIVE publication made for the sake of an internal tool, so the publication
# gets a test and the tool does not get the benefit of the doubt. This
# compares DNS, TLS and the served page against a baseline taken before the
# move. Run it before, then after the nameservers switch, and again a day
# later once caches everywhere have turned over.
set -uo pipefail
cd "$(dirname "$0")/.."
DIR=service/dns-backup
BASE="$DIR/publication-baseline.txt"
mkdir -p "$DIR"

probe() {
  echo "== resolution =="
  echo "   NS      $(dig +short NS ult-orb.com | sort | tr '\n' ' ')"
  echo "   apex A  $(dig +short A ult-orb.com | sort | tr '\n' ' ')"
  echo "   www     $(dig +short CNAME www.ult-orb.com | sort | tr '\n' ' ')$(dig +short A www.ult-orb.com | sort | tr '\n' ' ')"
  echo "   SPF     $(dig +short TXT ult-orb.com | sort | tr '\n' ' ')"
  echo "   DMARC   $(dig +short TXT _dmarc.ult-orb.com | sort | tr '\n' ' ')"
  echo "   MX      $(dig +short MX ult-orb.com | sort | tr '\n' ' ')"
  # CAA is in here because WordPress.com's own SSL troubleshooting names it:
  # "CAA DNS records that do not allow Let's Encrypt to issue a certificate".
  # The zone has none today, so any CA may issue and Automattic can renew.
  # One that names only Cloudflare's CAs would lock Let's Encrypt out and
  # take the publication down at the NEXT RENEWAL, not at the change.
  caa=$(dig +short CAA ult-orb.com | sort | tr '\n' ' ')
  echo "   CAA     ${caa:-(none — correct: any CA may issue)}"
  if [ -n "$caa" ] && ! echo "$caa" | grep -q "letsencrypt.org"; then
    echo "   !! CAA records exist and do NOT name letsencrypt.org."
    echo "   !! Automattic's certificate will fail to renew. Remove them,"
    echo "   !! or add: 0 issue \"letsencrypt.org\""
  fi
  echo
  echo "== the site itself =="
  echo "   status  $(curl -sL -o /dev/null -w '%{http_code}' --max-time 20 https://ult-orb.com/)"
  echo "   title   $(curl -sL --max-time 20 https://ult-orb.com/ 2>/dev/null | grep -oiE '<title[^>]*>[^<]*</title>' | head -1)"
  echo "   bytes   $(curl -sL --max-time 20 https://ult-orb.com/ 2>/dev/null | wc -c | tr -d ' ')"
  echo "   www     $(curl -sL -o /dev/null -w '%{http_code} -> %{url_effective}' --max-time 20 https://www.ult-orb.com/)"
  echo
  echo "== TLS =="
  # The certificate is the thing most likely to break: WordPress.com issues
  # and renews it against the domain, and that machinery assumes it controls
  # the records it is validated through.
  echo | openssl s_client -connect ult-orb.com:443 -servername ult-orb.com 2>/dev/null \
    | openssl x509 -noout -issuer -subject -dates 2>/dev/null | sed 's/^/   /'
}

if [ "${1:-}" = "--baseline" ]; then
  probe > "$BASE"
  echo "baseline written to $BASE"
  cat "$BASE"
  exit 0
fi

now=$(probe)
if [ ! -f "$BASE" ]; then
  echo "$now"
  echo
  echo "no baseline yet — run with --baseline BEFORE changing the nameservers"
  exit 0
fi
echo "$now" > /tmp/pub-now.txt
echo "=== what changed since the baseline ==="
if diff -u "$BASE" /tmp/pub-now.txt > /tmp/pub-diff.txt; then
  echo "   nothing. The publication is byte-for-byte as it was."
else
  # The NS line is SUPPOSED to change; everything else is a finding.
  sed -n '3,$p' /tmp/pub-diff.txt | sed 's/^/   /'
  echo
  echo "   NS changing is the migration. Anything else is a problem:"
  echo "   a different apex A, a lost SPF or DMARC, a non-200, a shorter"
  echo "   page, or an issuer that is no longer WordPress's."
fi
