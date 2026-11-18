"""engine.caption_fonts: every font loads, and the web app offers the same set."""
import re
from pathlib import Path

from engine import caption_fonts as cf

ROOT = Path(__file__).resolve().parent.parent


def test_every_font_file_loads_and_draws():
    for k in cf.FONTS:
        f = cf.face(k, 92)
        l, t, r, b = f.getbbox("that was INSANE")
        assert r - l > 300 and b - t > 40, k


def test_web_app_lists_the_same_fonts():
    ts = (ROOT / "webapp/src/fonts.ts").read_text()
    web = re.findall(r'\{ key: "(\w+)", label: "([^"]+)" \}', ts)
    assert web == [(k, v[0]) for k, v in cf.FONTS.items()]
    assert f'DEFAULT_CAPTION_FONT = "{cf.DEFAULT}"' in ts


def test_web_app_has_a_preview_for_every_font():
    ts = (ROOT / "webapp/src/fontPreviews.ts").read_text()
    assert re.findall(r'^  (\w+): \{ stroke: "', ts, re.M) == list(cf.FONTS)


def test_unknown_font_falls_back_to_the_default():
    assert cf.key("comic-sans") == cf.DEFAULT
    assert cf.key(None) == cf.DEFAULT
    assert cf.key("anton") == "anton"
