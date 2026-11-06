#!/usr/bin/env python3
"""Assemble web/static/index.html from shell.html + body.html."""
from pathlib import Path
W = Path(__file__).resolve().parent / "static"
html = (W / "shell.html").read_text() + "\n" + (W / "body.html").read_text()
html += '\n<script src="/app.js"></script>\n'
(W / "index.html").write_text(
    '<!doctype html>\n<html lang="en"><head>\n'
    + html.split("<style>")[0]
    + "\n</head><body>\n" + html[html.index("<style>"):] + "\n</body></html>\n")
print(f"index.html  {(W / 'index.html').stat().st_size / 1024:.0f} KB")
