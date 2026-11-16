"""Club colours for the interface, from data/manual/club_colours.csv (hand-maintained).

No crests or logos: they are trademarks and the repo is public. A club is shown as a colour
chip with its three-letter code.

The app is dark, so a dark club colour (navy, claret, black) needs help to stay visible:
  fill     the club's primary colour, used for chips and pitch cards
  outline  a light border drawn around a fill that is too dark to see on its own
  line     the colour for chart series: the primary if it is visible, otherwise the primary
           lightened until it is (keeps the club's hue; five clubs would otherwise all be white)
  ink      black or white text, whichever reads better on the fill
"""
from functools import lru_cache

import pandas as pd

from .config import ROOT

BACKGROUND = "#0B0F14"
LIGHT = "#E6EDF3"
MIN_CONTRAST = 3.0     # WCAG minimum for graphics and large text


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminance(hex_colour: str) -> float:
    def channel(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours: 1 (identical) to 21 (black on white)."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def lighten(hex_colour: str, background: str = BACKGROUND, target: float = MIN_CONTRAST) -> str:
    """Mix the colour with white in small steps until it reaches the target contrast."""
    r, g, b = _rgb(hex_colour)
    for step in range(0, 101, 5):
        k = step / 100
        mixed = "#{:02X}{:02X}{:02X}".format(*(round(v + (255 - v) * k) for v in (r, g, b)))
        if contrast(mixed, background) >= target:
            return mixed
    return "#FFFFFF"


@lru_cache
def club_colours() -> pd.DataFrame:
    """One row per club (index = three-letter code): primary, secondary, fill, outline, line, ink."""
    df = pd.read_csv(ROOT / "data" / "manual" / "club_colours.csv").set_index("team")
    visible = df.primary.map(lambda c: contrast(c, BACKGROUND) >= MIN_CONTRAST)
    df["fill"] = df.primary
    df["outline"] = ["" if ok else LIGHT for ok in visible]   # "" = no outline needed
    df["line"] = [c if ok else lighten(c) for c, ok in zip(df.primary, visible)]
    df["ink"] = df.fill.map(lambda c: "#000000" if contrast(c, "#000000") >= contrast(c, "#FFFFFF") else "#FFFFFF")
    df["chip_ink"] = df.line.map(lambda c: "#000000" if contrast(c, "#000000") >= contrast(c, "#FFFFFF") else "#FFFFFF")
    return df
