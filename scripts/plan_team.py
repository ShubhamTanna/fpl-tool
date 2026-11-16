"""Section 3b/3c: transfer plan and weekly picks for a real team.

Usage: python scripts/plan_team.py --team-id 123456 [--horizon 5] [--free-transfers N] [--bank 1.5]
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.ingest.team import load_team  # noqa: E402
from fpl.optimize.checker import check_plan  # noqa: E402
from fpl.optimize.models import plan_transfers  # noqa: E402
from fpl.optimize.rules import load_rules  # noqa: E402

P = ROOT / "data" / "processed"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team-id", type=int, required=True)
    ap.add_argument("--horizon", type=int, default=5, choices=range(1, 6))
    ap.add_argument("--free-transfers", type=int, default=None, help="override the derived count")
    ap.add_argument("--bank", type=float, default=None, help="override the bank, in millions")
    a = ap.parse_args()

    players, proj = pd.read_parquet(P / "players.parquet"), pd.read_parquet(P / "projections.parquet")
    player_gw = pd.read_parquet(P / "player_gw.parquet")
    rules = load_rules()
    gws = sorted(proj.gw.unique())[:a.horizon]
    team = load_team(a.team_id, players, player_gw, gws[0] - 1, rules.sell_fee, rules.max_free_transfers)
    derived_ft = team["free_transfers"]
    if a.free_transfers is not None:
        team["free_transfers"] = a.free_transfers
    if a.bank is not None:
        team["bank"] = round(a.bank * 10)

    p = players.set_index("player_id")
    name = lambda i: f"{p.web_name[i]} ({p.team[i]}, {p.position[i]})"  # noqa: E731
    xp = proj[proj.gw.isin(gws)].pivot(index="player_id", columns="gw", values="xp")

    print(f"Team: {team['name']}   planning GW{gws[0]}-{gws[-1]}")
    print(f"Bank {team['bank'] / 10:.1f}m   Free transfers {team['free_transfers']}"
          + (f" (entered by hand; replay of the season gives {derived_ft})" if a.free_transfers is not None
             else " (derived by replaying the season - check against the FPL site)"))
    sq = pd.DataFrame({"player": [p.web_name[i] for i in team["squad"]],
                       "pos": [p.position[i] for i in team["squad"]],
                       "team": [p.team[i] for i in team["squad"]],
                       "bought": [team["purchase_price"][i] / 10 for i in team["squad"]],
                       "now": [p.now_cost[i] / 10 for i in team["squad"]],
                       "sell": [team["sell_price"][i] / 10 for i in team["squad"]],
                       "status": [p.status[i] for i in team["squad"]],
                       f"xP GW{gws[0]}": [round(xp.loc[i, gws[0]], 2) for i in team["squad"]],
                       f"xP GW{gws[0]}-{gws[-1]}": [round(xp.loc[i].sum(), 2) for i in team["squad"]]})
    print("\nCurrent squad (sell prices are estimates from the 50% rule)")
    print(sq.to_string(index=False))

    t0 = time.time()
    plan = plan_transfers(team, proj, players, rules, gws)
    hold = plan_transfers(team, proj, players, rules, gws, allow_transfers=False)
    errs = check_plan(plan, team, players, rules) + check_plan(hold, team, players, rules)
    print(f"\nSolved in {time.time() - t0:.1f}s   Constraint check: {'PASS' if not errs else errs}")

    print("\n== Plan")
    for g, h in zip(plan["gws"], hold["gws"]):
        print(f"\nGW{g['gw']}: free transfers {g['free_transfers']}, hits {g['hits']} "
              f"(-{g['hits'] * rules.hit_cost}), bank after {g['bank'] / 10:.1f}m")
        if not g["transfers_in"]:
            print("  No transfers (roll the free transfer)")
        outs = sorted(g["transfers_out"], key=lambda i: p.position[i])
        ins = sorted(g["transfers_in"], key=lambda i: p.position[i])
        for o, i in zip(outs, ins):
            print(f"  OUT {name(o)} {xp.loc[o, g['gw']]:.2f}  ->  IN {name(i)} {p.now_cost[i] / 10:.1f}m {xp.loc[i, g['gw']]:.2f}")
        print("  XI:    " + ", ".join(f"{p.web_name[i]}{' (C)' if i == g['captain'] else ' (V)' if i == g['vice'] else ''}"
                                      for i in g["xi"]))
        print("  Bench: " + ", ".join(p.web_name[i] for i in g["bench"]))
        print(f"  xP {g['xp']:.2f} - hits {g['hits'] * rules.hit_cost} = {g['xp_net']:.2f}   "
              f"(no transfers: {h['xp_net']:.2f}, gain {g['xp_net'] - h['xp_net']:+.2f})")
    print(f"\n== Total GW{gws[0]}-{gws[-1]}: plan {plan['xp_net']:.2f} vs no transfers {hold['xp_net']:.2f} "
          f"= gain {plan['xp_net'] - hold['xp_net']:+.2f} xP")


if __name__ == "__main__":
    main()
