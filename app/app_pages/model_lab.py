"""Model lab: how the projections have performed, and how the model was tuned. Read-only."""
from dataclasses import asdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
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

fig = go.Figure()
fig.add_bar(x=s.season, y=s.xi_ppg.round(1), name="Points-per-game XI", marker_color=viz.MUTED,
            text=s.xi_ppg.round(1), textposition="outside")
fig.add_bar(x=s.season, y=s.xi_model.round(1), name="Model XI", marker_color=viz.ACCENT,
            text=s.xi_model.round(1), textposition="outside")
fig.update_layout(barmode="group", title="Best XI: actual points per gameweek", yaxis_title="Points per gameweek",
                  xaxis=dict(tickfont=dict(family=viz.SANS)))
viz.chart(fig, "The gap between the bars is what the model's ranking is worth over simply picking on points per "
               "game. It should be positive in every season, including the hold-out and the live one.", height=340, key="xi")

st.subheader("Calibration by xP bucket")
fig = go.Figure()
kb = buck[buck.model == which]
top = max(kb.mean_xp.max(), kb.mean_actual.max()) * 1.05
fig.add_scatter(x=[0, top], y=[0, top], mode="lines", line=dict(color=viz.MUTED, dash="dot"), name="Perfect", hoverinfo="skip")
for k, (season_name, d) in enumerate(kb.groupby("season", sort=False)):
    fig.add_scatter(x=d.mean_xp.round(2), y=d.mean_actual.round(2), mode="lines+markers", name=season_name,
                    marker=dict(size=(d.player_gws ** 0.5 / 6).clip(6, 22)),
                    hovertemplate=season_name + ": projected %{x:.2f}, actual %{y:.2f}<extra></extra>")
fig.update_layout(title="Average projected against average actual points, by xP bucket",
                  xaxis_title="Average xP in the bucket", yaxis_title="Average actual points")
viz.chart(fig, "Points on the dotted line = players projected X points averaged X. Below the line the model is "
               "too generous, above it too cautious. Bigger markers hold more player-gameweeks; the top bucket "
               "is small and noisy.", height=420, key="calib")

st.subheader("Calibration by part of the score")
season = st.selectbox("Season", list(s.season), index=len(s) - 1)
k = comp[(comp.model == which) & (comp.season == season)]
fig = go.Figure()
fig.add_bar(x=k.part, y=k.actual.round(0), name="Actual", marker_color=viz.MUTED)
fig.add_bar(x=k.part, y=k.projected.round(0), name="Projected", marker_color=viz.ACCENT)
fig.update_layout(barmode="group", title=f"Projected against actual points by part, {season}", yaxis_title="Points",
                  xaxis=dict(tickfont=dict(family=viz.SANS)))
viz.chart(fig, "Each pair should be level. A blue bar taller than the grey one means that part is over-projected; "
               "the ratio is in the table below.", height=340, key="parts")
a, b = st.columns(2)
with a:
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
