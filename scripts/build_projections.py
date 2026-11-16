"""Section 2: build xP for the next 8 gameweeks, show the top 20s and backtest."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.model.scoring import actual_points, load_scoring  # noqa: E402
from fpl.model.xp import project  # noqa: E402

P = ROOT / "data" / "processed"
NAMES = ["teams", "players", "fixtures", "events", "player_gw", "player_seasons"]
pd.set_option("display.width", 200)


def backtest(tables: dict, gw: int) -> dict:
    """Project `gw` using only matches before it, then compare with what happened.

    Injury flags are switched off: FPL only publishes today's flags, not the ones
    that were showing before a past gameweek.
    """
    proj, _ = project(tables, as_of_gw=gw - 1, horizon=1, use_availability=False)
    pg = tables["player_gw"]
    actual = pg[pg.gw == gw].groupby("player_id").agg(pts=("total_points", "sum"), mins=("minutes", "sum"))
    before = pg[pg.gw < gw].groupby("player_id").total_points.mean().rename("ppg_before")  # naive baseline
    d = proj.set_index("player_id")[["xp"]].join(actual, how="inner").join(before).fillna({"ppg_before": 0})
    played = d[d.mins > 0]
    return {"gw": gw, "players": len(d), "played": len(played),
            "xP all": d.xp.corr(d.pts), "baseline all": d.ppg_before.corr(d.pts),
            "xP played": played.xp.corr(played.pts), "baseline played": played.ppg_before.corr(played.pts),
            "xP rank corr all": d.xp.rank().corr(d.pts.rank())}


def main() -> None:
    tables = {n: pd.read_parquet(P / f"{n}.parquet") for n in NAMES}
    m = tables["player_gw"].merge(tables["players"][["player_id", "position"]], on="player_id")
    bad = (actual_points(m, load_scoring()) != m.total_points).sum()
    print(f"Scoring rules check: {bad} of {len(m):,} match rows differ from FPL's points")

    proj, r = project(tables)
    proj.to_parquet(P / "projections.parquet", index=False)
    gws = sorted(proj.gw.unique())
    print(f"Projections: {len(proj):,} rows = {proj.player_id.nunique()} players x GW{gws[0]}-{gws[-1]}")

    print(f"\n== Team ratings (league average xG: home {r['mu_home']:.2f}, away {r['mu_away']:.2f})")
    print("   attack > 1 = creates more than average; defence < 1 = concedes less than average")
    t = tables["teams"].set_index("team_id")[["short_name"]].assign(attack=r["attack"], defence=r["defence"])
    print(t.sort_values("attack", ascending=False).round(2).to_string(index=False))

    parts = ["xp_app", "xp_goals", "xp_assists", "xp_cs", "xp_conceded", "xp_saves", "xp_dc", "xp_bonus", "xp_cards"]
    nxt = proj[proj.gw == gws[0]]
    five = (proj[proj.gw.isin(gws[:5])].groupby(["player_id", "web_name", "position", "team", "now_cost"], as_index=False)
            .agg(xmins=("xmins", "sum"), xp=("xp", "sum")))
    five["price"], nxt = five.now_cost / 10, nxt.assign(price=nxt.now_cost / 10)
    for pos in ["GKP", "DEF", "MID", "FWD"]:
        print(f"\n== {pos}: top 20 for GW{gws[0]}")
        cols = ["web_name", "team", "price", "opp", "xmins"] + parts + ["xp"]
        print(nxt[nxt.position == pos].nlargest(20, "xp")[cols].round(2).to_string(index=False))
        print(f"\n== {pos}: top 20 for GW{gws[0]}-{gws[4]} (5 gameweeks)")
        print(five[five.position == pos].nlargest(20, "xp")[["web_name", "team", "price", "xmins", "xp"]]
              .round(2).to_string(index=False))

    last = gws[0] - 1
    print(f"\n== Backtest: projections made before each GW vs actual points (Pearson correlation)")
    print("   baseline = the player's average points per match before that GW")
    bt = pd.DataFrame([backtest(tables, g) for g in range(max(4, last - 4), last + 1)])
    print(bt.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
