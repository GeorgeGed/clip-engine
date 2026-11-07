# Getting the domain onto Cloudflare

The tunnel needs its hostname in a zone Cloudflare serves. **There is no way
round that**, and it was worth testing rather than asserting, because if a
foreign DNS provider could point at the tunnel nothing here would be needed.

**Measured.** A tunnel hostname resolves to Cloudflare's ordinary anycast
IPs — a quick tunnel of ours answered on `104.16.230.132` — so the obvious
idea is to point a `clips` record at those from any registrar and let the
edge sort it out by Host header. Against that same IP:

| SNI | result |
|---|---|
| a hostname Cloudflare hosts | **401** — our own key page. Routed. |
| one it does not | **TLS alert 40, no peer certificate** |

The edge will not complete a handshake for a name outside a zone it serves,
so there is nothing for a foreign CNAME or A record to reach.

## The easy path: register the domain AT Cloudflare

Cloudflare Registrar sells at cost — what the registry charges, no markup,
same price on renewal — and a domain registered there is **born on
Cloudflare's nameservers**. No migration, no propagation wait, nothing to
break. Roughly £8–10/yr for a .com.

That makes everything below unnecessary. Prefer it.

## The other path: bringing a domain you already own

Only if the domain is registered elsewhere and you want to keep it there.
Add the zone at dash.cloudflare.com → Add a domain, then change the
nameservers at the registrar. Four things learned doing this for real:

**1. CLOUDFLARE TURNS THE PROXY ON FOR EVERY IMPORTED RECORD.** Watched it
happen: a five-record import came back with all three proxiable records
orange. If the domain already serves a site, that puts Cloudflare in the
path of it, which is usually not what you want and can break the existing
host's certificate renewal — the validation stops reaching them. **Set
every pre-existing record to DNS only (grey).** Only the tunnel's own
hostname is proxied, because it has to be.

**2. "Enable Bot Preference Sync" is on by default and prepends the site's
robots.txt.** Another silent change to a site that was working fine. Off.

**3. A dialog on the way out pushes you to proxy something** — "… is not
fully protected". "I'll do this later" keeps everything grey.

**4. CAA records can lock the previous host out.** A CAA record names which
CAs may issue. If the existing host renews via Let's Encrypt and something
adds a CAA that does not name `letsencrypt.org`, renewal fails at the next
cycle — months later, with nothing connecting it to the change. Add none, or
include theirs.

**And back the zone up first.** Dump every record from the authoritative
nameservers before touching anything, and keep a probe that says whether the
existing site still resolves, still serves 200, and still has the same
certificate issuer. `service/ult-orb-not-used/` has a worked example of both
from the time this was nearly done against a live publication.

## Then

    cloudflared tunnel login        # browser; pick the zone
    echo clips.<your-domain> > service/HOST
    ./service/tunnel-setup.sh

---

## This project: clipengine.gg, and why it is the second path

**Cloudflare Registrar does not sell `.gg`.** Checked in the dashboard, not
assumed — searching `clipengine.gg` returns *"TLD is not supported:
clipengine.gg can't be registered because the '.gg' extension is not yet
supported."* So the easy path above is unavailable for this name and the
domain is registered elsewhere, then delegated.

**That is fine, and it is not the risky case.** Everything the section above
warns about — the proxy flipping on, robots.txt, CAA locking out a previous
CA — is about a domain with a LIVE SITE already on it. A newly registered
domain has nothing to break. The only record will be the tunnel's own, and
that one is supposed to be proxied.

Registrar prices read 2026-11-07:

| | registration | renewal |
|---|---|---|
| **Porkbun** | **$51.80** | **$51.80** — confirmed on the search page |
| Gandi | €85.50 | **€180.00/yr** |

Gandi's renewal is 2.1x its own registration and 3.5x Porkbun's. Porkbun's
listing reads "At Cost · $51.80 / year · renews at $51.80", so there is no
first-year teaser and the price holds. That is the one to use.

### The steps, once the domain exists

1. Register `clipengine.gg`. Porkbun unless the basket says otherwise.
2. dash.cloudflare.com -> Add a domain -> `clipengine.gg` -> **Free**.
   There is nothing to import, so there is nothing to grey out.
3. Cloudflare gives two nameservers. Set them at the registrar, replacing
   whatever it assigned.
4. `cloudflared tunnel login`, then `./service/tunnel-setup.sh`.
   `service/HOST` already says `clips.clipengine.gg`.
5. `service/ACCESS.md` for the auth in front.
