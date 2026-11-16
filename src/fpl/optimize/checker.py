"""Independent rule checks for optimizer output.

Plain pandas/Python, sharing no code with the MILP models, so a modelling mistake
cannot hide itself. Every function returns a list of problems; an empty list = valid.
"""
import pandas as pd

from .rules import Rules


def check_squad(squad: list[int], players: pd.DataFrame, rules: Rules) -> list[str]:
    errs = []
    p = players.set_index("player_id")
    if len(squad) != rules.squad_size or len(set(squad)) != len(squad):
        errs.append(f"squad has {len(squad)} players ({len(set(squad))} unique), need {rules.squad_size}")
    if missing := [i for i in squad if i not in p.index]:
        return errs + [f"unknown player ids {missing}"]
    s = p.loc[squad]
    for pos, n in rules.squad_count.items():
        if (got := (s.position == pos).sum()) != n:
            errs.append(f"{got} {pos} in squad, need {n}")
    for team, n in s.team.value_counts().items():
        if n > rules.team_limit:
            errs.append(f"{n} players from {team}, max {rules.team_limit}")
    return errs


def check_lineup(xi: list[int], bench: list[int], captain: int, vice: int,
                 squad: list[int], players: pd.DataFrame, rules: Rules) -> list[str]:
    errs = []
    p = players.set_index("player_id")
    if len(xi) != rules.xi_size:
        errs.append(f"XI has {len(xi)} players, need {rules.xi_size}")
    if sorted(xi + bench) != sorted(squad):
        errs.append("XI + bench is not exactly the squad")
    pos = p.loc[xi, "position"]
    for name in rules.squad_count:
        n = (pos == name).sum()
        if not rules.xi_min[name] <= n <= rules.xi_max[name]:
            errs.append(f"{n} {name} in XI, allowed {rules.xi_min[name]}-{rules.xi_max[name]}")
    if captain not in xi or vice not in xi or captain == vice:
        errs.append("captain and vice-captain must be two different XI players")
    if bench and p.loc[bench[0], "position"] != "GKP":
        errs.append("first bench slot must be the reserve goalkeeper")
    return errs


def check_plan(plan: dict, team: dict, players: pd.DataFrame, rules: Rules) -> list[str]:
    """Replay a transfer plan gameweek by gameweek: squads, money, free transfers, hits."""
    errs = []
    cost = players.set_index("player_id").now_cost
    squad, bank, ft = list(team["squad"]), team["bank"], team["free_transfers"]
    sell = dict(team["sell_price"])
    for g in plan["gws"]:
        tag = f"GW{g['gw']}: "
        ins, outs = g["transfers_in"], g["transfers_out"]
        if len(ins) != len(outs):
            errs.append(tag + "transfers in and out differ in number")
        if bad := [i for i in outs if i not in squad]:
            errs.append(tag + f"selling players not in the squad {bad}")
        if bad := [i for i in ins if i in squad]:
            errs.append(tag + f"buying players already in the squad {bad}")
        bank += sum(sell.get(i, cost[i]) for i in outs) - sum(cost[i] for i in ins)
        squad = [i for i in squad if i not in outs] + ins
        for i in ins:
            sell[i] = cost[i]  # a player bought in the plan sells at today's price
        if bank < 0:
            errs.append(tag + f"bank is negative ({bank / 10:.1f}m)")
        if bank != g["bank"]:
            errs.append(tag + f"bank reported {g['bank']} but replays to {bank}")
        hits = max(0, len(ins) - ft)
        if hits != g["hits"] or ft != g["free_transfers"]:
            errs.append(tag + f"free transfers/hits reported {g['free_transfers']}/{g['hits']}, replay gives {ft}/{hits}")
        ft = min(rules.max_free_transfers, ft - min(len(ins), ft) + 1)
        if sorted(squad) != sorted(g["squad"]):
            errs.append(tag + "squad does not match the replayed transfers")
        errs += [tag + e for e in check_squad(g["squad"], players, rules)]
        errs += [tag + e for e in check_lineup(g["xi"], g["bench"], g["captain"], g["vice"],
                                               g["squad"], players, rules)]
    return errs
