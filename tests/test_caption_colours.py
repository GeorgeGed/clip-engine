"""The web app offers exactly engine.caption_colour's palette, and every entry is legible."""
import re
from pathlib import Path

from engine import caption_colour as cc
from pipeline.core import STYLE

TS = Path(__file__).resolve().parent.parent / "webapp/src/captionColours.ts"


def test_webapp_palette_matches_engine():
    src = TS.read_text()
    web = dict(re.findall(r'key: "(\w+)", label: "[^"]+", hex: "(#[0-9A-F]{6})"', src))
    assert web == {k: v.upper() for k, v in cc.PALETTE.items()}
    assert f'DEFAULT_CAPTION_FILL = "{STYLE["caption_fill"]}"' in src
    assert f'DEFAULT_CAPTION_EMPH = "{STYLE["caption_emph"]}"' in src


def test_every_colour_clears_the_floor():
    assert cc.check() == []
