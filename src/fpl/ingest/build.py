"""Build the clean tables in data/processed/ from the FPL API.

Tables
  teams      one row per club
  players    one row per player (current snapshot)
  fixtures   one row per fixture, past and upcoming
  events     one row per gameweek (deadline, finished flag)
  player_gw  one row per player per fixture of his club this season
             (minutes = 0 rows are kept: the minutes model needs them)
  player_seasons  one row per player per past season (season totals)
"""
import pandas as pd

from . import fpl_api
from .cache import PROCESSED_DIR

# FPL sends these as strings; store them as numbers.
PLAYER_FLOAT_COLS = [
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "influence", "creativity", "threat", "ict_index",
    "form", "points_per_game", "selected_by_percent", "value_form", "value_season",
    "ep_next", "ep_this",
]
GW_FLOAT_COLS = [
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "influence", "creativity", "threat", "ict_index",
]


def build_teams(boot: dict) -> pd.DataFrame:
    cols = ["id", "code", "name", "short_name", "strength",
            "strength_overall_home", "strength_overall_away",
            "strength_attack_home", "strength_attack_away",
            "strength_defence_home", "strength_defence_away"]
    return pd.DataFrame(boot["teams"])[cols].rename(columns={"id": "team_id"})


def build_players(boot: dict, teams: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(boot["elements"]).rename(columns={"id": "player_id", "team": "team_id"})
    pos = {t["id"]: t["singular_name_short"] for t in boot["element_types"]}
    df["position"] = df["element_type"].map(pos)
    df = df.merge(teams[["team_id", "short_name"]].rename(columns={"short_name": "team"}),
                  on="team_id", how="left", validate="m:1")
    df[PLAYER_FLOAT_COLS] = df[PLAYER_FLOAT_COLS].apply(pd.to_numeric, errors="coerce")
    for c in df.columns:  # nested/mixed columns do not fit parquet cleanly
        if df[c].map(lambda v: isinstance(v, (list, dict))).any():
            df[c] = df[c].astype(str)
    first = ["player_id", "web_name", "first_name", "second_name", "position", "team", "team_id"]
    return df[first + [c for c in df.columns if c not in first]]


def build_fixtures(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw).drop(columns=["stats"])
    df = df.rename(columns={"id": "fixture_id", "event": "gw"})
    df["kickoff_time"] = pd.to_datetime(df["kickoff_time"], utc=True)
    df["gw"] = df["gw"].astype("Int64")  # null = fixture not yet scheduled
    return df


def build_events(boot: dict) -> pd.DataFrame:
    cols = ["id", "deadline_time", "finished", "is_current", "is_next"]
    df = pd.DataFrame(boot["events"])[cols].rename(columns={"id": "gw"})
    df["deadline_time"] = pd.to_datetime(df["deadline_time"], utc=True)
    return df


def build_player_history(player_ids: list[int], fixtures: pd.DataFrame, log_every: int = 50,
                         max_age_hours: float = 24.0, progress=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (player_gw, player_seasons) from the element-summary endpoint.
    progress: optional callback(done, total), called after every player."""
    rows, past = [], []
    for i, pid in enumerate(player_ids, 1):
        summary = fpl_api.element_summary(pid, max_age_hours)
        if progress:
            progress(i, len(player_ids))
        rows.extend(summary["history"])
        past.extend({"player_id": pid, **h} for h in summary["history_past"])
        if i % log_every == 0:
            print(f"  element-summary {i}/{len(player_ids)}", flush=True)
    df = pd.DataFrame(rows).rename(
        columns={"element": "player_id", "fixture": "fixture_id", "round": "gw",
                 "opponent_team": "opponent_team_id"})
    df[GW_FLOAT_COLS] = df[GW_FLOAT_COLS].apply(pd.to_numeric, errors="coerce")
    df["kickoff_time"] = pd.to_datetime(df["kickoff_time"], utc=True)
    # Club the player belonged to for this match (differs from his current club after a move).
    fx = fixtures.set_index("fixture_id")
    home, away = df["fixture_id"].map(fx["team_h"]), df["fixture_id"].map(fx["team_a"])
    df["team_id"] = home.where(df["was_home"], away)

    seasons = pd.DataFrame(past)
    seasons[GW_FLOAT_COLS] = seasons[GW_FLOAT_COLS].apply(pd.to_numeric, errors="coerce")
    return df, seasons


def build_all(max_age_hours: float = 6.0, history_max_age_hours: float = 24.0,
              progress=None) -> dict[str, pd.DataFrame]:
    boot = fpl_api.bootstrap(max_age_hours)
    teams = build_teams(boot)
    players = build_players(boot, teams)
    fixtures = build_fixtures(fpl_api.fixtures(max_age_hours))
    player_gw, player_seasons = build_player_history(
        players["player_id"].tolist(), fixtures, max_age_hours=history_max_age_hours, progress=progress)
    tables = {"teams": teams, "players": players, "fixtures": fixtures, "events": build_events(boot),
              "player_gw": player_gw, "player_seasons": player_seasons}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
    return tables
