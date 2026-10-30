"""Asserts the in-point walk only fires on real dead air, and lands on speech.

The threshold here is measured, not chosen: across 50 clips from FNS VOD
2905408276, leading silence splits into a natural 0.24-0.63s breath (14 clips,
median 0.42s) and a dead-air tail at 1.87s and up (6 clips), with a 1.24s gap
between. An earlier 0.35s guess flagged 13 and was wrong about 7 of them.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import boundaries as b
from engine import qc

fails: list[str] = []


def ok(name: str, cond: bool) -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def run() -> int:
    print("the natural band is left alone")
    for lead in (0.0, 0.24, 0.42, 0.63, 0.99):
        new, why = b.walk_in_point_to_speech(1000.0, lead)
        ok(f"{lead:.2f}s lead unchanged", new == 1000.0)

    print("dead air is walked forward")
    for lead, want in ((1.87, 1001.57), (4.36, 1004.06), (17.63, 1017.33)):
        new, why = b.walk_in_point_to_speech(1000.0, lead)
        ok(f"{lead:.2f}s lead walked to +{want - 1000:.2f}s",
           abs(new - want) < 1e-6)
    ok("walk explains itself",
       "dead air" in b.walk_in_point_to_speech(1000.0, 5.0)[1])

    print("the walk only ever moves forward")
    news = [b.walk_in_point_to_speech(1000.0, l)[0] for l in
            (0, 0.5, 1.0, 2.0, 10.0, 100.0)]
    ok("never earlier than the original", all(n >= 1000.0 for n in news))
    ok("monotonic in lead length", news == sorted(news))

    print("preroll is preserved")
    new, _ = b.walk_in_point_to_speech(0.0, 10.0, preroll=0.3)
    ok("lands preroll before speech", abs((10.0 - new) - 0.3) < 1e-6)

    print("transcript cross-check")
    utt = [{"start": 100.0, "text": "first"}, {"start": 117.4, "text": "second"}]
    ok("finds speech just after the walked point",
       (b.speech_near(utt, 117.3) or {}).get("text") == "second")
    ok("finds speech just before, within tolerance",
       (b.speech_near(utt, 117.6) or {}).get("text") == "second")
    ok("no speech near a silent point", b.speech_near(utt, 150.0) is None)
    ok("window is respected", b.speech_near(utt, 115.0, window=0.5) is None)

    print("leading silence is measured from the file")
    tmp = Path(tempfile.mkdtemp(prefix="bnd-"))
    f = tmp / "lead3.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=navy:s=320x240:r=30:d=6",
         "-f", "lavfi", "-i",
         "aevalsrc=if(gt(t\\,3)\\,0.5*sin(2*PI*440*t)\\,0):d=6",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(f)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    lead = qc.leading_silence(f)
    ok(f"3s of head silence measured (got {lead:.2f})", abs(lead - 3.0) < 0.25)

    g = tmp / "nolead.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=navy:s=320x240:r=30:d=6",
         "-f", "lavfi", "-i", "sine=f=440:d=6",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(g)], capture_output=True, check=True)
    ok("a file opening on sound measures 0.0", qc.leading_silence(g) == 0.0)

    ok("qc and boundaries share one threshold",
       qc.LEAD_SILENCE_WARN_S == b.LEAD_SILENCE_DEFECT_S == 1.0)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for x in fails:
        print("  -", x)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
