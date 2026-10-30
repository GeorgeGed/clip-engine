"""Each test asserts that one defect in a RENDERED file is actually caught.

Fixtures are synthetic on purpose. This suite tests the measurement code — that
ffprobe/ffmpeg output is parsed correctly and the thresholds fire — not
editorial judgement, which no synthetic clip can stand in for.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import qc

fails: list[str] = []


def ok(name: str, cond: bool) -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def _ff(args: list[str], out: Path) -> Path:
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        *args, str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"fixture build failed: {r.stderr.strip()[:300]}")
    return out


def vertical(d: Path, *, dur: float = 6.0, vol: str = "0.1",
            size: str = "1080x1920") -> Path:
    """Navy frame plus a sine, at `vol` (a volume-filter value, linear or dB).

    Measured: ffmpeg's `sine` source lands at about -21.8 LUFS / -18.1 dBTP,
    NOT full scale. So a clipping fixture needs roughly +20dB, and `volume=1.0`
    is nowhere near the ceiling.
    """
    safe = vol.replace(".", "p")
    return _ff(["-f", "lavfi", "-i", f"color=c=navy:s={size}:r=60:d={dur}",
                "-f", "lavfi", "-i", f"sine=f=440:d={dur}",
                "-af", f"volume={vol}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest"], d / f"v_{size}_{safe}_{dur}.mp4")


def gapped(d: Path, *, silent_until: float = 3.0, dur: float = 8.0) -> Path:
    """Video with TRUE digital silence for the first `silent_until` seconds.

    Encoded to AAC on purpose: that is what a real clip is, and AAC's lossy
    decode turns exact zeros into about -122 dBFS, which is why the detector
    uses a dB floor rather than equality with zero.
    """
    expr = f"if(gt(t\\,{silent_until})\\,0.5*sin(2*PI*440*t)\\,0)"
    return _ff(["-f", "lavfi", "-i", f"color=c=navy:s=1080x1920:r=60:d={dur}",
                "-f", "lavfi", "-i", f"aevalsrc={expr}:d={dur}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest"], d / f"gap_{silent_until}_{dur}.mp4")


def run() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="qc-fixtures-"))

    print("file-level")
    ok("missing file rejected", not qc.check(tmp / "nope.mp4").passed)
    empty = tmp / "empty.mp4"
    empty.write_bytes(b"")
    r = qc.check(empty)
    ok("zero bytes rejected", not r.passed and any("zero" in x for x in r.rejected))

    print("container")
    good = vertical(tmp)
    r = qc.check(good)
    ok("1080x1920 accepted as canvas", not any("canvas" in x for x in r.rejected))
    ok("duration measured", r.measured["duration"] is not None
       and abs(r.measured["duration"] - 6.0) < 0.3)
    ok("fps measured", r.measured["fps"] == 60.0)

    wrong = vertical(tmp, size="1280x720")
    r = qc.check(wrong)
    ok("wrong canvas rejected", not r.passed and any("canvas" in x for x in r.rejected))
    r = qc.check(wrong, expect_canvas=False)
    ok("raw cut exempt from canvas check", not any("canvas" in x for x in r.rejected))

    print("audio presence")
    mute = _ff(["-f", "lavfi", "-i", "color=c=navy:s=1080x1920:r=60:d=6",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"],
               tmp / "noaudio.mp4")
    r = qc.check(mute)
    ok("dropped audio track rejected",
       not r.passed and any("audio" in x for x in r.rejected))

    silent = _ff(["-f", "lavfi", "-i", "color=c=navy:s=1080x1920:r=60:d=6",
                  "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-shortest"], tmp / "silent.mp4")
    r = qc.check(silent)
    ok("silent audio rejected", not r.passed and any("silent" in x for x in r.rejected))

    print("loudness")
    hot = vertical(tmp, vol="20dB")
    r = qc.check(hot)
    ok("clipping master rejected",
       not r.passed and any("true peak" in x for x in r.rejected))
    ok("true peak measured above ceiling",
       r.measured["true_peak"] is not None
       and r.measured["true_peak"] > qc.gates.TRUE_PEAK_CEILING)
    r = qc.check(good)
    ok("quiet master warns, does not reject",
       r.passed and any("LUFS" in w for w in r.warnings))

    print("duration against the plan")
    r = qc.check(good, edit={"range": {"in": 0.0, "out": 6.0}})
    ok("matching plan has no drift reject",
       not any("drift" in x for x in r.rejected))
    r = qc.check(good, edit={"range": {"in": 0.0, "out": 20.0}})
    ok("plan/render mismatch rejected",
       not r.passed and any("drift" in x for x in r.rejected))

    print("absolute duration")
    short = vertical(tmp, dur=2.0)
    r = qc.check(short)
    ok("under 5s rejected", not r.passed and any("absolute" in x for x in r.rejected))

    print("planned duration maths")
    d = qc._planned_duration({"segments": [{"in": 0.0, "out": 10.0, "speed": 2.0}],
                              "source": {"fps": 60}, "tail_frames": 60})
    ok("speed and tail folded in", d is not None and abs(d - 6.0) < 1e-6)
    d = qc._planned_duration({"segments": [{"in": 0.0, "out": 4.0, "speed": 1.0},
                                           {"in": 10.0, "out": 16.0, "speed": 1.0}]})
    ok("segment spans summed, gap excluded", d is not None and abs(d - 10.0) < 1e-6)
    ok("no segments and no range is unknown", qc._planned_duration({}) is None)

    print("absent audio is not the same as quiet audio")
    g = gapped(tmp, silent_until=3.0, dur=8.0)
    dead = qc.dead_audio(g)
    ok("finds the absent run", len(dead["runs"]) >= 1)
    ok(f"run is ~3s (got {dead['total']:.2f})", abs(dead["total"] - 3.0) < 0.35)
    ok(f"fraction is ~0.375 (got {dead['fraction']:.3f})",
       abs(dead["fraction"] - 0.375) < 0.06)
    r = qc.check(g)
    ok("opening on absent audio rejects",
       not r.passed and any("absent audio" in x for x in r.rejected))
    ok("warning names the run count",
       any("absent, not quiet" in w for w in r.warnings))

    quiet = vertical(tmp, vol="-60dB")
    d2 = qc.dead_audio(quiet)
    ok("quiet audio is NOT reported absent", d2["runs"] == [])
    ok("a quiet file still passes", qc.check(quiet).passed)

    full = vertical(tmp)
    ok("audio throughout reports no absent runs", qc.dead_audio(full)["runs"] == [])

    ok("min_run filters short runs",
       qc.dead_audio(g, min_run=10.0)["runs"] == [])
    ok("floor is -90 dBFS", qc.DEAD_AUDIO_FLOOR_DB == -90.0)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
