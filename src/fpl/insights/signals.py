"""Underperformer signal (the Barry method): attackers creating chances that have not yet
turned into goals and assists, with secure minutes and low ownership.

This is a list to review, not an auto-buy. The method has not been backtested.
The thresholds are first guesses - edit them here.
"""
import pandas as pd

MIN_MINUTES = 360          # at least four full matches of data
XGI_PERCENTILE = 0.75      # xGI/90 in the top quarter of his position
MIN_GAP = 1.0              # actual goals + assists at least 1.0 below xGI
MAX_OWNERSHIP = 10.0       # owned by under 10% of all managers
SECURE_STARTS = 4          # started at least 4 of his club's last 5 matches


def underperformers(players: pd.DataFrame, player_gw: pd.DataFrame, flagged_only: bool = True) -> pd.DataFrame:
    h = player_gw.sort_values("kickoff_time")
    last5 = h.groupby("player_id").tail(5)
    starts5 = last5.groupby("player_id").starts.sum().rename("starts_last5")
    mins3 = h.groupby("player_id").tail(3).groupby("player_id").minutes.sum().rename("mins_last3")
    prev3 = (h.groupby("player_id").tail(6).groupby("player_id").head(3)
             .groupby("player_id").minutes.sum().rename("mins_prev3"))

    p = players[players.position.isin(["MID", "FWD"]) & (players.minutes >= MIN_MINUTES)
                & (players.status != "u")].set_index("player_id")
    p = p.join([starts5, mins3, prev3])
    df = pd.DataFrame({
        "web_name": p.web_name, "position": p.position, "team": p.team, "price": p.now_cost / 10,
        "minutes": p.minutes, "owned_pct": p.selected_by_percent,
        "xgi": p.expected_goal_involvements, "g_a": p.goals_scored + p.assists,
        "xgi_p90": p.expected_goal_involvements / p.minutes * 90,
        "starts_last5": p.starts_last5, "mins_last3": p.mins_last3, "mins_prev3": p.mins_prev3,
        "status": p.status,
    })
    df["gap"] = df.g_a - df.xgi                                   # negative = underperforming
    cut = df.groupby("position").xgi_p90.transform(lambda s: s.quantile(XGI_PERCENTILE))
    df["high_xgi"] = df.xgi_p90 >= cut
    df["underperforming"] = df.gap <= -MIN_GAP
    rising = (df.mins_last3 >= df.mins_prev3 + 60) & (df.mins_last3 >= 180)
    df["secure_or_rising"] = (df.starts_last5 >= SECURE_STARTS) | rising
    df["low_owned"] = df.owned_pct < MAX_OWNERSHIP
    tests = ["high_xgi", "underperforming", "secure_or_rising", "low_owned"]
    df["tests_passed"] = df[tests].sum(axis=1)
    df["flag"] = df.tests_passed == len(tests)
    df = df.sort_values(["flag", "gap"], ascending=[False, True]).reset_index()
    return df[df.flag] if flagged_only else df
