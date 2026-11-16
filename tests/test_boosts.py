"""Boost records and how a boost changes the projection."""
import pandas as pd
import pytest

from fpl.ingest.cache import PROCESSED_DIR
from fpl.model.scoring import DC_THRESHOLD
from fpl.model.xp import project
from fpl.user import boosts as bo

SCORING = {"long_play": 2, "short_play": 1, "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
           "assists": 3, "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
           "goals_conceded": {"GKP": -1, "DEF": -1, "MID": 0, "FWD": 0}, "saves": 1,
           "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2}, "bonus": 1,
           "yellow_cards": -1, "red_cards": -3}
NAMES = ["teams", "players", "fixtures", "events", "player_gw", "player_seasons"]


def test_add_validates_and_logs():
    log, errs = bo.add([], 7, "Player", "output", 1.2, 11, 13, "eye test")
    assert errs == [] and log[0]["id"] == 1 and log[0]["created_at"] and log[0]["cancelled_at"] is None
    assert bo.add(log, 7, "Player", "output", 5.0, 11, 13, "x")[1]          # value out of range
    assert bo.add(log, 7, "Player", "minutes", 1.5, 11, 13, "x")[1]
    assert bo.add(log, 7, "Player", "output", 1.1, 13, 12, "x")[1]          # ends before it starts
    assert bo.add(log, 7, "Player", "output", 1.1, 11, 12, "  ")[1]         # reason required
    assert bo.add(log, 7, "Player", "output", 1.1, 13, 15, "x")[1]          # overlaps the first
    assert bo.add(log, 7, "Player", "minutes", 0.9, 11, 13, "other type is fine")[1] == []


def test_cancel_keeps_the_record_and_played_gameweeks():
    log, _ = bo.add([], 7, "Player", "output", 1.2, 9, 14, "eye test")
    log = bo.cancel(log, 1, last_finished_gw=10)
    assert len(log) == 1 and log[0]["end_gw"] == 10 and log[0]["cancelled_at"]
    assert bo.ended(log, 10) == log and bo.live(log, 11) == []
    never, _ = bo.add([], 7, "Player", "output", 1.2, 11, 14, "eye test")
    never = bo.cancel(never, 1, last_finished_gw=10)
    assert bo.for_model(never) == [] and len(never) == 1                     # still in the log


@pytest.fixture(scope="module")
def tables():
    if not (PROCESSED_DIR / "players.parquet").exists():
        pytest.skip("no processed data on disk")
    return {n: pd.read_parquet(PROCESSED_DIR / f"{n}.parquet") for n in NAMES}


def _project(tables, boosts=None):
    out, _ = project(tables, horizon=3, use_availability=False, scoring=SCORING, dc_threshold=DC_THRESHOLD,
                     boosts=boosts)
    return out.set_index(["player_id", "gw"])


def test_output_boost_scales_only_goals_and_assists_in_its_gameweeks(tables):
    base = _project(tables)
    pid = base.xp_goals.groupby("player_id").sum().idxmax()
    g1, g2, g3 = sorted(base.index.get_level_values("gw").unique())
    new = _project(tables, [{"player_id": pid, "type": "output", "value": 1.5, "start_gw": g1, "end_gw": g2}])
    for g in (g1, g2):
        assert new.loc[(pid, g), "xp_goals"] == pytest.approx(1.5 * base.loc[(pid, g), "xp_goals"])
        assert new.loc[(pid, g), "xp_assists"] == pytest.approx(1.5 * base.loc[(pid, g), "xp_assists"])
        assert new.loc[(pid, g), "xp_app"] == pytest.approx(base.loc[(pid, g), "xp_app"])
        assert new.loc[(pid, g), "boosted"]
    assert new.loc[(pid, g3), "xp"] == pytest.approx(base.loc[(pid, g3), "xp"])     # after the end gameweek
    assert not new.loc[(pid, g3), "boosted"]
    others = new.drop(index=pid, level="player_id").xp
    assert others.equals(base.drop(index=pid, level="player_id").xp)                # nobody else moves


def test_minutes_boost_overrides_chance_of_starting(tables):
    base = _project(tables)
    g1 = base.index.get_level_values("gw").min()
    first = base.xs(g1, level="gw")
    pid = first[(first.p_start_used > 0.3) & (first.p_start_used < 0.6) & (first.n_fixtures == 1)].index[0]
    new = _project(tables, [{"player_id": pid, "type": "minutes", "value": 1.0, "start_gw": g1, "end_gw": g1}])
    assert new.loc[(pid, g1), "p_start_used"] == pytest.approx(1.0)
    assert new.loc[(pid, g1), "xmins"] > base.loc[(pid, g1), "xmins"]
    assert new.loc[(pid, g1), "xp"] > base.loc[(pid, g1), "xp"]
