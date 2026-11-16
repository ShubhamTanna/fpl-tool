"""Draft rules: budget, positions, 3-per-club, and squad history."""
import pandas as pd

from fpl.optimize.rules import Rules
from fpl.user import drafts, store

RULES = Rules(squad_count={"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}, xi_min={"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1},
              xi_max={"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}, squad_size=15, xi_size=11, team_limit=3,
              budget=1000, max_free_transfers=5, sell_fee=0.5)
POS = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
# ids 1-15 = a legal squad spread over 5 clubs; 16-19 = candidates
PLAYERS = pd.DataFrame({
    "player_id": range(1, 20), "position": POS + ["MID", "MID", "DEF", "MID"],
    "team": [f"T{k % 5}" for k in range(15)] + ["T9", "T0", "T9", "T9"],
    "now_cost": [50] * 15 + [55, 50, 50, 90]})
SQUAD = list(range(1, 16))


def _draft(budget=760):
    return drafts.new_draft([], "test", 11, "", SQUAD, {i: 50 for i in SQUAD}, budget, "copy")


def test_new_draft_is_legal_and_has_money_left():
    d = _draft()
    assert drafts.check_draft(SQUAD, drafts.spent(d), d["budget"], PLAYERS, RULES) == []
    assert drafts.remaining(d) == 10


def test_swap_within_budget_is_applied_from_the_effective_gameweek():
    d, errs = drafts.swap(_draft(), 8, 16, PLAYERS, RULES, effective_gw=13)
    assert errs == []
    assert 16 in drafts.current_squad(d) and 8 not in drafts.current_squad(d)
    assert drafts.remaining(d) == 5                      # 10 + 50 - 55
    assert 8 in drafts.squad_at(d, 12) and 16 in drafts.squad_at(d, 13)   # history is kept


def test_swap_over_budget_is_refused():
    d0 = _draft()
    d, errs = drafts.swap(d0, 8, 19, PLAYERS, RULES, 11)   # 9.0m player with 1.0m in the bank
    assert d is d0 and any("over budget" in e for e in errs)


def test_swap_must_keep_position():
    d, errs = drafts.swap(_draft(), 8, 18, PLAYERS, RULES, 11)   # MID out, DEF in
    assert errs and drafts.current_squad(d) == SQUAD


def test_swap_cannot_exceed_three_per_club():
    # T0 already has players 1, 6, 11; player 17 is a T0 midfielder replacing a T2 midfielder
    d, errs = drafts.swap(_draft(), 8, 17, PLAYERS, RULES, 11)
    assert any("max 3" in e for e in errs)


def test_swap_rejects_duplicates_and_strangers():
    assert drafts.swap(_draft(), 8, 9, PLAYERS, RULES, 11)[1]
    assert drafts.swap(_draft(), 16, 17, PLAYERS, RULES, 11)[1]


def test_store_round_trip_and_export(tmp_path):
    d = _draft()
    store.save("drafts", [d], tmp_path)
    back = store.load("drafts", [], tmp_path)
    assert back == [d] and drafts.squad_at(back[0], 11) == SQUAD
    assert store.load("missing", [], tmp_path) == []
    assert len(store.export_zip(tmp_path)) > 0
