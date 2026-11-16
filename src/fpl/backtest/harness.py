"""Backtest harness: replay any past gameweek and compare the projection with what happened.

replay_gw() projects one gameweek using only matches played before it, with the scoring
rules of that season, then attaches actual points. Injury flags are not used: nobody
publishes the flags that were showing before a past gameweek.

Seasons
  TUNE     dials are chosen on these
  HOLDOUT  looked at only to accept or reject a change
  LIVE     never used for tuning; it is the live check
"""
import numpy as np
import pandas as pd

from ..ingest.cache import PROCESSED_DIR
from ..model.dials import DIALS, Dials
from ..model.scoring import load_scoring, season_rules
from ..model.xp import RATE_STATS, project

TUNE = ["2023-24", "2024-25"]
HOLDOUT = "2025-26"
LIVE = "2026-27"
ALL_SEASONS = ["2022-23"] + TUNE + [HOLDOUT, LIVE]
PARTS = ["app", "goals", "assists", "cs", "conceded", "saves", "dc", "bonus", "cards"]
FIRST_GW = 2          # gameweek 1 has no matches before it
BUCKETS = [-np.inf, 1, 2, 3, 4, 5, 6, np.inf]
BUCKET_LABELS = ["<1", "1-2", "2-3", "3-4", "4-5", "5-6", "6+"]


def load_history() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / "history_gw.parquet")


def _actual_parts(h: pd.DataFrame, s: dict, thr: dict) -> pd.DataFrame:
    """Actual points of each match row, split into the same parts as xP."""
    pos, played = h.position, h.minutes > 0
    out = pd.DataFrame({
        "a_app": np.where(h.minutes >= 60, s["long_play"], s["short_play"]) * played,
        "a_goals": h.goals_scored * pos.map(s["goals_scored"]),
        "a_assists": h.assists * s["assists"],
        "a_cs": h.clean_sheets * pos.map(s["clean_sheets"]),
        "a_conceded": (h.goals_conceded // 2) * pos.map(s["goals_conceded"]),
        "a_saves": (h.saves // 3) * s["saves"],
        "a_dc": (h.defensive_contribution.fillna(0) >= pos.map(thr)) * pos.map(s["defensive_contribution"]),
        "a_bonus": h.bonus * s["bonus"],
        "a_cards": h.yellow_cards * s["yellow_cards"] + h.red_cards * s["red_cards"],
    }, index=h.index)
    return out


def season_data(history: pd.DataFrame, season: str, current_scoring: dict | None = None) -> dict:
    """Everything needed to replay one season. Players are keyed by `code`."""
    scoring, thr = season_rules(season, current_scoring or load_scoring())
    h = history[history.season == season].drop(columns="player_id").rename(columns={"code": "player_id"})
    h = pd.concat([h, _actual_parts(h, scoring, thr)], axis=1)
    prev_name = ALL_SEASONS[ALL_SEASONS.index(season) - 1] if season != ALL_SEASONS[0] else None
    p = history[history.season == prev_name]
    cols = sorted(set(RATE_STATS + ["minutes", "goals_scored", "assists", "own_goals", "expected_goals", "expected_assists"]))
    prev = p.groupby("code")[cols].sum(min_count=1).reset_index().rename(columns={"code": "player_id"})
    prev["season_name"] = prev_name or ""
    home = h[h.was_home][["fixture_id", "gw", "team_id", "opponent_team_id"]].drop_duplicates("fixture_id")
    fixtures = home.rename(columns={"team_id": "team_h", "opponent_team_id": "team_a"})
    teams = h[["team_id", "team"]].drop_duplicates().rename(columns={"team": "short_name"})
    return {"season": season, "rows": h, "prev": prev, "fixtures": fixtures, "teams": teams,
            "events": pd.DataFrame({"gw": range(1, 39)}), "scoring": scoring, "dc_threshold": thr,
            "gws": sorted(g for g in h.gw.unique() if g >= max(FIRST_GW, h.gw.min() + 1))}


def tables_for(sd: dict, gw: int) -> dict:
    """The model's input tables as they stood before `gw`."""
    h = sd["rows"]
    now = h[h.gw == gw].drop_duplicates("player_id")     # who is in the game, at which club and price
    players = now[["player_id", "web_name", "position", "team", "team_id"]].assign(now_cost=now.value)
    return {"players": players.reset_index(drop=True), "fixtures": sd["fixtures"], "events": sd["events"],
            "teams": sd["teams"], "player_seasons": sd["prev"],
            "player_gw": h[h.gw < gw].drop(columns=["web_name", "position", "team"])}


def replay_gw(sd: dict, gw: int, dials: Dials = DIALS, horizon: int = 1) -> pd.DataFrame:
    """One row per player per projected GW: xP and its parts, actual points and their parts.

    ppg = the player's average points per club match before `gw` (the naive baseline).
    """
    tables = tables_for(sd, gw)
    proj, _ = project(tables, as_of_gw=gw - 1, horizon=horizon, use_availability=False, dials=dials,
                      scoring=sd["scoring"], dc_threshold=sd["dc_threshold"])
    h = sd["rows"]
    gws = proj.gw.unique()
    act = (h[h.gw.isin(gws)].groupby(["player_id", "gw"])
           .agg(pts=("total_points", "sum"), mins=("minutes", "sum"), started=("starts", "max"),
                **{f"a_{p}": (f"a_{p}", "sum") for p in PARTS}).reset_index())
    ppg = tables["player_gw"].groupby("player_id").total_points.mean().rename("ppg")
    out = proj.merge(act, on=["player_id", "gw"], how="left").merge(ppg, on="player_id", how="left")
    fill = ["pts", "mins", "started", "ppg"] + [f"a_{p}" for p in PARTS]
    out[fill] = out[fill].fillna(0)
    return out.assign(season=sd["season"], as_of=gw - 1)


def run_season(sd: dict, dials: Dials = DIALS, gws: list[int] | None = None) -> pd.DataFrame:
    return pd.concat([replay_gw(sd, g, dials) for g in (gws or sd["gws"])], ignore_index=True)


def best_xi_points(df: pd.DataFrame, by: str) -> float:
    """Actual points of the XI that `by` ranks highest: valid formation, captain doubled.
    No budget or club limit: this measures ranking skill, not squad building."""
    top = {p: g.nlargest(5, by) for p, g in df.groupby("position")}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3:
                xi = pd.concat([top["GKP"].head(1), top["DEF"].head(d), top["MID"].head(m), top["FWD"].head(f)])
                if best is None or xi[by].sum() > best[by].sum():
                    best = xi
    return best.pts.sum() + best.loc[best[by].idxmax(), "pts"]


def summarise(rows: pd.DataFrame) -> dict:
    played = rows[rows.mins > 0]
    err = rows.xp - rows.pts
    by_gw = rows.groupby(["season", "gw"])
    return {
        "player_gws": len(rows), "played": len(played),
        "proj_pts": rows.xp.sum(), "actual_pts": rows.pts.sum(),
        "mae": err.abs().mean(), "rmse": np.sqrt((err ** 2).mean()),
        "mae_played": (played.xp - played.pts).abs().mean(),
        "corr_played": played.xp.corr(played.pts), "corr_played_ppg": played.ppg.corr(played.pts),
        "corr_all": rows.xp.corr(rows.pts),
        "xi_model": by_gw.apply(best_xi_points, by="xp").mean(),
        "xi_ppg": by_gw.apply(best_xi_points, by="ppg").mean(),
    }


def components(rows: pd.DataFrame) -> pd.DataFrame:
    """Projected vs actual points by part of the score."""
    out = pd.DataFrame({"projected": [rows[f"xp_{p}"].sum() for p in PARTS],
                        "actual": [rows[f"a_{p}"].sum() for p in PARTS]}, index=PARTS)
    out["ratio"] = out.projected / out.actual
    return out.rename_axis("part").reset_index()


def buckets(rows: pd.DataFrame) -> pd.DataFrame:
    """Do players projected 4-5 points actually average 4-5?"""
    b = pd.cut(rows.xp, BUCKETS, labels=BUCKET_LABELS)
    return (rows.groupby(b, observed=True).agg(player_gws=("xp", "size"), mean_xp=("xp", "mean"),
                                               mean_actual=("pts", "mean"))
            .rename_axis("xp_bucket").reset_index())
