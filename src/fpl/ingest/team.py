"""Load a manager's team from the public FPL API: squad, bank, selling prices, free transfers."""
import math

import pandas as pd

from .cache import fetch_json
from .fpl_api import BASE


def _get(team_id: int, name: str, path: str, max_age_hours: float):
    return fetch_json(f"entry/{team_id}/{name}", f"{BASE}entry/{team_id}/{path}", max_age_hours)


def build_team(entry: dict, history: dict, transfers: list, picks_by_gw: dict, players: pd.DataFrame,
               player_gw: pd.DataFrame, as_of_gw: int, sell_fee: float = 0.5,
               max_free_transfers: int = 5) -> dict:
    """The team as it stands for gameweek `as_of_gw` + 1, from raw API responses (no network).

    picks_by_gw: {gameweek: picks response}. Needs `as_of_gw`, and `as_of_gw - 1` if a Free Hit
    was played in `as_of_gw`.

    Selling prices and the free-transfer count are not public, so both are derived:
      sell price = purchase price + half of any rise (rounded down), or today's price if it fell.
                   Purchase price comes from the transfers endpoint; for players owned since the
                   team was created it is the player's price in the team's first gameweek.
      free transfers = replay of the season: +1 each gameweek, minus transfers made, capped.
                   Wildcard and Free Hit weeks are assumed to leave the count unchanged.

    Transfers already made for the next gameweek are applied: the squad, bank and free
    transfers returned are what is left to work with now. They are listed in `pending`.
    """
    chips = {c["event"]: c["name"] for c in history["chips"]}
    free_hit_gws = {gw for gw, name in chips.items() if name == "freehit"}
    # A Free Hit squad reverts after the gameweek, so read the squad from the week before.
    squad_gw = as_of_gw - 1 if as_of_gw in free_hit_gws else as_of_gw
    picks = picks_by_gw[squad_gw]
    squad = [p["element"] for p in picks["picks"]]
    bank = picks["entry_history"]["bank"]

    ft = 1  # available for the team's second gameweek
    start = entry["started_event"]
    used = {h["event"]: h["event_transfers"] for h in history["current"]}
    for gw in range(start + 1, as_of_gw + 1):
        if chips.get(gw) in ("wildcard", "freehit"):
            continue
        ft = min(max_free_transfers, max(ft - used.get(gw, 0), 0) + 1)

    ordered = sorted(transfers, key=lambda t: t["time"])
    pending = [t for t in ordered if t["event"] == as_of_gw + 1]
    for t in pending:
        if t["element_out"] in squad:
            squad[squad.index(t["element_out"])] = t["element_in"]
            bank += t["element_out_cost"] - t["element_in_cost"]
    hits_taken = max(0, len(pending) - ft)
    ft_left = max(0, ft - len(pending))

    p = players.set_index("player_id")
    now = p.now_cost
    first_price = player_gw[player_gw.gw == start].groupby("player_id").value.first()
    start_price = p.now_cost - p.cost_change_start
    bought = {t["element_in"]: t["element_in_cost"] for t in ordered if t["event"] not in free_hit_gws}
    purchase = {i: bought.get(i, int(first_price.get(i, start_price[i]))) for i in squad}
    sell_price = {i: int(now[i]) if now[i] <= purchase[i]
                  else purchase[i] + math.floor((now[i] - purchase[i]) * sell_fee) for i in squad}
    return {"team_id": entry["id"], "name": entry["name"], "squad": squad, "bank": bank,
            "free_transfers": ft_left, "free_transfers_before_pending": ft, "hits_taken": hits_taken,
            "pending": [(t["element_out"], t["element_in"]) for t in pending],
            "purchase_price": purchase, "sell_price": sell_price,
            "reported_value": picks["entry_history"]["value"], "chips_used": chips,
            "gw_points": {h["event"]: h["points"] for h in history["current"]},
            "gw_hits": {h["event"]: h["event_transfers_cost"] for h in history["current"]}}


def load_team(team_id: int, players: pd.DataFrame, player_gw: pd.DataFrame, as_of_gw: int,
              sell_fee: float = 0.5, max_free_transfers: int = 5, max_age_hours: float = 1.0) -> dict:
    """Fetch the API responses (cached) and build the team. See build_team."""
    entry = _get(team_id, "entry", "", max_age_hours)
    history = _get(team_id, "history", "history/", max_age_hours)
    transfers = _get(team_id, "transfers", "transfers/", max_age_hours)
    chips = {c["event"]: c["name"] for c in history["chips"]}
    gw = as_of_gw - 1 if chips.get(as_of_gw) == "freehit" else as_of_gw
    picks = {gw: _get(team_id, f"picks_gw{gw}", f"event/{gw}/picks/", max_age_hours)}
    return build_team(entry, history, transfers, picks, players, player_gw, as_of_gw, sell_fee, max_free_transfers)


def picks_history(team_id: int, gws: list[int]) -> dict[int, dict]:
    """The squad actually fielded in past gameweeks: {gw: picks response}. Finished weeks never change."""
    return {g: _get(team_id, f"picks_gw{g}", f"event/{g}/picks/", 24 * 365 * 10) for g in gws}
