"""Backtest of the rule "pick well, roll transfers": how big must a projected gain be
before a transfer is worth making?

One simulated manager per threshold X. All start a season with the same squad (the squad
builder's pick). Each gameweek the manager looks at the best single swap by projected gain
over the next 5 gameweeks (later weeks weighted down, as in the planner). If the gain is
above X he makes it and looks again while he has free transfers; otherwise he rolls the
transfer (up to the cap). No hits, no chips.

Simplifications, the same for every threshold: players are bought and sold at the current
price (no 50% rule), no automatic substitutions, and the fixture list is the one that was
actually played.
"""
import pandas as pd

from ..model.dials import DIALS, Dials
from ..optimize.models import DECAY, build_squad
from ..optimize.rules import Rules
from .harness import replay_gw

HORIZON = 5
START_GW = 4      # the first three gameweeks have too little data to plan from
FORMATIONS = [(d, m, 10 - d - m) for d in range(3, 6) for m in range(2, 6) if 1 <= 10 - d - m <= 3]


def _xi(squad: list, xp: dict, pos: dict) -> list:
    """Best XI by xP: valid formation. Returned with the captain first."""
    by = {p: sorted((i for i in squad if pos[i] == p), key=lambda i: -xp.get(i, 0.0))
          for p in ("GKP", "DEF", "MID", "FWD")}
    best, best_v = None, -1.0
    for d, m, f in FORMATIONS:
        xi = by["GKP"][:1] + by["DEF"][:d] + by["MID"][:m] + by["FWD"][:f]
        v = sum(xp.get(i, 0.0) for i in xi)
        if v > best_v:
            best, best_v = xi, v
    return sorted(best, key=lambda i: -xp.get(i, 0.0))


def _value(squad: list, xps: list[dict], pos: dict) -> float:
    """Planner-style value of a squad: XI + captain per gameweek, later weeks weighted down."""
    total = 0.0
    for k, xp in enumerate(xps):
        xi = _xi(squad, xp, pos)
        total += DECAY ** k * (sum(xp.get(i, 0.0) for i in xi) + xp.get(xi[0], 0.0))
    return total


def _best_swap(squad, bank, xps, pos, club, cost, per_out: int = 3):
    """(gain, out, in) of the best single legal swap, or None."""
    w = pd.Series(0.0, index=list(pos))
    for k, xp in enumerate(xps):
        w = w.add(pd.Series(xp) * DECAY ** k, fill_value=0.0)
    owned, base = set(squad), _value(squad, xps, pos)
    n_club = pd.Series([club[i] for i in squad]).value_counts().to_dict()
    best = None
    for o in squad:
        cands = [c for c in w.index if pos[c] == pos[o] and c not in owned and cost[c] <= bank + cost[o]
                 and n_club.get(club[c], 0) - (club[c] == club[o]) < 3]
        for c in sorted(cands, key=lambda c: -w[c])[:per_out]:
            gain = _value([c if i == o else i for i in squad], xps, pos) - base
            if best is None or gain > best[0]:
                best = (gain, o, c)
    return best


def simulate_season(sd: dict, rules: Rules, thresholds: list[float], dials: Dials = DIALS) -> pd.DataFrame:
    gws = [g for g in sd["gws"] if g >= START_GW]
    pos, club, cost = {}, {}, {}
    state, rows = {}, []
    for g in gws:
        proj = replay_gw(sd, g, dials, horizon=HORIZON)
        now = proj[proj.gw == g]
        pos.update(zip(now.player_id, now.position)); club.update(zip(now.player_id, now.team))
        cost.update(zip(now.player_id, now.now_cost))
        xps = [dict(zip(d.player_id, d.xp)) for _, d in proj.groupby("gw")]
        pts = dict(zip(now.player_id, now.pts))
        if not state:
            players = now[["player_id", "position", "team", "now_cost"]].assign(status="a")
            first = build_squad(proj, players, rules, sorted(proj.gw.unique()))
            state = {x: {"squad": list(first["squad"]), "bank": rules.budget - first["cost"], "ft": 1}
                     for x in thresholds}
        for x, s in state.items():
            made, gain_sum = 0, 0.0
            if g != gws[0]:
                while s["ft"] > 0:
                    swap = _best_swap(s["squad"], s["bank"], xps, pos, club, cost)
                    if swap is None or swap[0] <= x:
                        break
                    gain, o, c = swap
                    s["squad"] = [c if i == o else i for i in s["squad"]]
                    s["bank"] += cost[o] - cost[c]
                    s["ft"] -= 1; made += 1; gain_sum += gain
                s["ft"] = min(rules.max_free_transfers, s["ft"] + 1)
            xi = _xi(s["squad"], xps[0], pos)
            rows.append({"season": sd["season"], "threshold": x, "gw": g, "transfers": made,
                         "projected_gain": gain_sum,
                         "points": sum(pts.get(i, 0) for i in xi) + pts.get(xi[0], 0)})
    return pd.DataFrame(rows)
