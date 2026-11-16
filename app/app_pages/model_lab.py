"""Model lab: how the projections have performed, and how the model was tuned. Read-only."""
from dataclasses import asdict

import pandas as pd
import streamlit as st

import common as c
from fpl.model.dials import DIALS
from fpl.optimize.models import BENCH_GKP, BENCH_OUTFIELD, DECAY, FT_VALUE, MIN_GAIN

st.title("Model lab")
st.caption("Results of replaying past gameweeks: each one is projected from the matches before it and compared "
           "with what happened. Rebuild with scripts/backtest.py, scripts/run_trials.py and "
           "scripts/backtest_threshold.py. Nothing on this page can be edited: dials change only through the backtest.")

summ, comp, buck = c.table("backtest_summary"), c.table("backtest_components"), c.table("backtest_buckets")
which = st.segmented_control("Model", ["after", "before"], default="after",
                             format_func={"after": "Current model", "before": "Before Step 6"}.get)

st.subheader("Summary by season")
s = summ[summ.model == which]
c.show(pd.DataFrame({
    "Season": s.season, "Role": s.role, "Player-gameweeks": s.player_gws, "Projected pts": s.proj_pts.round(0),
    "Actual pts": s.actual_pts, "RMSE": s.rmse, "MAE": s.mae, "MAE (played)": s.mae_played,
    "Correlation (played)": s.corr_played, "Points-per-game correlation": s.corr_played_ppg,
    "Best XI pts per GW": s.xi_model, "Points-per-game XI": s.xi_ppg}).round(3))
st.caption("Role: dials were chosen on the tune seasons, accepted on the hold-out, and the live season was never "
           "used for tuning. RMSE and MAE are in points per player per gameweek. 'Played' = players with minutes. "
           "Best XI = actual points of the eleven the model ranks highest (valid formation, captain doubled, no "
           "budget), against the same pick made from points per game. Past injury flags are not available, so "
           "regular starters are over-projected in every replay.")

st.subheader("Calibration by part of the score")
season = st.selectbox("Season", list(s.season), index=len(s) - 1)
a, b = st.columns(2)
with a:
    k = comp[(comp.model == which) & (comp.season == season)]
    c.show(k[["part", "projected", "actual", "ratio"]].rename(columns={
        "part": "Part", "projected": "Projected pts", "actual": "Actual pts", "ratio": "Projected / actual"}).round(2))
    st.caption("1.00 = projected exactly what was scored. Defensive contribution did not exist before 2025-26.")
with b:
    k = buck[(buck.model == which) & (buck.season == season)]
    c.show(k[["xp_bucket", "player_gws", "mean_xp", "mean_actual"]].rename(columns={
        "xp_bucket": "xP bucket", "player_gws": "Player-gameweeks", "mean_xp": "Average xP",
        "mean_actual": "Average actual"}).round(2))
    st.caption("Do players projected 4-5 points average 4-5? The two averages should match in each row.")

st.subheader("Trial log")
log = pd.read_csv(c.P / "trial_log.csv")
c.show(log.round(5), height=420)
st.caption(f"{log.trial.nunique()} trials, {(log.decision == 'ACCEPTED').sum()} accepted. One dial at a time: every "
           "candidate is scored on the tune set, the best is taken to the hold-out once, and the change is kept "
           "only if the hold-out improves. A fix aimed at one part of the score is judged on that part.")

st.subheader("Current dials")
a, b = st.columns(2)
with a:
    c.show(pd.DataFrame({"Projection dial": list(asdict(DIALS)), "Value": [str(v) for v in asdict(DIALS).values()]}))
with b:
    opt = {"DECAY (weight lost per further gameweek)": DECAY, "BENCH_OUTFIELD (bench outfielder's share of xP)": BENCH_OUTFIELD,
           "BENCH_GKP (reserve keeper's share)": BENCH_GKP, "FT_VALUE (xP credited per unused free transfer)": FT_VALUE,
           "MIN_GAIN (default transfer threshold, xP)": MIN_GAIN}
    c.show(pd.DataFrame({"Optimizer setting": list(opt), "Value": [str(v) for v in opt.values()]}))
    st.caption("The optimizer settings are judgement calls and have not been through the backtest.")

st.subheader("Transfer threshold backtest")
t = c.table("backtest_threshold")
pts = t.groupby(["threshold", "season"]).points.sum().unstack()
moves = t.groupby(["threshold", "season"]).transfers.sum().unstack().add_prefix("Transfers ")
out = pd.concat([pts.add_prefix("Points "), moves], axis=1).reset_index().rename(columns={"threshold": "Threshold (xP)"})
c.show(out)
st.caption(f"One simulated manager per threshold, GW{int(t.gw.min())}-{int(t.gw.max())}, best single swap each week "
           "if its projected gain beats the threshold. 99 = never transfer. Prices ignore the 50% rule and there "
           "are no automatic substitutions. Totals for thresholds 0 to 6 show no pattern, so the default of "
           f"{MIN_GAIN} is a judgement call, not a fitted value.")
