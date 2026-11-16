"""Expected points (xP) per player per gameweek.

xP is built from separate parts, each estimated on its own and then scored with game_config:
  appearance, goals, assists, clean sheet, goals conceded, saves,
  defensive contribution, bonus, cards.
Not modelled (small): own goals, penalty saves, penalty misses.

All constants below are judgement calls, not fitted values. They have not been tuned
to any backtest.
"""
import re

import numpy as np
import pandas as pd

from .scoring import DC_THRESHOLD, load_scoring
from .teams import fit_ratings

MINUTES_HALF_LIFE = 3    # matches: minutes change fast, so recent games dominate
RATE_HALF_LIFE = 8       # matches: per-90 output is noisy, so use a longer memory
PRIOR_90S = 5            # this-season rate is blended with a prior worth 5 full matches
PREV_SEASON_SHRINK = 5   # last season's rate is itself pulled to the position mean by 5 matches
MAX_P_START = 0.95       # nobody is a certain starter
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


def _weights(hist: pd.DataFrame, half_life: float) -> pd.Series:
    age = hist.groupby("player_id").cumcount(ascending=False)  # 0 = most recent match
    return 0.5 ** (age / half_life)


def minutes_model(hist: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """P(start), P(sub appearance), minutes when starting / as a sub, P(60+ | start)."""
    h = hist.copy()
    h["w"] = _weights(h, MINUTES_HALF_LIFE)
    h["start"] = h.starts == 1
    h["sub"] = (h.minutes > 0) & ~h.start
    lg_min_start = h.loc[h.start, "minutes"].mean()
    lg_p60 = (h.loc[h.start, "minutes"] >= 60).mean()
    lg_min_sub = h.loc[h["sub"], "minutes"].mean()

    def wsum(col):
        return (h.w * col).groupby(h.player_id).sum()

    w, ws, wb = wsum(1.0), wsum(h.start), wsum(h["sub"])
    out = pd.DataFrame({
        "p_start": (ws / w).clip(upper=MAX_P_START),
        "p_sub": wb / w,
        # the "+ 2" terms pull small samples toward the league average
        "min_start": (wsum(h.minutes * h.start) + 2 * lg_min_start) / (ws + 2),
        "p60": (wsum((h.minutes >= 60) & h.start) + 2 * lg_p60) / (ws + 2),
        "min_sub": (wsum(h.minutes * h["sub"]) + 2 * lg_min_sub) / (wb + 2),
    })
    out["p_sub"] = np.minimum(out.p_sub, 1 - out.p_start)
    out = out.reindex(players.player_id)
    out[["p_start", "p_sub"]] = out[["p_start", "p_sub"]].fillna(0.0)  # no matches yet
    return out.fillna({"min_start": lg_min_start, "p60": lg_p60, "min_sub": lg_min_sub})


def rate_model(hist: pd.DataFrame, players: pd.DataFrame, seasons: pd.DataFrame) -> pd.DataFrame:
    """Per-90 rates: recency-weighted this season, blended with a prior.

    prior = last season's per-90 rate, itself shrunk toward this season's position mean.
    A player with no last season (new signing, promoted club) gets the position mean.
    """
    h = hist.merge(players[["player_id", "position"]], on="player_id")
    h["w"] = _weights(h, RATE_HALF_LIFE)
    n90 = h.minutes / 90
    pos_mean = h.groupby("position")[RATE_STATS].sum().div(n90.groupby(h.position).sum(), axis=0)

    prev = seasons[seasons.season_name == seasons.season_name.max()].set_index("player_id")
    prev = prev.reindex(players.player_id)
    prev_n90 = (prev.minutes / 90).fillna(0)
    pm = pos_mean.loc[players.position].set_axis(players.player_id)
    prior = (prev[RATE_STATS].fillna(0) + PREV_SEASON_SHRINK * pm).div(prev_n90 + PREV_SEASON_SHRINK, axis=0)

    cur = h[RATE_STATS].mul(h.w, axis=0).groupby(h.player_id).sum().reindex(players.player_id).fillna(0)
    cur_n90 = (h.w * n90).groupby(h.player_id).sum().reindex(players.player_id).fillna(0)
    rates = (cur + PRIOR_90S * prior).div(cur_n90 + PRIOR_90S, axis=0)
    return rates.add_suffix("_p90")


def conversion_ratios(hist: pd.DataFrame, seasons: pd.DataFrame) -> tuple[float, float]:
    """League-wide goals per xG and FPL assists per xA (last season + this season so far).

    FPL awards assists more generously than xA implies (rebounds, penalties won),
    so xA is scaled up by the observed ratio.
    """
    prev = seasons[seasons.season_name == seasons.season_name.max()]
    g = (hist.goals_scored.sum() + prev.goals_scored.sum()) / (hist.expected_goals.sum() + prev.expected_goals.sum())
    a = (hist.assists.sum() + prev.assists.sum()) / (hist.expected_assists.sum() + prev.expected_assists.sum())
    return g, a


def availability(players: pd.DataFrame, events: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """P(available) per player per GW from FPL's injury flags. Rows = players, columns = GWs.

    Next GW:   FPL's chance_of_playing_next_round (blank = 100%).
    Later GWs: if the news gives a date ("Expected back 22 Nov", "Suspended until 5 Dec"),
               0 before that date and 1 after. With no date, recover by 25 points per GW
               (an assumption). Status "u" (left the club / unavailable) = 0 throughout.
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
            a = np.minimum(1.0, base + 0.25 * k)
            # a GW's matches run for about 3 days after its deadline
            dated = np.where(back <= deadline[gw] + pd.Timedelta(days=3), 1.0, 0.0)
            a = np.where(back.notna(), dated, a)
        out[gw] = np.where(gone, 0.0, a)
    return pd.DataFrame(out, index=players.player_id)


def project(tables: dict, as_of_gw: int | None = None, horizon: int = 8,
            use_availability: bool = True) -> tuple[pd.DataFrame, dict]:
    """xP for every player for the `horizon` gameweeks after `as_of_gw`.

    Only matches up to and including `as_of_gw` are used, so passing an earlier
    gameweek gives an honest backtest. Returns (one row per player per GW, team ratings).
    """
    players, fixtures, events = tables["players"], tables["fixtures"], tables["events"]
    seasons = tables["player_seasons"]
    if as_of_gw is None:
        as_of_gw = int(events.loc[events.finished, "gw"].max())
    hist = tables["player_gw"]
    hist = hist[hist.gw <= as_of_gw].sort_values("kickoff_time")
    gws = [g for g in range(as_of_gw + 1, as_of_gw + 1 + horizon) if g <= events.gw.max()]

    s = load_scoring()
    ratings = fit_ratings(hist)
    att, dfn, mu = ratings["attack"], ratings["defence"], ratings["mu"]
    g_ratio, a_ratio = conversion_ratios(hist, seasons)

    per_player = pd.concat(
        [players.set_index("player_id")[["web_name", "position", "team", "team_id", "now_cost"]],
         minutes_model(hist, players), rate_model(hist, players, seasons)], axis=1).reset_index()

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

    df = per_player.merge(tf, on="team_id")
    if use_availability:
        av = availability(players, events, gws).stack().rename("avail")
        av.index.names = ["player_id", "gw"]
        df = df.merge(av.reset_index(), on=["player_id", "gw"])
    else:
        df["avail"] = 1.0

    pos = df.position
    a_start = df.avail * df.p_start
    share = df.min_start.clip(upper=90) / 90          # share of the match a starter plays
    df["xmins"] = df.avail * (df.p_start * df.min_start + df.p_sub * df.min_sub)
    n90 = df.xmins / 90

    df["xp_app"] = df.avail * (df.p_start * (s["short_play"] + df.p60 * (s["long_play"] - s["short_play"]))
                               + df.p_sub * s["short_play"])
    df["xp_goals"] = df.expected_goals_p90 * df.att_mult * g_ratio * n90 * pos.map(s["goals_scored"])
    df["xp_assists"] = df.expected_assists_p90 * df.att_mult * a_ratio * n90 * s["assists"]
    df["p_cs"] = np.exp(-df.lam_against * share)
    df["xp_cs"] = a_start * df.p60 * df.p_cs * pos.map(s["clean_sheets"])
    df["xp_conceded"] = a_start * _exp_floor_div(df.lam_against * share, 2) * pos.map(s["goals_conceded"])
    saves = df.saves_p90 * df.save_mult * share
    df["xp_saves"] = np.where(pos == "GKP", a_start * _exp_floor_div(saves, 3) * s["saves"], 0.0)
    df["p_dc"] = _prob_at_least(df.defensive_contribution_p90 * share, pos.map(DC_THRESHOLD))
    df["xp_dc"] = a_start * df.p_dc * pos.map(s["defensive_contribution"])
    df["xp_bonus"] = df.bonus_p90 * n90 * s["bonus"]
    df["xp_cards"] = (df.yellow_cards_p90 * s["yellow_cards"] + df.red_cards_p90 * s["red_cards"]) * n90
    parts = [c for c in df.columns if c.startswith("xp_")]
    df["xp"] = df[parts].sum(axis=1)

    # One row per player per GW: doubles sum both fixtures, blanks get 0.
    agg = df.groupby(["player_id", "gw"]).agg(
        opp=("opp", " + ".join), n_fixtures=("opp", "size"), xmins=("xmins", "sum"),
        **{c: (c, "sum") for c in parts}, xp=("xp", "sum")).reset_index()
    grid = pd.MultiIndex.from_product([players.player_id, gws], names=["player_id", "gw"]).to_frame(index=False)
    out = grid.merge(agg, on=["player_id", "gw"], how="left")
    out["opp"] = out.opp.fillna("-")
    out = out.fillna(0.0)
    out["n_fixtures"] = out.n_fixtures.astype(int)
    info = per_player[["player_id", "web_name", "position", "team", "now_cost", "p_start"]]
    return info.merge(out, on="player_id"), ratings
