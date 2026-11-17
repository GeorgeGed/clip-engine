"""WCAG relative luminance and contrast ratio, the one implementation the project uses."""
import colorsys

PANEL_BG = (0x18, 0x18, 0x1B)
CONTRAST_FLOOR = 4.5


def rel_luminance(rgb) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b) -> float:
    la, lb = rel_luminance(a), rel_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def readable(hex_colour, bg=PANEL_BG, floor=CONTRAST_FLOOR):
    """`hex_colour` with its lightness raised until it clears `floor` on `bg`."""
    s = hex_colour.lstrip("#")
    rgb = [int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    if ratio([v * 255 for v in rgb], bg) >= floor:
        return hex_colour.upper()
    h, l, sat = colorsys.rgb_to_hls(*rgb)
    if sat < 0.02:
        sat = 0.0                      # a grey has no hue to preserve
    lo, hi = l, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        out = [v * 255 for v in colorsys.hls_to_rgb(h, mid, sat)]
        if ratio(out, bg) < floor:
            lo = mid
        else:
            hi = mid
    out = [v * 255 for v in colorsys.hls_to_rgb(h, hi, sat)]
    return "#%02X%02X%02X" % tuple(int(round(v)) for v in out)
