"""Past seasons from GitHub vaastav/Fantasy-Premier-League, in one table with the live season.

Output: data/processed/history_gw.parquet - one row per player per match, all seasons.
Players are keyed by `code` (stable across seasons); `player_id` changes every season.

Checked 16 Nov 2026:
  2022-23  xG and starts are only filled from GW16, so earlier rows are dropped. The season
           is used as "last season" for 2023-24, not as a season to replay.
  2024-25  has assistant-manager rows (position AM); dropped.
  2025-26  has 10 duplicated player-match rows; dropped. First season with defensive_contribution.
"""
import time

import pandas as pd
import requests

from .cache import HEADERS, MIN_INTERVAL, PROCESSED_DIR, RAW_DIR

URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/{file}"
PAST_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
LIVE_SEASON = "2026-27"
FIRST_GW_WITH_XG = {"2022-23": 16}
FILES = {"merged_gw.csv": "gws/merged_gw.csv", "players_raw.csv": "players_raw.csv", "teams.csv": "teams.csv"}

STATS = ["minutes", "starts", "goals_scored", "assists", "clean_sheets", "goals_conceded", "own_goals",
         "penalties_saved", "penalties_missed", "yellow_cards", "red_cards", "saves", "bonus", "bps",
         "expected_goals", "expected_assists", "expected_goals_conceded", "defensive_contribution",
         "total_points"]
KEYS = ["season", "code", "player_id", "web_name", "position", "team_id", "team", "opponent_team_id",
        "fixture_id", "gw", "was_home", "kickoff_time", "value"]


def _download(season: str) -> dict[str, pd.DataFrame]:
    """Past seasons never change, so a file on disk is never re-fetched."""
    out = {}
    for local, remote in FILES.items():
        path = RAW_DIR / "vaastav" / season / local
        if not path.exists() or path.stat().st_size == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(URL.format(season=season, file=remote), headers=HEADERS, timeout=60)
            r.raise_for_status()
            path.write_bytes(r.content)
            time.sleep(MIN_INTERVAL)
        out[local] = pd.read_csv(path)
    return out


def load_past_season(season: str) -> pd.DataFrame:
    f = _download(season)
    gw, raw, teams = f["merged_gw.csv"], f["players_raw.csv"], f["teams.csv"]
    gw = gw[gw.position != "AM"].drop_duplicates(["element", "fixture"])
    gw = gw[gw.GW >= FIRST_GW_WITH_XG.get(season, 1)]
    gw = gw.rename(columns={"element": "player_id", "fixture": "fixture_id", "GW": "gw",
                            "opponent_team": "opponent_team_id", "team": "team_name"})
    gw = gw.merge(raw[["id", "code", "web_name"]].rename(columns={"id": "player_id"}), on="player_id",
                  validate="m:1")
    gw = gw.merge(teams[["id", "name", "short_name"]].rename(
        columns={"id": "team_id", "name": "team_name", "short_name": "team"}), on="team_name", validate="m:1")
    gw["position"] = gw.position.replace({"GK": "GKP"})
    gw["season"] = season
    gw["kickoff_time"] = pd.to_datetime(gw.kickoff_time, utc=True)
    if "defensive_contribution" not in gw:
        gw["defensive_contribution"] = float("nan")   # stat did not exist before 2025-26
    return gw[KEYS + STATS]


def load_live_season() -> pd.DataFrame:
    """The current season, from the tables the data layer already builds."""
    pg = pd.read_parquet(PROCESSED_DIR / "player_gw.parquet")
    players = pd.read_parquet(PROCESSED_DIR / "players.parquet")
    teams = pd.read_parquet(PROCESSED_DIR / "teams.parquet")
    pg = pg.merge(players[["player_id", "code", "web_name", "position"]], on="player_id", validate="m:1")
    pg = pg.merge(teams[["team_id", "short_name"]].rename(columns={"short_name": "team"}), on="team_id")
    pg["season"] = LIVE_SEASON
    return pg[KEYS + STATS]


def build_history() -> pd.DataFrame:
    df = pd.concat([load_past_season(s) for s in PAST_SEASONS] + [load_live_season()], ignore_index=True)
    df["defensive_contribution"] = df.defensive_contribution.astype(float)
    df.to_parquet(PROCESSED_DIR / "history_gw.parquet", index=False)
    return df
