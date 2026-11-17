"""Clubs: team strength, form in xG, and each club's players."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
from fpl.model.dials import DIALS
from fpl.model.teams import fit_ratings, team_matches
from fpl.model.xp import dc_matchup

ROLL = 4      # matches in the rolling average

st.title("Clubs")
st.caption("Team strength as the projections see it: ratings from xG for and against, recent matches weighing "
           "more, pulled toward average because the season is young.")
stamp = c.data_stamp()
players, pg, proj, nm = c.table("players"), c.table("player_gw"), c.proj(), c.names()
teams = c.table("teams").set_index("team_id")
short = teams.short_name
p = players.set_index("player_id")
mine = sorted(set(p.team[c.my_team(stamp)["squad"]]))

r = fit_ratings(pg, DIALS.team_half_life, DIALS.team_prior_matches)
rt = pd.DataFrame({"team": short, "attack": r["attack"], "defence": r["defence"]}).dropna()
fig = go.Figure()
fig.add_hline(y=1, line_color=viz.MUTED, line_dash="dot")
fig.add_vline(x=1, line_color=viz.MUTED, line_dash="dot")
cols = [viz.fill(t) for t in rt.team]
fig.add_scatter(x=rt.attack.round(2), y=rt.defence.round(2), mode="markers+text", text=rt.team, textposition="top center",
                textfont=dict(family=viz.MONO, color=viz.TEXT, size=12),
                marker=dict(size=20, color=[k[0] for k in cols], line=dict(color=[k[1] if k[1] != k[0] else viz.BG for k in cols], width=2)),
                hovertemplate="%{text}: attack %{x:.2f}, defence %{y:.2f}<extra></extra>", showlegend=False)
x0, x1 = rt.attack.min() - 0.08, rt.attack.max() + 0.08
y0, y1 = rt.defence.min() - 0.08, rt.defence.max() + 0.08
for x, y, label, xa, ya in ((x1, y0, "Scores a lot, concedes little", "right", "top"),
                            (x0, y0, "Scores little, concedes little", "left", "top"),
                            (x1, y1, "Scores a lot, concedes a lot", "right", "bottom"),
                            (x0, y1, "Scores little, concedes a lot", "left", "bottom")):
    fig.add_annotation(x=x, y=y, text=label, showarrow=False, xanchor=xa, yanchor=ya, font=dict(color=viz.MUTED, size=12))
fig.update_layout(title="Attack rating against defence rating (1.00 = league average)",
                  xaxis=dict(title="Attack rating: xG created, relative to average (right = better)", range=[x0, x1]),
                  yaxis=dict(title="Defence rating: xG conceded, relative to average (up = better)", range=[y1, y0]))
viz.chart(fig, "Top right = strong at both ends: pick attackers and defenders from there. Bottom right = buy the "
               "attackers, avoid the defenders. Clubs close together are not reliably different after this few "
               "matches.", height=520, key="ratings")

st.subheader("Form in xG")
tm = team_matches(pg).sort_values("kickoff_time")
tm["team"] = tm.team_id.map(short)
tm["n"] = tm.groupby("team_id").cumcount() + 1
pick = st.multiselect("Clubs to show", sorted(short), default=mine[:3] or sorted(short)[:3], max_selections=6)
fig = go.Figure()
for t in pick:
    d = tm[tm.team == t]
    col = viz.line(t)
    fig.add_scatter(x=d.n, y=d.xg_for.rolling(ROLL, min_periods=1).mean().round(2), name=f"{t} xG for", mode="lines+markers",
                    line=dict(color=col, width=3))
    fig.add_scatter(x=d.n, y=d.xg_against.rolling(ROLL, min_periods=1).mean().round(2), name=f"{t} xG against",
                    mode="lines+markers", line=dict(color=col, width=2, dash="dash"), marker=dict(symbol="circle-open"))
fig.update_layout(title=f"Rolling {ROLL}-match average of xG for (solid) and against (dashed)",
                  xaxis=dict(title="Match number", dtick=1), yaxis_title="xG per match")
viz.chart(fig, "A club is improving where its solid line rises and its dashed line falls. A solid line well above "
               "the dashed one means it is creating more than it allows. Early points average fewer than "
               f"{ROLL} matches.", height=380, key="form")

st.subheader("One club")
club = st.selectbox("Club", sorted(short), index=sorted(short).index(mine[0]) if mine else 0)
gws5 = c.gameweeks()[:5]
ids = players[(players.team == club) & (players.status != "u")].player_id.tolist()
xp5 = c.xp_grid(gws5).sum(axis=1)
ids = [i for i in sorted(ids, key=lambda i: -xp5.get(i, 0)) if xp5.get(i, 0) > 0]
st.markdown(f"**{club} players ranked by xP, GW{gws5[0]}-{gws5[-1]}**")
c.show(c.breakdown(ids, gws5), decimals=1, height=420)

st.markdown(f"**Defensive actions opponents record against {club}**")
h = pg.merge(players[["player_id", "position"]], on="player_id")
h = h[h.position.isin(["DEF", "MID"]) & (h.minutes > 0)]
per = (h.groupby(["opponent_team_id", "fixture_id", "position"]).defensive_contribution.sum()
       .groupby(["opponent_team_id", "position"]).mean().unstack())
per.index = per.index.map(short)
mult = dc_matchup(pg, players, DIALS.team_prior_matches).unstack()
mult.index = mult.index.map(short)
a, b = st.columns(2)
for holder, pos in ((a, "DEF"), (b, "MID")):
    d = per[pos].sort_values()
    fig = go.Figure(go.Bar(x=d.round(1), y=d.index, orientation="h",
                           marker=dict(color=[viz.line(t) if t == club else "#3A4654" for t in d.index]),
                           hovertemplate="%{y}: %{x:.1f} per match<extra></extra>"))
    fig.add_vline(x=d.mean(), line_color=viz.MUTED, line_dash="dot")
    fig.update_layout(title=f"Defensive actions per match by opposing {pos}s", xaxis_title="Per match, all of that position combined",
                      yaxis=dict(tickfont=dict(family=viz.MONO)))
    with holder:
        viz.chart(fig, f"Longer bar = opposing {pos}s rack up more defensive actions against that club. "
                       f"{club} is highlighted; the dotted line is the league average.", height=520, key=f"dc_{pos}")
c.show(pd.DataFrame({"Position": ["DEF", "MID"],
                     f"Per match against {club}": [per.loc[club, "DEF"], per.loc[club, "MID"]],
                     "League average": [per.DEF.mean(), per.MID.mean()],
                     "Matchup multiplier (shrunk, vs players' own norm)": [mult.loc[club, "DEF"], mult.loc[club, "MID"]]}))
st.caption("Display only: this is the defender-matchup signal, which failed its backtest twice and is switched "
           "off in the projections. The multiplier compares what opposing players recorded against this club "
           "with what the same players record elsewhere, pulled toward 1.00.")
