"""Expected points (xP) per player per gameweek.

xP is built from separate parts, each estimated on its own and then scored with game_config:
  appearance, goals, assists, clean sheet, goals conceded, saves,
  defensive contribution, bonus, cards.
Not modelled (small): own goals, penalty saves, penalty misses.

The tunable numbers live in dials.py and change only through the backtest.
"""
import re

import numpy as np
import pandas as pd

from .dials import DIALS, Dials
from .scoring import DC_THRESHOLD, load_scoring
from .teams import fit_ratings

RATE_STATS = ["expected_goals", "expected_assists", "defensive_contribution",
              "saves", "bonus", "yellow_cards", "red_cards"]

_FACT = np.cumprod(np.r_[1.0, np.arange(1, 41)])  # 0! .. 40!


def _pois_pmf(lam: np.ndarray) -> np.ndarray:
    """Poisson probabilities, shape (len(lam), 41): P(N = n) for n = 0..40."""
    lam = np.asarray(lam, dtype=float)[:, None]
    n = np.arange(41)[None, :]
    return np.exp(-lam) * lam ** n / _FACT[None, :]


def _exp_floor_div(lam, k: int) -> np.ndarray:
    """E[floor(N / k)] for N ~ Poisson(lam). E.g. -1 point per 2 goals conceded."""
    return (_pois_pmf(lam) * (np.arange(41) // k)).sum(axis=1)


def _prob_at_least(lam, threshold) -> np.ndarray:
    """P(N >= threshold) for N ~ Poisson(lam)."""
    n = np.arange(41)[None, :]
    return (_pois_pmf(lam) * (n >= np.asarray(threshold, dtype=float)[:, None])).sum(axis=1)


def _prob_at_least_nb(mean, threshold, phi: float) -> np.ndarray:
    """P(N >= threshold) when N has the given mean and variance = phi x mean (negative binomial).

    Poisson forces variance = mean. Real match counts vary more than that, which matters
    here because the threshold sits in the upper tail of most players' range.
    """
    mean, threshold = np.asarray(mean, dtype=float), np.asarray(threshold, dtype=float)
    if phi <= 1.0:
        return _prob_at_least(mean, threshold)
    r, q = mean / (phi - 1), 1 - 1 / phi
    pmf = (1 / phi) ** r                       # P(N = 0)
    below = np.zeros_like(mean)                # running P(N < threshold)
    for n in range(41):
        below += np.where(n < threshold, pmf, 0.0)
        pmf = pmf * (n + r) / (n + 1) * q
    return 1 - below


def dc_dispersion(hist: pd.DataFrame, min_matches: int = 3, min_players: int = 30) -> float:
    """Variance / mean of a player's defensive-action count across his own full matches.

    Measured from this season's matches so far, pooled over outfield players with at least
    `min_matches` full 90s. Returns 1.0 (= Poisson) until `min_players` players qualify.
    """
    h = hist[(hist.minutes == 90) & hist.defensive_contribution.notna()]
    g = h.groupby("player_id").defensive_contribution.agg(["mean", "var", "size"])
    g = g[(g["size"] >= min_matches) & (g["mean"] > 0)]
    if len(g) < min_players:
        return 1.0
    w = g["size"] - 1
    return max(1.0, float((g["var"] * w).sum() / (g["mean"] * w).sum()))


def dc_matchup(hist: pd.DataFrame, players: pd.DataFrame, prior_matches: float) -> pd.Series:
    """Defender matchup: how many defensive actions players record AGAINST each club,
    relative to what the same players record in their other matches (their own norm).
    A player with under two full matches elsewhere is compared with his position's average.

    Returns a multiplier indexed by (opponent club, position). 1.2 = opponents of this club
    record 20% more defensive actions than average. Shrunk toward 1.0 by `prior_matches`
    average matches, the same pull the team ratings use.
    """
    h = hist.merge(players[["player_id", "position"]], on="player_id")
    h = h[(h.position != "GKP") & (h.minutes > 0)]
    n90 = h.minutes / 90
    pos_rate = h.groupby("position").defensive_contribution.sum() / n90.groupby(h.position).sum()
    tot = h.groupby("player_id")[["defensive_contribution", "minutes"]].transform("sum")
    other_min = tot.minutes - h.minutes
    own_rate = (tot.defensive_contribution - h.defensive_contribution) / other_min.where(other_min >= 180) * 90
    expected = n90 * own_rate.fillna(h.position.map(pos_rate))
    key = [h.opponent_team_id, h.position]
    obs, exp = h.defensive_contribution.groupby(key).sum(), expected.groupby(key).sum()
    matches = h.groupby(key).fixture_id.nunique()
    k = prior_matches * exp / matches          # what `prior_matches` average matches would add
    return ((obs + k) / (exp + k)).rename("dc_mult")


def conceded_ratio(hist: pd.DataFrame, seasons: pd.DataFrame, w: float = 1.0) -> float:
    """Actual team goals per unit of player-summed xG (last season + this season so far).

    Team goals include own goals, which no player's xG covers, and finishing as it really was.
    """
    prev = seasons[seasons.season_name == seasons.season_name.max()]
    goals = hist.goals_scored.sum() + hist.own_goals.sum() + w * (prev.goals_scored.sum() + prev.own_goals.sum())
    return goals / (hist.expected_goals.sum() + w * prev.expected_goals.sum())


def _weights(hist: pd.DataFrame, half_life: float) -> pd.Series:
    age = hist.groupby("player_id").cumcount(ascending=False)  # 0 = most recent match
    return 0.5 ** (age / half_life)


def minutes_model(hist: pd.DataFrame, players: pd.DataFrame, d: Dials = DIALS) -> pd.DataFrame:
    """P(start), P(sub appearance), minutes when starting / as a sub, P(60+ | start)."""
    h = hist.copy()
    h["w"] = _weights(h, d.minutes_half_life)
    h["start"] = h.starts == 1
    h["sub"] = (h.minutes > 0) & ~h.start
    lg_min_start = h.loc[h.start, "minutes"].mean()
    lg_p60 = (h.loc[h.start, "minutes"] >= 60).mean()
    lg_min_sub = h.loc[h["sub"], "minutes"].mean()
    h["full"] = h.start & (h.minutes >= 90)      # started and finished
    h["part"] = h.start & ~h.full                # started and was taken off
    lg_p_full, lg_min_part = h.loc[h.start, "full"].mean(), h.loc[h.part, "minutes"].mean()

    def wsum(col):
        return (h.w * col).groupby(h.player_id).sum()

    w, ws, wb = wsum(1.0), wsum(h.start), wsum(h["sub"])
    out = pd.DataFrame({
        "p_start": (ws / w).clip(upper=d.max_p_start),
        "p_sub": wb / w,
        # the "+ 2" terms pull small samples toward the league average
        "min_start": (wsum(h.minutes * h.start) + 2 * lg_min_start) / (ws + 2),
        "p60": (wsum((h.minutes >= 60) & h.start) + 2 * lg_p60) / (ws + 2),
        "min_sub": (wsum(h.minutes * h["sub"]) + 2 * lg_min_sub) / (wb + 2),
        "p_full": (wsum(h.full) + 2 * lg_p_full) / (ws + 2),
        "min_part": (wsum(h.minutes * h.part) + 2 * lg_min_part) / (wsum(h.part) + 2),
    })
    out["p_sub"] = np.minimum(out.p_sub, 1 - out.p_start)
    out = out.reindex(players.player_id)
    out[["p_start", "p_sub"]] = out[["p_start", "p_sub"]].fillna(0.0)  # no matches yet
    return out.fillna({"min_start": lg_min_start, "p60": lg_p60, "min_sub": lg_min_sub,
                       "p_full": lg_p_full, "min_part": lg_min_part})


def rate_model(hist: pd.DataFrame, players: pd.DataFrame, seasons: pd.DataFrame,
               d: Dials = DIALS) -> pd.DataFrame:
    """Per-90 rates: recency-weighted this season, blended with a prior.

    prior = last season's per-90 rate, itself shrunk toward this season's position mean.
    A player with no last season (new signing, promoted club) gets the position mean.
    So does a stat that was not recorded last season (blank in `seasons`).
    """
    h = hist.merge(players[["player_id", "position"]], on="player_id")
    h["w"] = _weights(h, d.rate_half_life)
    n90 = h.minutes / 90
    pos_mean = h.groupby("position")[RATE_STATS].sum().div(n90.groupby(h.position).sum(), axis=0)

    prev = seasons[seasons.season_name == seasons.season_name.max()].set_index("player_id")
    prev = prev.reindex(players.player_id)
    pm = pos_mean.loc[players.position].set_axis(players.player_id)
    # minutes behind each stat: 0 where the player or the stat has no last season
    prev_n90 = prev[RATE_STATS].notna().mul(prev.minutes.fillna(0) / 90, axis=0)
    prior = (prev[RATE_STATS].fillna(0) + d.prev_season_shrink * pm) / (prev_n90 + d.prev_season_shrink)

    cur = h[RATE_STATS].mul(h.w, axis=0).groupby(h.player_id).sum().reindex(players.player_id).fillna(0)
    cur_n90 = (h.w * n90).groupby(h.player_id).sum().reindex(players.player_id).fillna(0)
    rates = (cur + d.prior_90s * prior).div(cur_n90 + d.prior_90s, axis=0)
    return rates.add_suffix("_p90")


def conversion_ratios(hist: pd.DataFrame, seasons: pd.DataFrame, w: float = 1.0) -> tuple[float, float]:
    """League-wide goals per xG and FPL assists per xA (last season + this season so far).

    FPL awards assists more generously than xA implies (rebounds, penalties won),
    so xA is scaled up by the observed ratio.
    """
    prev = seasons[seasons.season_name == seasons.season_name.max()]   # w = weight of last season
    g = (hist.goals_scored.sum() + w * prev.goals_scored.sum()) / (hist.expected_goals.sum() + w * prev.expected_goals.sum())
    a = (hist.assists.sum() + w * prev.assists.sum()) / (hist.expected_assists.sum() + w * prev.expected_assists.sum())
    return g, a


def availability(players: pd.DataFrame, events: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """P(available) per player per GW from FPL's injury flags. Rows = players, columns = GWs.

    Next GW:   FPL's chance_of_playing_next_round (blank = 100%).
    Later GWs: if the news gives a date ("Expected back 22 Nov", "Suspended until 5 Dec"),
               0 before that date and 1 after. With no date, hold FPL's chance flat for the
               whole horizon: an injury with an unknown return is not assumed to heal. This is
               a cautious assumption, not a tested one (nobody publishes past injury flags to
               test with). Status "u" (left the club / unavailable) = 0 throughout.
    """
    deadline = events.set_index("gw").deadline_time
    now = deadline[gws[0]]
    base = (players.chance_of_playing_next_round.fillna(100) / 100).to_numpy()
    gone = (players.status == "u").to_numpy()

    def back_date(news):
        m = re.search(r"(?:Expected back|until) (\d{1,2} \w{3})", news or "")
        if not m:
            return pd.NaT
        d = pd.to_datetime(f"{m.group(1)} {now.year}", format="%d %b %Y", utc=True)
        return d + pd.DateOffset(years=1) if d < now - pd.Timedelta(days=180) else d

    back = players.news.map(back_date)
    out = {}
    for k, gw in enumerate(gws):
        if k == 0:
            a = base.copy()
        else:
            a = base.copy()
            # a GW's matches run for about 3 days after its deadline
            dated = np.where(back <= deadline[gw] + pd.Timedelta(days=3), 1.0, 0.0)
            a = np.where(back.notna(), dated, a)
        out[gw] = np.where(gone, 0.0, a)
    return pd.DataFrame(out, index=players.player_id)


def project(tables: dict, as_of_gw: int | None = None, horizon: int = 8,
            use_availability: bool = True, dials: Dials = DIALS, scoring: dict | None = None,
            dc_threshold: dict | None = None, boosts: list[dict] | None = None) -> tuple[pd.DataFrame, dict]:
    """xP for every player for the `horizon` gameweeks after `as_of_gw`.

    Only matches up to and including `as_of_gw` are used, so passing an earlier
    gameweek gives an honest backtest. Returns (one row per player per GW, team ratings).
    `scoring` and `dc_threshold` default to this season's rules; the backtest passes
    the rules of the season it is replaying.

    boosts: Shubham's manual overrides, each {"player_id", "type", "value", "start_gw", "end_gw"}.
      type "output"  multiplies the player's goal and assist points by `value`
      type "minutes" replaces his chance of starting with `value` (0 to 1)
    A boost applies to gameweeks start_gw..end_gw. Boosted rows are marked in the `boosted` column.

    Besides xP and its parts, each row carries the inputs behind them: p_start_used, xmins,
    att_mult (fixture multiplier on goals and assists), p_cs, p_dc, team_xg, opp_xg, and the
    player's blended per-90 rates.
    """
    d = dials
    players, fixtures, events = tables["players"], tables["fixtures"], tables["events"]
    seasons = tables["player_seasons"]
    if as_of_gw is None:
        as_of_gw = int(events.loc[events.finished, "gw"].max())
    hist = tables["player_gw"]
    hist = hist[hist.gw <= as_of_gw].sort_values("kickoff_time")
    gws = [g for g in range(as_of_gw + 1, as_of_gw + 1 + horizon) if g <= events.gw.max()]

    s = scoring or load_scoring()
    dc_threshold = dc_threshold or DC_THRESHOLD
    ratings = fit_ratings(hist, d.team_half_life, d.team_prior_matches)
    att, dfn, mu = ratings["attack"], ratings["defence"], ratings["mu"]
    g_ratio, a_ratio = conversion_ratios(hist, seasons, d.ratio_prev_weight)

    per_player = pd.concat(
        [players.set_index("player_id")[["web_name", "position", "team", "team_id", "now_cost"]],
         minutes_model(hist, players, d), rate_model(hist, players, seasons, d)], axis=1).reset_index()

    # One row per team per upcoming fixture, then one row per player per fixture.
    fx = fixtures[fixtures.gw.isin(gws)]
    home = fx[["gw", "team_h", "team_a"]].set_axis(["gw", "team_id", "opp_id"], axis=1).assign(is_home=True)
    away = fx[["gw", "team_a", "team_h"]].set_axis(["gw", "team_id", "opp_id"], axis=1).assign(is_home=False)
    tf = pd.concat([home, away])
    mu_for = np.where(tf.is_home, ratings["mu_home"], ratings["mu_away"])
    mu_opp = np.where(tf.is_home, ratings["mu_away"], ratings["mu_home"])
    tf["lam_for"] = mu_for * tf.team_id.map(att) * tf.opp_id.map(dfn)        # team's expected goals
    tf["lam_against"] = mu_opp * tf.opp_id.map(att) * tf.team_id.map(dfn)    # expected goals conceded
    tf["att_mult"] = tf.lam_for / (mu * tf.team_id.map(att))                 # fixture vs team's average
    tf["save_mult"] = tf.lam_against / (mu * tf.team_id.map(dfn))
    short = tables["teams"].set_index("team_id").short_name
    tf["opp"] = tf.opp_id.map(short) + np.where(tf.is_home, "(H)", "(A)")

    ratings["team_fixtures"] = tf      # expected goals for/against per team per fixture
    df = per_player.merge(tf, on="team_id")
    if use_availability:
        av = availability(players, events, gws).stack().rename("avail")
        av.index.names = ["player_id", "gw"]
        df = df.merge(av.reset_index(), on=["player_id", "gw"])
    else:
        df["avail"] = 1.0

    df["out_mult"], df["boosted"] = 1.0, False
    for b in boosts or []:
        hit = (df.player_id == b["player_id"]) & df.gw.between(b["start_gw"], b["end_gw"])
        if b["type"] == "minutes":
            df.loc[hit, "p_start"] = float(b["value"])
            df.loc[hit, "p_sub"] = np.minimum(df.loc[hit, "p_sub"], 1 - float(b["value"]))
        elif b["type"] == "output":
            df.loc[hit, "out_mult"] *= float(b["value"])
        df.loc[hit, "boosted"] = True

    pos = df.position
    a_start = df.avail * df.p_start
    share = df.min_start.clip(upper=90) / 90          # share of the match a starter plays
    df["xmins"] = df.avail * (df.p_start * df.min_start + df.p_sub * df.min_sub)
    n90 = df.xmins / 90

    df["xp_app"] = df.avail * (df.p_start * (s["short_play"] + df.p60 * (s["long_play"] - s["short_play"]))
                               + df.p_sub * s["short_play"])
    df["xp_goals"] = df.expected_goals_p90 * df.att_mult * g_ratio * n90 * pos.map(s["goals_scored"]) * df.out_mult
    df["xp_assists"] = df.expected_assists_p90 * df.att_mult * a_ratio * n90 * s["assists"] * df.out_mult
    lam_pts = df.lam_against * (conceded_ratio(hist, seasons, d.ratio_prev_weight) if d.conceded_ratio else 1.0)
    df["p_cs"] = np.exp(-lam_pts * share)
    df["xp_cs"] = a_start * df.p60 * df.p_cs * pos.map(s["clean_sheets"])
    df["xp_conceded"] = a_start * _exp_floor_div(lam_pts * share, 2) * pos.map(s["goals_conceded"])
    saves = df.saves_p90 * df.save_mult * share
    df["xp_saves"] = np.where(pos == "GKP", a_start * _exp_floor_div(saves, 3) * s["saves"], 0.0)
    dc_mean = df.defensive_contribution_p90 * share
    if d.dc_matchup:
        mult = dc_matchup(hist, players, d.team_prior_matches)
        dc_mean = dc_mean * df.join(mult, on=["opp_id", "position"]).dc_mult.fillna(1.0)
    phi = dc_dispersion(hist) if d.dc_dist == "negbin" else 1.0
    thr = pos.map(dc_threshold)
    if d.dc_minutes_mix:
        # the threshold is in the tail, so "90 minutes sometimes, 65 other times" reaches it
        # more often than "80 minutes every time" does
        rate = dc_mean / share
        df["p_dc"] = (df.p_full * _prob_at_least_nb(rate, thr, phi)
                      + (1 - df.p_full) * _prob_at_least_nb(rate * df.min_part / 90, thr, phi))
    else:
        df["p_dc"] = _prob_at_least_nb(dc_mean, thr, phi)
    df["xp_dc"] = a_start * df.p_dc * pos.map(s["defensive_contribution"])
    df["xp_bonus"] = df.bonus_p90 * n90 * s["bonus"]
    df["xp_cards"] = (df.yellow_cards_p90 * s["yellow_cards"] + df.red_cards_p90 * s["red_cards"]) * n90
    parts = [c for c in df.columns if c.startswith("xp_")]
    df["xp"] = df[parts].sum(axis=1)

    # One row per player per GW: doubles sum both fixtures, blanks get 0.
    agg = df.groupby(["player_id", "gw"]).agg(
        opp=("opp", " + ".join), n_fixtures=("opp", "size"), xmins=("xmins", "sum"),
        p_start_used=("p_start", "mean"), avail=("avail", "mean"), att_mult=("att_mult", "mean"),
        p_cs=("p_cs", "mean"), p_dc=("p_dc", "mean"), team_xg=("lam_for", "sum"), opp_xg=("lam_against", "sum"),
        boosted=("boosted", "max"),
        **{c: (c, "sum") for c in parts}, xp=("xp", "sum")).reset_index()
    grid = pd.MultiIndex.from_product([players.player_id, gws], names=["player_id", "gw"]).to_frame(index=False)
    out = grid.merge(agg, on=["player_id", "gw"], how="left")
    out["opp"] = out.opp.fillna("-")
    out["boosted"] = out.boosted.fillna(False).astype(bool)
    out = out.fillna(0.0)
    out["n_fixtures"] = out.n_fixtures.astype(int)
    rates = {"expected_goals_p90": "xg_p90", "expected_assists_p90": "xa_p90",
             "defensive_contribution_p90": "dc_p90", "saves_p90": "saves_p90", "bonus_p90": "bonus_p90"}
    info = per_player[["player_id", "web_name", "position", "team", "now_cost", "p_start", "p_sub",
                       "min_start", "p60", *rates]].rename(columns=rates)
    return info.merge(out, on="player_id"), ratings
