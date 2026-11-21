"""Chat badges ship with the repo, and a missing one never costs a clip.

v18 was deployed from a fresh checkout. badgemap.json was committed but the
PNGs it names were gitignored, so the image had none, and the first badged
chat message would have crashed the build.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import chat_native as cn  # noqa: E402


def test_every_mapped_badge_is_in_the_repo():
    badges = json.loads((cn.PUBLIC / "badgemap.json").read_text())
    missing = [p for p in badges.values() if not (cn.PUBLIC / p).exists()]
    assert not missing, missing


def test_a_missing_badge_file_costs_only_the_badge(tmp_path):
    m = {"author": "viewer", "badges": ["gone/1"], "frags": [{"text": "hi"}], "t": 0}
    im = cn._message(m, bold=cn._font(700), regular=cn._font(500),
                     badges={"gone/1": "badges/not-here.png"}, emotes=tmp_path)
    assert im.width > 0
