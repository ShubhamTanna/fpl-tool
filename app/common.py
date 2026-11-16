"""Shared loaders and display helpers for every page."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fpl.optimize.checker import check_lineup, check_squad  # noqa: E402
from fpl.optimize.models import build_squad  # noqa: E402
from fpl.optimize.rules import load_rules  # noqa: E402

P = ROOT / "data" / "processed"
PARTS = {"xp_app": "Appearance", "xp_goals": "Goals", "xp_assists": "Assists", "xp_cs": "Clean sheet",
         "xp_conceded": "Conceded", "xp_saves": "Saves", "xp_dc": "Def. contribution",
         "xp_bonus": "Bonus", "xp_cards": "Cards"}
POSITIONS = ["GKP", "DEF", "MID", "FWD"]

# The site's small-caps label style (mono, uppercase, muted) for widget and metric labels,
# its ruled page title, tabular figures, and ink text on red buttons. Everything else is
# set in .streamlit/config.toml.
CSS = """<style>
.stApp { font-variant-numeric: tabular-nums; }
[data-testid="stWidgetLabel"] p, [data-testid="stMetricLabel"] p {
  font: 500 11px "JetBrains Mono", ui-monospace, Menlo, monospace;
  text-transform: uppercase; letter-spacing: .06em; color: #5d5b56; }
h1 { border-bottom: 1.5px solid #121211; padding-bottom: .35rem; }
button[kind="primary"], button[kind="primary"] p { color: #121211; }
</style>"""


def apply_theme() -> None:
    st.html(CSS)


@st.cache_data(show_spinner=False)
def _table(name: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(P / f"{name}.parquet")


def table(name: str) -> pd.DataFrame:
    """A processed table. Re-read automatically when the file on disk changes."""
    return _table(name, (P / f"{name}.parquet").stat().st_mtime)


@st.cache_resource
def rules():
    return load_rules()


def proj() -> pd.DataFrame:
    """The projections every page uses."""
    return table("projections")


def gameweeks() -> list[int]:
    return sorted(int(g) for g in proj().gw.unique())


def xp_grid(gws: list[int]) -> pd.DataFrame:
    p = proj()
    return p[p.gw.isin(gws)].pivot(index="player_id", columns="gw", values="xp")


def player_rows(ids: list[int], gws: list[int], extra: dict | None = None) -> pd.DataFrame:
    """Display table for a list of players: name, position, club, price and xP per gameweek."""
    p, xp = table("players").set_index("player_id"), xp_grid(gws)
    df = pd.DataFrame({"Player": p.web_name[ids].values, "Pos": p.position[ids].values,
                       "Club": p.team[ids].values, "Price": (p.now_cost[ids] / 10).values})
    for k, v in (extra or {}).items():
        df[k] = v
    for g in gws:
        df[f"GW{g}"] = xp.loc[ids, g].round(2).values
    return df


def show(df: pd.DataFrame, **kw) -> None:
    st.dataframe(df, hide_index=True, width="stretch", **kw)


@st.cache_data(show_spinner=False)
def run_squad(horizon: int, budget: int):
    r, players = rules(), table("players")
    gws = gameweeks()[:horizon]
    res = build_squad(proj(), players, r, gws, budget=budget)
    errs = check_squad(res["squad"], players, r)
    for g in res["gws"]:
        errs += check_lineup(g["xi"], g["bench"], g["captain"], g["vice"], g["squad"], players, r)
    return res, errs
