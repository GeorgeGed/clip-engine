"""engine/finish: the stamp's freeze and the cold open, on a synthetic clip."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import finish  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
W, H, TOP = 108, 192, 76


def _clip(tmp: Path) -> Path:
    src = tmp / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r=30:d=4",
                    "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    return src


def _frame(path: Path, n: int) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{n})",
                           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout


def _rows(b: bytes, y0: int, y1: int) -> bytes:
    return b[y0 * W * 3:y1 * W * 3]


def test_the_stamp_freezes_and_greys_only_the_lower_pane(tmp_path):
    src = _clip(tmp_path)
    out, still = tmp_path / "frz.mp4", tmp_path / "pane.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex",
                    finish.still_graph("0:v", "s", frame=30, top=TOP, height=H - TOP, width=W),
                    "-map", "[s]", "-frames:v", "1", str(still)], check=True)
    g = finish.hold_graph("0:v", "o", still=still, first=30, frames=36, top=TOP, fps=30)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", g,
                    "-map", "[o]", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", str(out)],
                   check=True)
    before, a, b, after = _frame(out, 29), _frame(out, 30), _frame(out, 65), _frame(out, 66)
    lower = _rows(a, TOP + 4, H)
    assert lower == _rows(b, TOP + 4, H)                       # held
    assert _rows(a, 0, TOP - 4) != _rows(b, 0, TOP - 4)        # the top keeps playing
    px = [lower[i:i + 3] for i in range(0, len(lower), 3)]
    assert max(max(p) - min(p) for p in px) <= 6               # grey
    assert _rows(after, TOP + 4, H) != lower                   # and it lets go
    assert _rows(before, TOP + 4, H) != lower                  # on its own frame


def test_the_cold_open_plays_the_tease_then_the_whole_clip(tmp_path):
    src = _clip(tmp_path)
    out = tmp_path / "cold.mp4"
    tease = finish.cold_open(src, out, start=2.0, end=3.0, fps=30)
    assert tease == pytest.approx(1.0)
    assert finish.duration(out) == pytest.approx(5.0, abs=0.05)
    def close(x, y):
        return sum(abs(p - q) for p, q in zip(x, y)) / len(x) < 4
    assert close(_frame(out, 0), _frame(src, 60))
    assert close(_frame(out, 30), _frame(src, 0))


def test_cards_shift_behind_the_tease():
    cards = [{"start": 0.5, "end": 1.0, "text": "A"}, {"start": 2.2, "end": 3.4, "text": "B"}]
    got = finish.shift_cards(cards, start=2.0, end=3.0)
    assert [(c["text"], round(c["start"], 2), round(c["end"], 2)) for c in got] == [
        ("B", 0.2, 1.0), ("A", 1.5, 2.0), ("B", 3.2, 4.4)]


def test_an_overlay_can_be_hidden_for_a_window():
    from engine import native_composite as nc
    g, _files = nc.video_graph("base", [nc.Overlay(Path("chat.mov"), 0.0, dur=10.0, track=3,
                                                   hide=(4.0, 5.2))], fps=60)
    assert "enable='between(t,0.000,10.000)*not(between(t,4.000,5.200))'" in g
