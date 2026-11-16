"""Scout lists: ranked candidates to look at. None of these rules has been backtested.

The thresholds are first guesses. Edit them here; the page prints whatever is set.
"""
import pandas as pd

from .ticker import fixture_ticker

# minutes rising
RISE_WINDOW = 3            # last 3 club matches against the 3 before
MIN_MINUTES_RISE = 90      # at least one full match more than in the earlier window
MIN_RECENT_MINUTES = 180   # and at least two full matches' worth in the recent window
# value
VALUE_TOP_N = 10           # per position
VALUE_MIN_START = 0.6      # chance of starting next gameweek, after injury flags
# fixture swing
SWING_WINDOW = 5           # next 5 gameweeks against the last 5
SWING_TOP_CLUBS = 5
SWING_PLAYERS_PER_CLUB = 3


def minutes_rising(player_gw: pd.DataFrame) -> pd.DataFrame:
    """Players whose starts AND minutes went up over the last 3 club matches against the 3 before."""
    h = player_gw.sort_values("kickoff_time")
    last = h.groupby("player_id").tail(RISE_WINDOW)
    prev = h.groupby("player_id").tail(2 * RISE_WINDOW).groupby("player_id").head(RISE_WINDOW)
    n = h.groupby("player_id").size()
    df = pd.DataFrame({
        "starts_last3": last.groupby("player_id").starts.sum(), "starts_prev3": prev.groupby("player_id").starts.sum(),
        "mins_last3": last.groupby("player_id").minutes.sum(), "mins_prev3": prev.groupby("player_id").minutes.sum()})
    df = df[n.reindex(df.index) >= 2 * RISE_WINDOW]
    df["minutes_rise"] = df.mins_last3 - df.mins_prev3
    keep = ((df.starts_last3 > df.starts_prev3) & (df.minutes_rise >= MIN_MINUTES_RISE)
            & (df.mins_last3 >= MIN_RECENT_MINUTES))
    return df[keep].sort_values("minutes_rise", ascending=False).reset_index()


def value(proj: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """Best xP per million over `gws`, top VALUE_TOP_N per position, likely starters only."""
    d = proj[proj.gw.isin(gws)]
    first = d[d.gw == gws[0]].set_index("player_id")
    agg = d.groupby(["player_id", "position", "now_cost"], as_index=False).xp.sum()
    agg["start"] = agg.player_id.map(first.p_start_used * first.avail)
    agg["xp_per_m"] = agg.xp / (agg.now_cost / 10)
    agg = agg[agg.start >= VALUE_MIN_START]
    return (agg.sort_values("xp_per_m", ascending=False).groupby("position").head(VALUE_TOP_N)
            .sort_values(["position", "xp_per_m"], ascending=[True, False]).reset_index(drop=True))


def fixture_swing(player_gw: pd.DataFrame, fixtures: pd.DataFrame, teams: pd.DataFrame,
                  next_gws: list[int]) -> pd.DataFrame:
    """Per club: expected goals for and against per match, last SWING_WINDOW gameweeks vs the next.

    Both windows are priced with today's team ratings, so the swing is purely the change in
    opponents and venues. attack_swing > 0 = scoring outlook improves; defence_swing > 0 =
    fewer goals expected against.
    """
    nxt = next_gws[:SWING_WINDOW]
    last = list(range(nxt[0] - SWING_WINDOW, nxt[0]))
    t = fixture_ticker(player_gw, fixtures, teams, last + nxt)

    def per_match(gws: list[int]) -> pd.DataFrame:
        g = t[t.gw.isin(gws)].groupby("team")[["xg_for", "xg_against", "n_fixtures"]].sum()
        return g[["xg_for", "xg_against"]].div(g.n_fixtures, axis=0)

    a, b = per_match(last), per_match(nxt)
    fx = t[t.gw.isin(nxt)].sort_values("gw").groupby("team").opp.agg(", ".join)
    out = pd.DataFrame({"last_for": a.xg_for, "next_for": b.xg_for, "attack_swing": b.xg_for - a.xg_for,
                        "last_against": a.xg_against, "next_against": b.xg_against,
                        "defence_swing": a.xg_against - b.xg_against, "fixtures": fx})
    return out.rename_axis("team").reset_index()
