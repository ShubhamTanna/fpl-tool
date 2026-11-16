"""Load a manager's team from the public FPL API: squad, bank, selling prices, free transfers."""
import math

import pandas as pd

from .cache import fetch_json
from .fpl_api import BASE


def _get(team_id: int, name: str, path: str):
    return fetch_json(f"entry/{team_id}/{name}", f"{BASE}entry/{team_id}/{path}", max_age_hours=1.0)


def load_team(team_id: int, players: pd.DataFrame, player_gw: pd.DataFrame, as_of_gw: int,
              sell_fee: float = 0.5, max_free_transfers: int = 5) -> dict:
    """The team as it stands after gameweek `as_of_gw`.

    Selling prices and the free-transfer count are not public, so both are derived:
      sell price = purchase price + half of any rise (rounded down), or today's price if it fell.
                   Purchase price comes from the transfers endpoint; for players owned since the
                   team was created it is the player's price in the team's first gameweek.
      free transfers = replay of the season: +1 each gameweek, minus transfers made, capped.
                   Wildcard and Free Hit weeks are assumed to leave the count unchanged.
    """
    entry = _get(team_id, "entry", "")
    history = _get(team_id, "history", "history/")
    transfers = _get(team_id, "transfers", "transfers/")
    chips = {c["event"]: c["name"] for c in history["chips"]}
    free_hit_gws = {gw for gw, name in chips.items() if name == "freehit"}

    # A Free Hit squad reverts after the gameweek, so read the squad from the week before.
    squad_gw = as_of_gw - 1 if as_of_gw in free_hit_gws else as_of_gw
    picks = _get(team_id, f"picks_gw{squad_gw}", f"event/{squad_gw}/picks/")
    squad = [p["element"] for p in picks["picks"]]
    bank = picks["entry_history"]["bank"]

    now = players.set_index("player_id").now_cost
    start = entry["started_event"]
    first_price = player_gw[player_gw.gw == start].groupby("player_id").value.first()
    start_price = (players.set_index("player_id").eval("now_cost - cost_change_start"))
    bought = {}
    for t in sorted(transfers, key=lambda t: t["time"]):
        if t["event"] not in free_hit_gws:
            bought[t["element_in"]] = t["element_in_cost"]
    purchase = {i: bought.get(i, int(first_price.get(i, start_price[i]))) for i in squad}
    sell_price = {i: int(now[i]) if now[i] <= purchase[i]
                  else purchase[i] + math.floor((now[i] - purchase[i]) * sell_fee) for i in squad}

    ft = 1  # available for the team's second gameweek
    used = {h["event"]: h["event_transfers"] for h in history["current"]}
    for gw in range(start + 1, as_of_gw + 1):
        if chips.get(gw) in ("wildcard", "freehit"):
            continue
        ft = min(max_free_transfers, max(ft - used.get(gw, 0), 0) + 1)

    return {"team_id": team_id, "name": entry["name"], "squad": squad, "bank": bank,
            "free_transfers": ft, "purchase_price": purchase, "sell_price": sell_price,
            "reported_value": picks["entry_history"]["value"], "chips_used": chips}
