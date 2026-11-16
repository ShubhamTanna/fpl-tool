"""Team attack and defence ratings from xG.

Model: expected goals for team i against team j
    = (league average xG at that venue) x attack_i x defence_j
attack > 1 = creates more xG than average. defence > 1 = concedes more than average (worse).

Each rating is a recency-weighted ratio of actual xG to what an average team would have
produced against the same opponents and venues, shrunk toward 1.0 by PRIOR_MATCHES
"average" matches so that ten games do not produce extreme ratings.
"""
import pandas as pd

HALF_LIFE = 8        # matches; a game 8 matches ago counts half as much as the latest
PRIOR_MATCHES = 3    # strength of the pull toward league average


def team_matches(player_gw: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match: xG for and against (sum of player xG)."""
    tm = (player_gw.groupby(["fixture_id", "team_id", "opponent_team_id", "was_home", "gw"], as_index=False)
          .agg(xg_for=("expected_goals", "sum"), kickoff_time=("kickoff_time", "first")))
    opp = tm[["fixture_id", "team_id", "xg_for"]].rename(
        columns={"team_id": "opponent_team_id", "xg_for": "xg_against"})
    tm = tm.merge(opp, on=["fixture_id", "opponent_team_id"], validate="1:1")
    tm = tm.sort_values("kickoff_time")
    age = tm.groupby("team_id").cumcount(ascending=False)
    tm["w"] = 0.5 ** (age / HALF_LIFE)
    return tm


def fit_ratings(player_gw: pd.DataFrame, n_iter: int = 30) -> dict:
    tm = team_matches(player_gw)
    mu_home = tm.loc[tm.was_home, "xg_for"].mean()
    mu_away = tm.loc[~tm.was_home, "xg_for"].mean()
    mu = (mu_home + mu_away) / 2
    tm["mu_for"] = tm.was_home.map({True: mu_home, False: mu_away})      # venue average for this team
    tm["mu_against"] = tm.was_home.map({True: mu_away, False: mu_home})  # venue average for the opponent

    teams = sorted(tm.team_id.unique())
    att = pd.Series(1.0, index=teams)
    dfn = pd.Series(1.0, index=teams)
    k = PRIOR_MATCHES * mu
    for _ in range(n_iter):  # attack depends on opponents' defence and vice versa, so iterate
        exp_for = tm.w * tm.mu_for * tm.opponent_team_id.map(dfn)
        att = ((tm.w * tm.xg_for).groupby(tm.team_id).sum() + k) / (exp_for.groupby(tm.team_id).sum() + k)
        exp_against = tm.w * tm.mu_against * tm.opponent_team_id.map(att)
        dfn = ((tm.w * tm.xg_against).groupby(tm.team_id).sum() + k) / (exp_against.groupby(tm.team_id).sum() + k)
        att, dfn = att / att.mean(), dfn / dfn.mean()
    return {"attack": att, "defence": dfn, "mu_home": mu_home, "mu_away": mu_away, "mu": mu}
