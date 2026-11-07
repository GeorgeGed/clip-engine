# Step 7: real auth on the permanent hostname

Do this after `clips.ult-orb.com` answers. It cannot be done sooner — an
Access application needs a hostname in a zone on the account, and cannot
attach to a `trycloudflare.com` name.

## Why the shared key stops being enough at a permanent address

Not because one person needs SSO. Because **the hostname stops being
obscure the moment it exists.**

Every public HTTPS hostname needs a certificate, and every certificate is
appended to Certificate Transparency logs, which are public, permanent and
machine-readable. Cloudflare's Universal SSL issues **per-hostname**
certificates, not wildcards — checked against live certs, not docs — so
`clips.ult-orb.com` is published to a feed anyone can stream, within minutes
of it working, forever. Scanners read those feeds. A random
`trycloudflare.com` name was obscure in a way this is not.

A 190-bit key still is not guessable. What changes is everything else: a
bearer secret has no identity, no revocation short of rotating it for
everyone, no log of who opened what, and it leaks the ordinary way — a
pasted URL, a screenshot of a terminal, shell history.

## It is free, and Range survives it — measured, not assumed

Zero Trust Free: **$0 forever, 50 users**, ZTNA included, one-time-PIN and
Google both inside the tier. One person is 1 of 50. A seat is consumed on
authentication and freed by removing the user, not by revoking.

The question that mattered was whether putting Access in front breaks video,
since the editor plays clips out of 206 responses. It does not, and this was
tested rather than reasoned: a real 29.8 MB clip from `deliver/` served
through the edge gave **206 with correct Content-Range, a mid-file 2 MB
range byte-identical by sha256, and the whole 29.8 MB in 1.71 s at 110 ms
TTFB** with no stall. An echo origin confirmed the edge forwards `Range`,
the full `Cookie` header (`cf_key` and `CF_Authorization` together) and
`X-Clip-Key` unmodified — so **Access and our own key gate do not fight**,
and the key stays underneath as origin-side defence.

The mechanism backs the measurement: Cloudflare's phase list puts the Access
application check at request-phase row 14 and Cache Rules at row 18. Access
authorises and gets out of the way before anything touches the body.

## Setting it up

dash.cloudflare.com → Zero Trust → Access → Applications → **Add an
application** → **Self-hosted**.

| | |
|---|---|
| Application domain | `clips.ult-orb.com` |
| Session duration | 24 hours (the default if neither is set) |
| Policy | Action **Allow**, Include → **Emails** → his address |
| Identity | **One-time PIN** — no provider to configure |

SameSite must be **None** or **Lax**; Strict "can result in too many
redirects".

## The worker needs a service token, and the rules changed recently

A browser gets a cookie. `curl` and `worker/agent.py` cannot, so they use a
**service token** — `CF-Access-Client-Id` and `CF-Access-Client-Secret`
headers.

**Zero Trust organisations created on or after 2026-10-05 have strict
service token authentication on by default and cannot turn it off.** Under
it, *"Only Service Auth policies can authorize the request"* and *"Access
ignores Allow policies and any CF_Authorization cookie sent with the
request."* A new organisation is created the first time Zero Trust is set
up, so **this will apply.**

Practically: the application needs a **second policy**, action **Service
Auth**, Include → **Service Token**. An Allow policy will not let a token
through on its own.

## Two things that break video and are not in any config file

**HTTP/3.** A zone-level dashboard toggle, **on by default on Free**, and
the single documented cause of video playback failing through a Cloudflare
Tunnel (cloudflared issue #1519, open, no root cause, four independent
confirmations of the workaround). If clips stall or refuse to play once the
named tunnel is live and they played fine on the quick tunnel, turn it off
first: **Speed → Optimization → Protocol Optimization → HTTP/3 (with
QUIC)**. Nothing in `config.yml` affects this.

**Today's Range test proves less than it looks.** It was run through
`trycloudflare.com`, which returns `cf-cache-status: DYNAMIC` — *"not
eligible for cache, so the request went to the origin without a cache
lookup."* A real zone caches. Re-run the test on `clips.ult-orb.com` and
watch `cf-cache-status`: anything but `DYNAMIC` on a clip URL means a
rebuilt clip can serve stale bytes. The origin now sends
`Cache-Control: no-store` on 206s, which should keep it `DYNAMIC`.

    curl -sD - -o /dev/null -H 'X-Clip-Key: <key>' -H 'Range: bytes=0-1023' \
      https://clips.ult-orb.com/api/jobs/1/clip/12 \
      | grep -Ei 'HTTP/|content-range|cache-control|cf-cache-status'

## The one thing that is a business decision, not a technical one

Cloudflare's Service-Specific Terms, verbatim:

> *"Unless you are an Enterprise customer, Cloudflare offers specific Paid
> Services (e.g., the Developer Platform, Images, and Stream) that you must
> use in order to serve video and other large files via the CDN."*
> — cloudflare.com/service-specific-terms-application-services/

This clip pipeline serves video through the CDN on a Free plan. The usual
escape — serve it from a grey-clouded subdomain — **is not available for a
tunnel**: a `cfargotunnel.com` target has no public A record, so the CNAME
must be proxied or it does not work at all.

How much this matters is about volume and whose name is on it. One person
reviewing their own clips is not what the clause is aimed at; an agency
delivering client video off it is closer. The outs, if it ever comes up, are
R2 or Stream for the clips, or Enterprise. **It is worth George knowing the
term exists before the tool becomes load-bearing for clients**, which is why
it is written down here rather than discovered later.

(A correction to an earlier claim in this file's research: this clause lives
in the Service-Specific Terms, **not** on Cloudflare's Tunnel routing page.
The terms are real; the claim about where they appear was not.)
