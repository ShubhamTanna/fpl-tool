"""Scoring rules, read from the FPL game_config at runtime (never hardcoded)."""
import numpy as np
import pandas as pd

from ..ingest import fpl_api

# Defensive-contribution thresholds are NOT in game_config.
# Confirmed against GW1-10 of 2026-27 by rebuilding every match score:
#   DEF: 10 CBIT (lowest count that scored = 10, highest that did not = 9)
#   MID: 12 CBIRT (lowest that scored = 12, highest that did not = 11)
#   FWD: 12 CBIRT is the 2025/26 rule. This season's data only narrows it to 11-16
#        (one forward has scored, with 16), so 12 is an assumption that fits the data.
DC_THRESHOLD = {"GKP": np.inf, "DEF": 10, "MID": 12, "FWD": 12}


def load_scoring() -> dict:
    return fpl_api.bootstrap()["game_config"]["scoring"]


def actual_points(df: pd.DataFrame, s: dict) -> pd.Series:
    """Rebuild FPL points for match rows (needs a `position` column). Used to verify the rules."""
    pos = df["position"]
    played = df["minutes"] > 0
    dc_hit = df["defensive_contribution"] >= pos.map(DC_THRESHOLD)
    pts = (
        np.where(df["minutes"] >= 60, s["long_play"], s["short_play"])
        + df["goals_scored"] * pos.map(s["goals_scored"])
        + df["assists"] * s["assists"]
        + df["clean_sheets"] * pos.map(s["clean_sheets"])
        + (df["goals_conceded"] // 2) * pos.map(s["goals_conceded"])
        + (df["saves"] // 3) * s["saves"]
        + df["penalties_saved"] * s["penalties_saved"]
        + df["penalties_missed"] * s["penalties_missed"]
        + df["yellow_cards"] * s["yellow_cards"]
        + df["red_cards"] * s["red_cards"]
        + df["own_goals"] * s["own_goals"]
        + df["bonus"] * s["bonus"]
        + dc_hit * pos.map(s["defensive_contribution"])
    )
    return pts.where(played, 0)
