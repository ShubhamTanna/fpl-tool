"""Squad and transfer rules, read from the FPL API at runtime."""
from dataclasses import dataclass

from ..ingest import fpl_api

# The cost of an extra transfer is not in the API. 4 points is the published rule.
HIT_COST = 4


@dataclass(frozen=True)
class Rules:
    squad_count: dict      # position -> players in the squad, e.g. {"GKP": 2, "DEF": 5, ...}
    xi_min: dict           # position -> minimum in the starting XI
    xi_max: dict           # position -> maximum in the starting XI
    squad_size: int
    xi_size: int
    team_limit: int        # max players from one club
    budget: int            # in tenths of a million (1000 = 100.0m)
    max_free_transfers: int
    sell_fee: float        # share of a price rise kept when selling (0.5)
    hit_cost: int = HIT_COST


def load_rules() -> Rules:
    boot = fpl_api.bootstrap()
    r, types = boot["game_settings"], boot["element_types"]
    short = "singular_name_short"
    return Rules(
        squad_count={t[short]: t["squad_select"] for t in types},
        xi_min={t[short]: t["squad_min_play"] for t in types},
        xi_max={t[short]: t["squad_max_play"] for t in types},
        squad_size=r["squad_squadsize"], xi_size=r["squad_squadplay"],
        team_limit=r["squad_team_limit"], budget=r["squad_total_spend"],
        max_free_transfers=1 + r["max_extra_free_transfers"],
        sell_fee=r["transfers_sell_on_fee"],
    )
