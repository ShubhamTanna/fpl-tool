"""Club colour file: every club present, valid colours, visible on the dark background."""
import re

import pandas as pd
import pytest

from fpl.colours import BACKGROUND, LIGHT, MIN_CONTRAST, club_colours, contrast
from fpl.ingest.cache import PROCESSED_DIR

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_contrast_formula():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast("#123456", "#123456") == pytest.approx(1.0)


def test_twenty_clubs_with_valid_hex():
    c = club_colours()
    assert len(c) == 20 and c.index.is_unique
    for col in ("primary", "secondary", "fill", "line", "ink", "chip_ink"):
        assert c[col].map(lambda v: bool(HEX.match(v))).all(), col


def test_file_covers_every_club_in_the_teams_table():
    path = PROCESSED_DIR / "teams.parquet"
    if not path.exists():
        pytest.skip("no processed data on disk")
    assert set(pd.read_parquet(path).short_name) == set(club_colours().index)


def test_every_club_is_visible_on_the_dark_background():
    for team, r in club_colours().iterrows():
        assert contrast(r.line, BACKGROUND) >= MIN_CONTRAST, f"{team} chart colour"
        edge = r.outline or r.fill                   # what separates a chip from the page
        assert contrast(edge, BACKGROUND) >= MIN_CONTRAST, f"{team} chip edge"
        assert contrast(r.ink, r.fill) >= 4.5, f"{team} text on chip"
        assert contrast(r.chip_ink, r.line) >= 4.5, f"{team} text on table chip"


def test_dark_clubs_get_an_outline():
    c = club_colours()
    assert c.outline["TOT"] == LIGHT and c.outline["NEW"] == LIGHT
    assert c.outline["ARS"] == "" and c.line["ARS"] == c.primary["ARS"]
