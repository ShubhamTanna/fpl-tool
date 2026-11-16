"""Draft teams: saved squads kept apart from the real team.

A draft is a dict:
  id, name, start_gw, note, source, created_at
  budget   total money the draft may spend (tenths of a million)
  prices   {player_id: price paid}. A player copied from the real team is valued at his
           selling price; a player added later at his price on the day he was added.
  squads   {gameweek: [15 player ids]}. An edit is stored under the gameweek it takes effect,
           so earlier gameweeks keep the squad they were played with.
JSON turns the integer keys into strings; squad_at() and the helpers handle both.
"""
from datetime import datetime, timezone

import pandas as pd

from ..optimize.checker import check_squad
from ..optimize.rules import Rules


def new_draft(drafts: list[dict], name: str, start_gw: int, note: str, squad: list[int], prices: dict,
              budget: int, source: str) -> dict:
    return {"id": 1 + max((d["id"] for d in drafts), default=0), "name": name, "start_gw": int(start_gw),
            "note": note, "source": source, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "budget": int(budget), "prices": {str(i): int(prices[i]) for i in squad},
            "squads": {str(int(start_gw)): [int(i) for i in squad]}}


def squad_at(draft: dict, gw: int) -> list[int]:
    """The squad in force for gameweek `gw`: the latest one stored at or before it."""
    keys = sorted(int(k) for k in draft["squads"])
    use = [k for k in keys if k <= gw] or keys[:1]
    return list(draft["squads"][str(use[-1])])


def current_squad(draft: dict) -> list[int]:
    return squad_at(draft, 10 ** 6)


def spent(draft: dict, squad: list[int] | None = None) -> int:
    return sum(draft["prices"][str(i)] for i in (squad or current_squad(draft)))


def remaining(draft: dict) -> int:
    return draft["budget"] - spent(draft)


def check_draft(squad: list[int], cost: int, budget: int, players: pd.DataFrame, rules: Rules) -> list[str]:
    """Squad size, positions, 3-per-club (the optimizer's independent checker) and budget."""
    errs = check_squad(squad, players, rules)
    if cost > budget:
        errs.append(f"over budget by {(cost - budget) / 10:.1f}m")
    return errs


def swap(draft: dict, out_id: int, in_id: int, players: pd.DataFrame, rules: Rules,
         effective_gw: int) -> tuple[dict, list[str]]:
    """Replace one player. Returns (draft, problems); the draft is unchanged if there are problems."""
    squad = current_squad(draft)
    if out_id not in squad:
        return draft, ["the player to remove is not in the draft"]
    if in_id in squad:
        return draft, ["the player to add is already in the draft"]
    p = players.set_index("player_id")
    if p.position[in_id] != p.position[out_id]:
        return draft, [f"a {p.position[out_id]} must be replaced by a {p.position[out_id]}"]
    new_squad = [in_id if i == out_id else i for i in squad]
    prices = {**draft["prices"], str(in_id): int(p.now_cost[in_id])}
    cost = sum(prices[str(i)] for i in new_squad)
    errs = check_draft(new_squad, cost, draft["budget"], players, rules)
    if errs:
        return draft, errs
    gw = max(int(effective_gw), draft["start_gw"])
    return {**draft, "prices": prices, "squads": {**draft["squads"], str(gw): new_squad}}, []
