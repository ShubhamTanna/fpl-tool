"""Team loader: squad, bank, free transfers, sell prices and transfers already made."""
import pandas as pd

from fpl.ingest.team import build_team

PLAYERS = pd.DataFrame({"player_id": range(1, 18), "now_cost": [50] * 15 + [60, 70],
                        "cost_change_start": [0] * 17})
PLAYERS.loc[PLAYERS.player_id == 2, ["now_cost", "cost_change_start"]] = [57, 7]   # risen 0.7m since GW1
PLAYERS.loc[PLAYERS.player_id == 3, ["now_cost", "cost_change_start"]] = [46, -4]  # fallen 0.4m
PLAYER_GW = pd.DataFrame({"player_id": range(1, 18), "gw": 1, "value": [50] * 15 + [60, 70]})
ENTRY = {"id": 1, "name": "Test FC", "started_event": 1}


def _history(transfers_by_gw: dict, chips=()):
    return {"chips": [{"event": g, "name": n} for g, n in chips],
            "current": [{"event": g, "event_transfers": transfers_by_gw.get(g, 0), "points": 50,
                         "event_transfers_cost": 0} for g in range(1, 4)]}


def _picks(squad, bank=10):
    return {"picks": [{"element": i} for i in squad], "entry_history": {"bank": bank, "value": 1000}}


def _team(transfers, history, squad=tuple(range(1, 16))):
    return build_team(ENTRY, history, transfers, {3: _picks(squad)}, PLAYERS, PLAYER_GW, as_of_gw=3)


def test_free_transfers_roll_and_cap():
    assert _team([], _history({}))["free_transfers"] == 3            # 1, then +1 after GW2 and GW3
    assert _team([], _history({2: 1, 3: 1}))["free_transfers"] == 1  # used every week


def test_wildcard_week_leaves_count_unchanged():
    assert _team([], _history({2: 6}, chips=[(2, "wildcard")]))["free_transfers"] == 2


def test_sell_price_keeps_half_of_a_rise_rounded_down():
    t = _team([], _history({}))
    assert t["purchase_price"][2] == 50 and t["sell_price"][2] == 53   # 50 + floor(7 / 2)
    assert t["sell_price"][3] == 46                                     # a fall is passed on in full
    assert t["sell_price"][1] == 50


def test_pending_transfer_is_applied():
    pending = [{"event": 4, "time": "2026-09-01T10:00:00Z", "element_out": 1, "element_out_cost": 50,
                "element_in": 16, "element_in_cost": 60}]
    t = _team(pending, _history({}))
    assert 16 in t["squad"] and 1 not in t["squad"] and len(t["squad"]) == 15
    assert t["bank"] == 0                       # 10 + 50 - 60
    assert t["free_transfers"] == 2 and t["hits_taken"] == 0
    assert t["pending"] == [(1, 16)]
    assert t["purchase_price"][16] == 60


def test_pending_transfers_beyond_free_ones_count_as_hits():
    pending = [{"event": 4, "time": f"2026-09-01T1{k}:00:00Z", "element_out": k + 1, "element_out_cost": 50,
                "element_in": 16 + k, "element_in_cost": 50} for k in range(2)]
    t = _team(pending, _history({2: 1, 3: 1}))  # only 1 free transfer available
    assert t["free_transfers"] == 0 and t["hits_taken"] == 1


def test_old_transfers_are_not_applied_twice():
    old = [{"event": 3, "time": "2026-08-20T10:00:00Z", "element_out": 17, "element_out_cost": 70,
            "element_in": 5, "element_in_cost": 48}]
    t = _team(old, _history({3: 1}))
    assert sorted(t["squad"]) == list(range(1, 16)) and t["bank"] == 10
    assert t["purchase_price"][5] == 48
