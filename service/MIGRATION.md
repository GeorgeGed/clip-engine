# Moving ult-orb.com to Cloudflare, without touching the publication

`clips.ult-orb.com` needs the **whole zone** on Cloudflare's nameservers,
and WordPress.com's own DNS editor accepting arbitrary CNAMEs does not get
round it. That was worth testing rather than asserting, because if it had
worked the publication would never need to be touched.

**Measured.** A tunnel hostname resolves to Cloudflare's ordinary anycast
IPs — our own quick tunnel answers on `104.16.230.132` — so the obvious idea
is to point `clips` at those from WordPress's DNS and let the edge sort it
out by Host header. Against that same IP:

| SNI | result |
|---|---|
| `…trycloudflare.com` (a hostname Cloudflare hosts) | **401** — our own key page. Routed. |
| `clips.ult-orb.com` (one it does not) | **TLS alert 40, no peer certificate** |

The edge will not complete a handshake for a name that is not in a zone it
serves, so there is nothing for a foreign CNAME or A record to reach. The
zone has to be on Cloudflare. There is no partial setup on the free plan.

So this moves DNS for **Ult Orb, a live publication**, for the sake of an
internal tool. That asymmetry sets the rule for the whole procedure:

> **The publication's traffic must not change at all. Cloudflare answers
> DNS and nothing else.**

## The zone, in full. It is four records.

Captured from WordPress's own nameservers before anything moved
(`service/dns-backup/`):

| name | type | value | proxy |
|---|---|---|---|
| `ult-orb.com` | A | `192.0.78.206` | **DNS only** |
| `ult-orb.com` | A | `192.0.78.156` | **DNS only** |
| `ult-orb.com` | TXT | `v=spf1 include:_spf.wpcloud.com ~all` | — |
| `www` | CNAME | `ult-orb.com` | **DNS only** |
| `_dmarc` | TXT | `v=DMARC1;p=none;` | — |

No MX: nothing sends mail from this domain. Good — that is the part of a
migration that usually goes wrong, and it is absent.

## GREY CLOUD, NOT ORANGE — and the reason is a delayed failure

Cloudflare's import turns the proxy **on** by default. For every record
above it must be **off** ("DNS only", grey). Proxying would put Cloudflare
in the path of the publication, which is the one thing this must not do, and
it breaks something that will not show up for weeks:

**The certificate is Automattic's, and it renews in January.** Measured on
the live site: `issuer=Google Trust Services CN=WR1`,
`subject=CN=tls.automattic.com`, valid to **14 Jan 2027**. It is a shared
WordPress.com certificate, renewed by their machinery, validated by reaching
*their* servers over the domain. Proxy the record and the renewal
validation lands on Cloudflare instead. The site keeps working — until
January, when the certificate expires and the publication goes down with a
TLS error, months after the change that caused it and with nothing to
connect the two.

Grey cloud means Cloudflare hands out the same two IPs WordPress always
handed out and takes no part in the traffic. Only `clips` is proxied,
because the tunnel requires it.

## NO CAA RECORDS. This is the other delayed failure.

WordPress.com's SSL troubleshooting names it outright: *"CAA DNS records
error: This domain has CAA DNS records that do not allow Let's Encrypt to
issue a certificate."*

A CAA record says which certificate authorities may issue for a domain. The
zone has **none today** — checked, the apex returns nothing for CAA — which
means any CA may issue, which is what lets Automattic renew. Add CAA records
that name only Cloudflare's CAs and Let's Encrypt is locked out, and the
publication's certificate fails at its next renewal rather than at the
change. Same shape as the proxy problem and the same January.

So: **do not add CAA records.** If something adds them, they must include
`letsencrypt.org`. `check-publication.sh` asserts this on every run.

The other named failure, *"mixed name servers"*, only happens on a partial
switch — replace all three WordPress nameservers, not some.

## Steps

**1. Baseline the publication.** Already done — `./service/check-publication.sh --baseline`.

**2. Add the zone.** dash.cloudflare.com → Add a site → `ult-orb.com` → Free.
It scans and imports. **Check all five records are there, and set every one
to DNS only.** Add nothing yet.

**3. Change the nameservers at WordPress.com.** Allowed, and their own guide
even uses Cloudflare as the example. The domain is registered with Automattic
(`clientTransferProhibited` — that lock blocks a *registrar transfer*, not a
nameserver change, so it is not in the way). Exact path, from their docs:

> my.wordpress.com/domains → click **ult-orb.com** → under **Settings**,
> **Name servers** → toggle **Use WordPress.com name servers** OFF → enter
> Cloudflare's two → **Save**

Their docs are explicit that registration does not move and you keep paying
Automattic. They are **silent** on whether their SSL renewal keeps working
with external DNS — which is why steps 1 and 5 exist, and why the records
stay grey.

**4. Wait.** Usually minutes to a couple of hours. Cloudflare emails when the
zone is active. Watch it:

    watch -n 30 'dig +short NS ult-orb.com'

**5. Check nothing broke** — the whole point of step 1:

    ./service/check-publication.sh

Only the NS line should differ. A changed apex A, a lost SPF or DMARC, a
non-200, a much shorter page, or an issuer that is not Google Trust
Services/Automattic is a problem, and the fix is to put the WordPress
nameservers back at step 3 — the records are in `service/dns-backup/`.

**6. Then the tunnel:**

    cloudflared tunnel login        # browser; pick ult-orb.com
    ./service/tunnel-setup.sh

## Backing out

Set the nameservers at WordPress.com back to `ns1/ns2/ns3.wordpress.com`.
The zone's own records never left WordPress — they are still there — so the
rollback is one field, and the only cost is DNS propagation.
