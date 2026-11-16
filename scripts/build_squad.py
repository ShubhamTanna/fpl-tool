"""Section 3a: best 15 from scratch.  Usage: python scripts/build_squad.py [--horizon 5] [--budget 100.0]"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.optimize.checker import check_lineup, check_squad  # noqa: E402
from fpl.optimize.models import build_squad  # noqa: E402
from fpl.optimize.rules import load_rules  # noqa: E402

P = ROOT / "data" / "processed"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--budget", type=float, default=None, help="in millions, default = game budget")
    a = ap.parse_args()
    players, proj = pd.read_parquet(P / "players.parquet"), pd.read_parquet(P / "projections.parquet")
    rules = load_rules()
    gws = sorted(proj.gw.unique())[:a.horizon]
    t0 = time.time()
    res = build_squad(proj, players, rules, gws, budget=round(a.budget * 10) if a.budget else None)
    errs = check_squad(res["squad"], players, rules)
    for g in res["gws"]:
        errs += check_lineup(g["xi"], g["bench"], g["captain"], g["vice"], g["squad"], players, rules)
    if res["cost"] > (round(a.budget * 10) if a.budget else rules.budget):
        errs.append("over budget")

    p = players.set_index("player_id")
    xp = proj[proj.gw.isin(gws)].pivot(index="player_id", columns="gw", values="xp")
    first = res["gws"][0]
    print(f"Best squad for GW{gws[0]}-{gws[-1]}  (solved in {time.time() - t0:.1f}s)")
    print(f"Cost {res['cost'] / 10:.1f}m   Constraint check: {'PASS' if not errs else errs}")
    rows = []
    for i in first["xi"] + first["bench"]:
        role = "C" if i == first["captain"] else "V" if i == first["vice"] else ""
        rows.append({"": "XI" if i in first["xi"] else "bench", "player": p.web_name[i], "pos": p.position[i],
                     "team": p.team[i], "price": p.now_cost[i] / 10, "role": role,
                     **{f"GW{g}": round(xp.loc[i, g], 2) for g in gws}})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nExpected points (XI + captain):  " + "  ".join(f"GW{g['gw']} {g['xp']:.1f}" for g in res["gws"]))


if __name__ == "__main__":
    main()
