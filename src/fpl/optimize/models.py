"""MILP models: squad builder, weekly picks, transfer planner.

A MILP (mixed-integer linear program) picks yes/no decisions (own this player? start him?)
to maximise a linear objective (total xP) under linear constraints (budget, positions, clubs).

The weights below are judgement calls, not fitted values.
"""
import pandas as pd
import pulp

from .rules import Rules

DECAY = 0.9            # each further gameweek counts 10% less: later projections are less certain
BENCH_OUTFIELD = 0.10  # a bench outfielder is worth 10% of his xP (chance he is subbed on)
BENCH_GKP = 0.02       # the reserve keeper almost never plays
FT_VALUE = 1.0         # points credited per free transfer left unused at the end of the plan
# A transfer is suggested only if it adds more than this many xP over the horizon (later weeks
# weighted down). Chosen for Shubham's rule "pick well, roll transfers". The backtest
# (scripts/backtest_threshold.py) could not separate values from 0 to 6: season totals moved
# by less than the season-to-season noise, so this is a judgement call, not a fitted value.
MIN_GAIN = 2.0


def _solve(prob: pulp.LpProblem, time_limit: int = 120) -> None:
    status = prob.solve(pulp.HiGHS(msg=False, timeLimit=time_limit))
    if "Optimal" not in str(status):
        raise RuntimeError(f"solver did not find an optimal solution (status {status})")


def _xp_table(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """Rows = players, columns = gameweeks, values = xP."""
    return proj[proj.gw.isin(gws)].pivot(index="player_id", columns="gw", values="xp").fillna(0.0)


def _add_lineup(prob, x, ids, pos, rules: Rules, tag: str):
    """Add starting-XI (y) and captain (c) variables for one gameweek, given squad variables x."""
    y = prob.add_variable_dict(f"y_{tag}", ids, cat="Binary")
    c = prob.add_variable_dict(f"c_{tag}", ids, cat="Binary")
    for i in ids:
        prob += y[i] <= x[i]          # can only start players you own
        prob += c[i] <= y[i]          # captain must be in the XI
    prob += pulp.lpSum(y.values()) == rules.xi_size
    prob += pulp.lpSum(c.values()) == 1
    for name in rules.squad_count:
        n = pulp.lpSum(y[i] for i in ids if pos[i] == name)
        prob += n >= rules.xi_min[name]
        prob += n <= rules.xi_max[name]
    return y, c


def _add_squad_rules(prob, x, ids, pos, club, rules: Rules) -> None:
    for name, n in rules.squad_count.items():
        prob += pulp.lpSum(x[i] for i in ids if pos[i] == name) == n
    for t in set(club.values()):
        prob += pulp.lpSum(x[i] for i in ids if club[i] == t) <= rules.team_limit


def _gw_value(x, y, c, ids, xp_gw, pos):
    """xP of one gameweek: XI + captain's extra share + a small credit for the bench."""
    bench_w = {i: BENCH_GKP if pos[i] == "GKP" else BENCH_OUTFIELD for i in ids}
    return pulp.lpSum(xp_gw[i] * (y[i] + c[i] + bench_w[i] * (x[i] - y[i])) for i in ids)


def _lineup_result(squad: list[int], y, c, xp_gw, pos) -> dict:
    xi = [i for i in squad if y[i].value() > 0.5]
    captain = next(i for i in xi if c[i].value() > 0.5)
    vice = max((i for i in xi if i != captain), key=lambda i: xp_gw[i])
    bench = [i for i in squad if i not in xi]
    # reserve keeper first, then outfielders by xP (the order they come on)
    bench.sort(key=lambda i: (pos[i] != "GKP", -xp_gw[i]))
    order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    xi.sort(key=lambda i: (order[pos[i]], -xp_gw[i]))
    return {"xi": xi, "bench": bench, "captain": captain, "vice": vice,
            "xp": sum(xp_gw[i] for i in xi) + xp_gw[captain]}


def _pool(players: pd.DataFrame, keep: list[int] = ()) -> pd.DataFrame:
    """Players who can be picked: not departed/unavailable (status 'u'), plus anyone already owned."""
    return players[(players.status != "u") | players.player_id.isin(keep)].set_index("player_id")


def build_squad(proj: pd.DataFrame, players: pd.DataFrame, rules: Rules, gws: list[int],
                budget: int | None = None) -> dict:
    """Best 15 from scratch for the given gameweeks."""
    p = _pool(players)
    ids, pos, club, cost = list(p.index), p.position.to_dict(), p.team.to_dict(), p.now_cost.to_dict()
    xp = _xp_table(proj, gws).reindex(ids).fillna(0.0)
    prob = pulp.LpProblem("squad", pulp.LpMaximize)
    x = prob.add_variable_dict("x", ids, cat="Binary")
    _add_squad_rules(prob, x, ids, pos, club, rules)
    prob += pulp.lpSum(cost[i] * x[i] for i in ids) <= (budget or rules.budget)
    lineups, obj = {}, []
    for k, gw in enumerate(gws):
        y, c = _add_lineup(prob, x, ids, pos, rules, str(gw))
        lineups[gw] = (y, c)
        obj.append(DECAY ** k * _gw_value(x, y, c, ids, xp[gw].to_dict(), pos))
    prob += pulp.lpSum(obj)
    _solve(prob)
    squad = [i for i in ids if x[i].value() > 0.5]
    out = {"squad": squad, "cost": sum(cost[i] for i in squad), "gws": []}
    for gw, (y, c) in lineups.items():
        out["gws"].append({"gw": gw, "squad": squad, **_lineup_result(squad, y, c, xp[gw].to_dict(), pos)})
    return out


def pick_team(squad: list[int], proj: pd.DataFrame, players: pd.DataFrame, rules: Rules, gw: int) -> dict:
    """XI, bench order, captain and vice-captain for one gameweek from a fixed squad."""
    p = players.set_index("player_id").loc[squad]
    pos = p.position.to_dict()
    xp = _xp_table(proj, [gw]).reindex(squad).fillna(0.0)[gw].to_dict()
    prob = pulp.LpProblem("picks", pulp.LpMaximize)
    x = {i: 1 for i in squad}
    y, c = _add_lineup(prob, x, squad, pos, rules, str(gw))
    prob += _gw_value(x, y, c, squad, xp, pos)
    _solve(prob)
    return {"gw": gw, "squad": squad, **_lineup_result(squad, y, c, xp, pos)}


def plan_transfers(team: dict, proj: pd.DataFrame, players: pd.DataFrame, rules: Rules, gws: list[int],
                   allow_transfers: bool = True, min_gain: float = MIN_GAIN, lock: list[int] = (),
                   ban: list[int] = (), max_transfers: int | None = None) -> dict:
    """Best transfers, XI and captain for each gameweek in `gws`, starting from `team`.

    team = {"squad": [ids], "bank": int, "free_transfers": int, "sell_price": {id: price}}
    Free transfers roll over (up to the cap); each transfer beyond them costs rules.hit_cost.
    min_gain: every transfer is charged this many xP inside the solver, so one is made only
    if it adds more than that. The charge is not part of the reported xP.
    lock: players who must stay in the squad every gameweek. ban: players who may not be
    bought. max_transfers: most transfers allowed in any one gameweek.
    """
    p = _pool(players, keep=team["squad"])
    ids, pos, club, cost = list(p.index), p.position.to_dict(), p.team.to_dict(), p.now_cost.to_dict()
    sell = {i: team["sell_price"].get(i, cost[i]) for i in ids}
    xp = _xp_table(proj, gws).reindex(ids).fillna(0.0)
    owned = {i: int(i in team["squad"]) for i in ids}

    prob = pulp.LpProblem("transfers", pulp.LpMaximize)
    obj, state = [], {}
    prev_x, prev_bank, ft = owned, team["bank"], team["free_transfers"]
    for k, gw in enumerate(gws):
        x = prob.add_variable_dict(f"x_{gw}", ids, cat="Binary")       # owned this GW
        buy = prob.add_variable_dict(f"in_{gw}", ids, cat="Binary")
        out = prob.add_variable_dict(f"out_{gw}", ids, cat="Binary")
        for i in ids:
            prob += x[i] == prev_x[i] + buy[i] - out[i]
            if not allow_transfers:
                prob += buy[i] == 0
        for i in lock:
            if i in x:
                prob += x[i] == 1
        for i in ban:
            if i in buy:
                prob += buy[i] == 0
        _add_squad_rules(prob, x, ids, pos, club, rules)
        bank = prob.add_variable(f"bank_{gw}", lowBound=0)             # money can never go negative
        prob += bank == prev_bank + pulp.lpSum(sell[i] * out[i] for i in ids) - pulp.lpSum(cost[i] * buy[i] for i in ids)
        n = pulp.lpSum(buy.values())
        if max_transfers is not None:
            prob += n <= max_transfers
        hits = prob.add_variable(f"hits_{gw}", lowBound=0, cat="Integer")
        prob += hits >= n - ft                                         # transfers beyond the free ones
        ft_next = prob.add_variable(f"ft_{gw}", lowBound=1, upBound=rules.max_free_transfers)
        prob += ft_next <= ft - (n - hits) + 1                         # unused free transfers roll over
        y, c = _add_lineup(prob, x, ids, pos, rules, str(gw))
        obj.append(DECAY ** k * (_gw_value(x, y, c, ids, xp[gw].to_dict(), pos) - rules.hit_cost * hits)
                   - min_gain * n)
        state[gw] = (x, buy, out, y, c, bank, hits, ft)
        prev_x, prev_bank, ft = x, bank, ft_next
    obj.append(DECAY ** (len(gws) - 1) * FT_VALUE * ft)                # small credit for transfers left over
    prob += pulp.lpSum(obj)
    _solve(prob)

    plan = {"gws": []}
    ft_val = team["free_transfers"]
    for gw, (x, buy, out, y, c, bank, hits, _) in state.items():
        squad = [i for i in ids if x[i].value() > 0.5]
        row = _lineup_result(squad, y, c, xp[gw].to_dict(), pos)
        n_hits = round(hits.value())
        n_in = sum(buy[i].value() > 0.5 for i in ids)
        plan["gws"].append({
            "gw": gw, "squad": squad, **row,
            "transfers_in": [i for i in ids if buy[i].value() > 0.5],
            "transfers_out": [i for i in ids if out[i].value() > 0.5],
            "free_transfers": ft_val, "hits": n_hits, "bank": round(bank.value()),
            "xp_net": row["xp"] - rules.hit_cost * n_hits,
        })
        # The solver's own counter can sit below the true count when a spare transfer has
        # no use, so the reported count is rolled forward from the transfers actually made.
        ft_val = min(rules.max_free_transfers, ft_val - min(n_in, ft_val) + 1)
    plan["xp_net"] = sum(g["xp_net"] for g in plan["gws"])
    return plan
