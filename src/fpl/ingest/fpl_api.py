"""FPL API fetchers (all cached through cache.fetch_json)."""
from .cache import fetch_json

BASE = "https://fantasy.premierleague.com/api/"


def bootstrap(max_age_hours: float = 6.0) -> dict:
    return fetch_json("bootstrap-static", BASE + "bootstrap-static/", max_age_hours)


def fixtures(max_age_hours: float = 6.0) -> list:
    return fetch_json("fixtures", BASE + "fixtures/", max_age_hours)


def element_summary(player_id: int, max_age_hours: float = 24.0) -> dict:
    return fetch_json(
        f"element-summary/{player_id}",
        f"{BASE}element-summary/{player_id}/",
        max_age_hours,
    )
