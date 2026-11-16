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


# ---------------------------------------------------------------- team, names, tables
from fpl.config import team_id  # noqa: E402
from fpl.ingest.team import load_team  # noqa: E402

IST = "Asia/Kolkata"


def next_gw() -> int:
    return gameweeks()[0]


def deadline_text() -> str:
    ev = table("events")
    d = ev.loc[ev.gw == next_gw(), "deadline_time"].iloc[0].tz_convert(IST)
    return f"GW{next_gw()} deadline: {d:%a %d %b, %H:%M} IST"


def data_stamp() -> float:
    """Changes whenever the data or projections on disk change. Used as a cache key."""
    return max((P / f"{n}.parquet").stat().st_mtime for n in ("players", "projections", "player_gw"))


@st.cache_data(show_spinner=False, ttl=3600)
def my_team(stamp: float) -> dict:
    """Shubham's team for the next gameweek, with transfers already made applied."""
    r = rules()
    return load_team(team_id(), table("players"), table("player_gw"), next_gw() - 1,
                     r.sell_fee, r.max_free_transfers)


def names() -> pd.Series:
    """player_id -> display name."""
    return table("players").set_index("player_id").web_name


def labels() -> dict[int, str]:
    """player_id -> 'Name (CLUB, POS, 5.5m)' for pickers."""
    p = table("players")
    return {i: f"{n} ({t}, {pos}, {c / 10:.1f}m)"
            for i, n, t, pos, c in zip(p.player_id, names().reindex(p.player_id), p.team, p.position, p.now_cost)}


def top1k() -> pd.Series:
    """player_id -> % of the scanned top managers who own him (0 if nobody does)."""
    return table("template").set_index("player_id").owned_pct


def top1k_caption() -> str:
    return (f"Top 1k % = share of the top {table('top_picks').entry.nunique():,} overall managers who owned "
            "the player when the template was last scanned (scripts/build_template.py).")


def breakdown(ids: list[int], gws: list[int], extra: dict | None = None) -> pd.DataFrame:
    """One row per player: fixtures, expected minutes, xP and every part of it, summed over `gws`."""
    d = proj()
    d = d[d.gw.isin(gws) & d.player_id.isin(ids)]
    agg = d.groupby("player_id").agg(opp=("opp", ", ".join), xmins=("xmins", "sum"), xp=("xp", "sum"),
                                     **{c: (c, "sum") for c in PARTS}).reindex(ids)
    p, own = table("players").set_index("player_id"), top1k()
    out = pd.DataFrame({"Player": names().reindex(ids).values, "Pos": p.position[ids].values,
                        "Club": p.team[ids].values, "Price": (p.now_cost[ids] / 10).values})
    for k, v in (extra or {}).items():
        out[k] = v
    out["Fixtures"] = agg.opp.values
    out["Top 1k %"] = own.reindex(ids).fillna(0).round(1).values
    out["xMins"] = agg.xmins.round(0).values
    out["xP"] = agg.xp.round(2).values
    for c, label in PARTS.items():
        out[label] = agg[c].round(2).values
    return out


def ticker_grid(value: str, best_high: bool, first: list[str] = ()):
    """Club x gameweek grid, coloured green (good) to red. Clubs in `first` are listed on top."""
    ticker = table("ticker")
    vals = ticker.pivot(index="team", columns="gw", values=value)
    text = ticker.assign(cell=ticker.opp + "  " + ticker[value].map("{:.2f}".format)).pivot(
        index="team", columns="gw", values="cell")
    order = vals.sum(axis=1).sort_values(ascending=not best_high).index
    order = [t for t in order if t in first] + [t for t in order if t not in first]
    vals, text = vals.loc[order], text.loc[order]
    lo, hi = vals.values.min(), vals.values.max()

    def colour(_):
        score = (vals - lo) / (hi - lo)              # 0..1, low to high
        good = score if best_high else 1 - score     # 1 = good fixture
        return good.map(lambda g: f"background-color: rgba({'46,160,67' if g >= 0.5 else '218,54,51'}, "
                                  f"{abs(g - 0.5) * 1.2:.2f})")

    text.columns = [f"GW{g}" for g in text.columns]
    vals.columns = text.columns
    text.insert(0, "Total", vals.sum(axis=1).round(2))
    text.insert(0, "Mine", ["yes" if t in first else "" for t in text.index])
    return text.style.apply(colour, axis=None, subset=list(vals.columns)).format({"Total": "{:.2f}"})


# ---------------------------------------------------------------- past gameweeks and auto-picks
from fpl import pipeline  # noqa: E402
from fpl.model.xp import project  # noqa: E402
from fpl.optimize.models import pick_team  # noqa: E402


def tables() -> dict:
    return {n: table(n) for n in pipeline.TABLES}


def finished_gws() -> list[int]:
    ev = table("events")
    return sorted(int(g) for g in ev.loc[ev.finished, "gw"])


@st.cache_data(show_spinner=False)
def past_proj(gw: int, stamp: float) -> pd.DataFrame:
    """xP for a finished gameweek as the model would have projected it beforehand: only matches
    before `gw` are used. Injury flags of the time are not available, so none are applied."""
    out, _ = project(tables(), as_of_gw=gw - 1, horizon=1, use_availability=False)
    return out


@st.cache_data(show_spinner=False)
def actual_points(stamp: float) -> pd.DataFrame:
    """Rows = players, columns = gameweeks, values = FPL points scored (0 if he had no match)."""
    return table("player_gw").pivot_table(index="player_id", columns="gw", values="total_points",
                                          aggfunc="sum", fill_value=0)


@st.cache_data(show_spinner=False)
def auto_pick(squad: tuple, gw: int, stamp: float) -> dict | None:
    """Best XI, bench order and captain for `squad` in `gw`, chosen by the optimizer's pick_team.

    For a finished gameweek the choice uses the projection made before it, and `actual` is what
    that XI scored with the captain doubled (no automatic substitutions, no chips)."""
    players, done = table("players"), gw in finished_gws()
    if not set(squad) <= set(players.player_id):
        return None                                   # a player has left the game
    res = pick_team(list(squad), past_proj(gw, stamp) if done else proj(), players, rules(), gw)
    res["actual"] = None
    if done:
        pts = actual_points(stamp)[gw].reindex(res["xi"]).fillna(0)
        res["actual"] = int(pts.sum() + pts[res["captain"]])
    return res
