# Keeping it up

A stable URL is only half of it. The other half is that the thing behind the
URL is actually running — after a reboot, after the lid closes, after a
crash. That is what this directory is for.

Two services, and they are deliberately different kinds:

| | what | why that kind |
|---|---|---|
| `com.clipfactory.site.plist` | the Python site | a **LaunchAgent**, in George's GUI session, because the build stage drives Resolve's scripting API and that needs a logged-in desktop |
| the tunnel | `cloudflared` | installed by `cloudflared service install`, which is the vendor's own supported path |

## THE ONE THAT BITES: launchd does not give you Homebrew

A launchd job starts with `PATH=/usr/bin:/bin:/usr/sbin:/sbin`. Measured in
this repo, the pipeline shells out to **`ffmpeg` 43 times and `ffprobe` 9
times by bare name**, plus `yt-dlp`, `node` and `npx` — and every one of them
lives in `/opt/homebrew/bin` or `~/.local/bin`, neither of which is on that
PATH.

Run the site from a terminal and it works, because your shell profile put
Homebrew on PATH. Run the identical command from launchd and every thumbnail
and every build fails with a file-not-found that names ffmpeg. The plist sets
`PATH` explicitly for exactly this reason. **If you add a tool, add its
directory here too.**

## Install

    ./service/install.sh            # local only
    CLIP_FACTORY_TOKEN=… ./service/install.sh

Uninstall with `./service/uninstall.sh`. Logs land in `jobs/_service/`.

## IT DOES NOT SURVIVE A REBOOT. It survives a LOGIN.

Stated plainly because an earlier note here said "comes back by itself" and
that is false as this Mac is configured.

Apple: *"A user agent is essentially identical to a daemon, but is specific
to a given logged-in user and executes only while that user is logged in."*
A LaunchAgent in `gui/501` starts when George logs in, not when the machine
boots. Measured here: `sysadminctl -autologin status` → **"Automatic login
is OFF"**, and `autoLoginUser` is absent. So after a restart the Mac sits at
the login window with the site down and the hostname returning a Cloudflare
error.

**And a restart is scheduled, not hypothetical.** Also measured:
`AutomaticallyInstallMacOSUpdates = 1`, and `softwareupdate --list` has
**macOS 27.2 pending with `Action: restart`**. The machine will reboot on
Apple's schedule and stay down until somebody logs in.

Three ways out, in order of how much they ask:

1. **Turn on automatic login** — System Settings → Users & Groups →
   Automatic login. Needs the password, so it is George's to do. The Mac
   then boots to a logged-in desktop, which is the real cost: anyone with
   physical access has the session. On a Mac mini at his own desk with
   FileVault already off, that is a small step, not a new exposure.
   **Note `/etc/kcpassword` exists and is 395 days older than the current
   password** — a leftover from a previous enablement. Setting auto-login
   through System Settings rewrites it; setting `autoLoginUser` by script
   without the password would leave the stale key and log nobody in.
2. **Turn off automatic macOS updates**, so reboots only happen when he is
   there. Does not help with a power cut; `sudo pmset -a autorestart 1`
   does, and `pmset -g cap` confirms this Mac supports it.
3. **Accept it** and treat the URL as up-when-he-is. Honest, and fine if the
   people using it are him and whoever he is sitting with.

A LaunchDaemon would start before login and would be no use: the build stage
drives Resolve's scripting API, which needs a desktop. **The login
requirement belongs to Resolve, not to this plist** — nothing in the service
arrangement can remove it.

`./service/status.sh` reports all of this rather than assuming it.
