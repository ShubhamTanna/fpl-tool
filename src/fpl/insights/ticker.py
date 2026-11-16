"""Fixture ticker: separate attack and defence outlook per team, from our own team ratings
(not the official FDR).

  xg_for      expected goals the team scores in that fixture  (higher = better for attackers)
  xg_against  expected goals it concedes                      (lower = better for defenders)
  p_cs        clean-sheet probability = exp(-xg_against)
"""
import numpy as np
import pandas as pd

from ..model.teams import fit_ratings


def fixture_ticker(player_gw: pd.DataFrame, fixtures: pd.DataFrame, teams: pd.DataFrame,
                   gws: list[int]) -> pd.DataFrame:
    """One row per team per gameweek (doubles summed, blanks = 0 fixtures)."""
    r = fit_ratings(player_gw)
    fx = fixtures[fixtures.gw.isin(gws)]
    home = fx[["gw", "team_h", "team_a"]].set_axis(["gw", "team_id", "opp_id"], axis=1).assign(is_home=True)
    away = fx[["gw", "team_a", "team_h"]].set_axis(["gw", "team_id", "opp_id"], axis=1).assign(is_home=False)
    t = pd.concat([home, away])
    mu_for = np.where(t.is_home, r["mu_home"], r["mu_away"])
    mu_opp = np.where(t.is_home, r["mu_away"], r["mu_home"])
    t["xg_for"] = mu_for * t.team_id.map(r["attack"]) * t.opp_id.map(r["defence"])
    t["xg_against"] = mu_opp * t.opp_id.map(r["attack"]) * t.team_id.map(r["defence"])
    short = teams.set_index("team_id").short_name
    t["opp"] = t.opp_id.map(short) + np.where(t.is_home, "(H)", "(A)")
    agg = t.groupby(["team_id", "gw"]).agg(opp=("opp", " + ".join), n_fixtures=("opp", "size"),
                                           xg_for=("xg_for", "sum"), xg_against=("xg_against", "sum")).reset_index()
    grid = pd.MultiIndex.from_product([teams.team_id, gws], names=["team_id", "gw"]).to_frame(index=False)
    out = grid.merge(agg, on=["team_id", "gw"], how="left").fillna({"opp": "-", "n_fixtures": 0, "xg_for": 0.0})
    out["p_cs"] = np.where(out.n_fixtures > 0, np.exp(-out.xg_against), 0.0)  # doubles: P(both clean)
    out["team"] = out.team_id.map(short)
    return out


def ticker_view(ticker: pd.DataFrame, value: str, best_high: bool) -> pd.DataFrame:
    """Team x gameweek grid of 'OPP(H) 1.85', best run of fixtures at the top."""
    cell = ticker.opp + " " + ticker[value].map("{:.2f}".format)
    grid = ticker.assign(cell=cell).pivot(index="team", columns="gw", values="cell")
    grid.columns = [f"GW{g}" for g in grid.columns]
    total = ticker.groupby("team")[value].sum()
    grid.insert(0, "total", total.round(2))
    return grid.sort_values("total", ascending=not best_high)
