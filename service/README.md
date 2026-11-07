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

## What a LaunchAgent does NOT survive

**FileVault.** Nothing in a user session runs until that user logs in and
unlocks the disk, so after a reboot the site is down until George logs in. A
LaunchDaemon would start earlier — and would be useless, because Resolve
needs the desktop anyway. So: *the Mac must be logged in*, and that is a
property of driving Resolve, not of this plist.
