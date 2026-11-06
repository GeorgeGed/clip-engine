#!/usr/bin/env python3
"""Concatenate the prototype's parts and inline its data."""
from pathlib import Path

P = Path(__file__).resolve().parent
PARTS = ("a-head.html", "a-css1.html", "a-css2.html", "a-css3.html", "a-body.html")

html = "\n".join((P / f).read_text() for f in PARTS)
html += ('\n<script id="factory-data" type="application/json">'
         + (P / "factory.json").read_text() + "</script>\n")
html += ('<script>window.__FACTORY__=JSON.parse('
         "document.getElementById('factory-data').textContent);</script>\n")
html += "<script>\n" + (P / "a-app.js").read_text() + "\n</script>\n"
(P / "clip-factory.html").write_text(html)
print(f"clip-factory.html  {len(html)/1024:.0f} KB")
