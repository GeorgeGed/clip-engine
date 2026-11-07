#!/usr/bin/env python3
"""A stand-in control plane, so the contract is PROVEN before it is built.

    ./.venv/bin/python worker/mock_control_plane.py --job fns-2905408276 --stages report
    CLIP_WORKER_URL=http://127.0.0.1:8899 CLIP_WORKER_TOKEN=test \
        ./.venv/bin/python worker/agent.py --once

WHY THIS EXISTS. `worker/backend.py` describes six HTTP calls and had never
made one of them against anything. Building a cloud app to that description
and THEN discovering the shapes are wrong is the expensive order. This
implements the six endpoints in the stdlib, stores "uploads" in a temp
directory, and prints every call it receives — so a single real agent run
either proves the contract or names the field that is wrong.

It is not a product. It is the test harness the control plane has to pass.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "jobs" / "_mock-store"
CALLS: list[str] = []
STATE: dict = {}


def log(what: str, detail: str = "") -> None:
    line = f"  {what:<14} {detail}"
    CALLS.append(what)
    print(line, flush=True)


class H(BaseHTTPRequestHandler):
    # HTTP/1.0 ON PURPOSE, unlike the real site. At 1.1 the agent's
    # connection stays open after the last call and `handle_request()`
    # blocks on it forever, so the harness never reaches its own verdict.
    # A test rig that cannot print its result is worse than none.
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth_ok(self) -> bool:
        want = f"Bearer {STATE['token']}"
        return self.headers.get("Authorization") == want

    def do_PUT(self):                                     # noqa: N802
        # Stands in for object storage. A real signed PUT carries its
        # authorisation in the URL, so there is no bearer header here —
        # which is exactly why upload-url is a separate call.
        n = int(self.headers.get("Content-Length") or 0)
        name = self.path.rsplit("/", 1)[-1].split("?")[0]
        STORE.mkdir(parents=True, exist_ok=True)
        dest = STORE / name
        remaining, h = n, dest.open("wb")
        while remaining > 0:
            chunk = self.rfile.read(min(1 << 20, remaining))
            if not chunk:
                break
            h.write(chunk)
            remaining -= len(chunk)
        h.close()
        got = dest.stat().st_size
        log("PUT", f"{name}  {got/1e6:.1f} MB"
                   + ("" if got == n else f"  !! expected {n}"))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):                                    # noqa: N802
        route = self.path.strip("/").rsplit("/", 1)[-1]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if not self._auth_ok():
            log("UNAUTHORISED", route)
            return self._json({"error": "bad token"}, 401)

        if route == "claim":
            if STATE["handed_out"]:
                log("claim", "-> null (nothing queued)")
                return self._json({"job": None})
            STATE["handed_out"] = True
            caps = body.get("caps") or {}
            log("claim", f"worker={body.get('worker')} resolve={caps.get('resolve')}")
            return self._json({"job": {
                "id": "mock-job-1",
                "name": STATE["job"],
                "url": STATE["url"],
                "rights": "explicit",
                "stages": STATE["stages"],
                "note": "exercised by mock_control_plane.py",
                "extra": [],
                # Handed DOWN, and deliberately identical to what is on
                # disk: this is a round-trip identity test, so a bug in
                # write_specs cannot destroy a reviewed spec.
                "specs": STATE["send_specs"],
            }})

        if route == "stage":
            log("stage_state", f"{body.get('stage')} -> {body.get('state')}"
                               + (f" (exit {body['code']})"
                                  if body.get("code") is not None else ""))
            return self._json({})

        if route == "heartbeat":
            p = body.get("progress") or {}
            log("heartbeat", f"{body.get('stage')}  {str(p)[:90]}")
            return self._json({"cancelled": False})

        if route == "upload-url":
            name = body.get("name", "file")
            log("upload-url", f"clip {body.get('clip')}  {name}  {body.get('type')}")
            return self._json({
                "url": f"http://127.0.0.1:{STATE['port']}/upload/{name}?sig=mock",
                "public": f"https://storage.example/{STATE['job']}/{name}",
            })

        if route == "artifact":
            kind, idx = body.get("kind"), body.get("idx")
            data = body.get("data")
            size = (len(data) if isinstance(data, list)
                    else len(data or {}) if isinstance(data, dict) else 0)
            log("artifact", f"{kind}"
                            + (f"[{idx}]" if idx is not None else "")
                            + (f"  {size} field(s)/row(s)" if size else "")
                            + (f"  url={body.get('url')[:48]}" if body.get("url") else ""))
            STATE["artifacts"].setdefault(kind, {})[idx] = data or body.get("url")
            return self._json({})

        if route == "clip":
            meta = body.get("meta") or {}
            idx = body.get("clip")
            # THE PRIMARY KEY IS (job, idx). Enforce it here, because
            # Postgres will, and a mock that accepts what the real thing
            # rejects is worse than no mock.
            if any(c.get("clip") == idx for c in STATE["clips"]):
                log("DUPLICATE CLIP", f"idx={idx} already recorded — in "
                                      f"Postgres this is a PK violation")
                return self._json({"error": f"clip {idx} already exists"}, 409)
            log("clip", f"idx={idx} bytes={meta.get('bytes')} "
                        f"sidecar={'yes' if meta.get('sidecar_url') else 'no'} "
                        f"-> {body.get('url')}")
            STATE["clips"].append(body)
            return self._json({})

        if route == "finish":
            log("finish", f"state={body.get('state')} "
                          f"manifest_keys={len(body.get('manifest') or {})}")
            STATE["finished"] = body.get("state")
            return self._json({})

        if route == "health":
            h = body.get("health") or {}
            log("health", f"{body.get('worker')} resolve={h.get('resolve')} "
                          f"host={h.get('host')}")
            return self._json({})

        log("UNKNOWN ROUTE", route)
        return self._json({"error": f"no route {route}"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="fns-2905408276")
    ap.add_argument("--url", default="https://www.twitch.tv/videos/2905408276")
    ap.add_argument("--stages", default="report",
                    help="comma-separated; 'report' is quick and still "
                         "exercises the whole call sequence")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--token", default="test")
    a = ap.parse_args()

    # Read the real specs off disk and hand those exact objects down, so
    # the agent writing them back can only ever be a no-op.
    chan = a.job.split("-")[0]
    send = {}
    for sp in sorted((ROOT / "clips").glob(f"{chan}-*.json")):
        send[str(int(sp.stem.rsplit("-", 1)[-1]))] = json.loads(sp.read_text())

    STATE.update(job=a.job, url=a.url, stages=a.stages.split(","),
                 port=a.port, token=a.token, handed_out=False,
                 clips=[], finished=None, artifacts={}, send_specs=send,
                 before={p.name: p.read_bytes()
                         for p in (ROOT / "clips").glob(f"{chan}-*.json")})

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    srv.request_queue_size = 64
    print(f"mock control plane on http://127.0.0.1:{a.port}")
    print(f"  will hand out {a.job!r}, stages {STATE['stages']}")
    print(f"  uploads land in {STORE}")
    print("  calls received:", flush=True)
    # THE TIMEOUT GOES ON BEFORE THE LOOP, NOT AFTER IT. This is a
    # ThreadingHTTPServer, so `finish` is handled in a worker thread and
    # sets STATE["finished"] there — while the main thread is already
    # blocked inside handle_request() with no timeout, waiting for a
    # connection that will never come. The loop condition is only tested
    # BETWEEN calls, so the harness ran to completion and then hung
    # forever without printing its own verdict.
    srv.timeout = 0.5
    try:
        deadline = time.time() + 600
        while STATE["finished"] is None and time.time() < deadline:
            srv.handle_request()          # returns every 0.5s either way
        for _ in range(4):                # drain anything sent after finish
            srv.handle_request()
    except KeyboardInterrupt:
        pass

    print("\n  --- what the contract exercised ---", flush=True)
    for c in ("health", "claim", "stage_state", "heartbeat",
              "upload-url", "PUT", "clip", "finish", "DUPLICATE CLIP"):
        hit = CALLS.count(c)
        print(f"  {'OK ' if hit else '!! '}{c:<14} {hit}", flush=True)
    missing = [c for c in ("health", "claim", "stage_state", "upload-url",
                           "PUT", "clip", "finish") if c not in CALLS]
    print(f"\n  finished: {STATE['finished']}, clips recorded: {len(STATE['clips'])}", flush=True)
    for kind, got in STATE["artifacts"].items():
        print(f"  artifact  {kind:<12} {len(got)}", flush=True)
    # THE SAFETY ASSERTION: handing specs down must not alter them.
    chan = STATE["job"].split("-")[0]
    after = {p.name: p.read_bytes() for p in (ROOT / "clips").glob(f"{chan}-*.json")}
    changed = [n for n in STATE["before"] if after.get(n) != STATE["before"][n]]
    gone = [n for n in STATE["before"] if n not in after]
    if changed or gone:
        print(f"  !! SPECS ALTERED: changed={changed} missing={gone}", flush=True)
        return 1
    print(f"  OK  {len(after)} spec(s) on disk, byte-identical after the round trip", flush=True)
    if missing:
        print(f"  NOT EXERCISED: {', '.join(missing)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
