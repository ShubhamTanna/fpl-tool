"""Player: everything on file about one player, or 2 to 4 players side by side."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
from fpl.insights import player_view as pv

st.title("Player")
stamp = c.data_stamp()
players, proj, nm, lab = c.table("players"), c.proj(), c.names(), c.labels()
if "player_pick" not in st.session_state:
    st.session_state.player_pick = [c.my_team(stamp)["squad"][0]]
order = players.sort_values("total_points", ascending=False).player_id.tolist()
ids = st.multiselect("Players (pick 1 for the full page, 2 to 4 to compare; type to search)", order,
                     format_func=lab.get, max_selections=4, key="player_pick")
if not ids:
    st.info("Pick a player.")
    st.stop()
gws = c.gameweeks()
pset = players.set_index("player_id")
pg = c.table("player_gw")
PALETTE = [viz.ACCENT, "#A78BFA", viz.WARN, "#F472B6"]


def colours(ids: list[int]) -> dict[int, str]:
    """Each player in his club colour. If that is too close to one already used, he gets a palette colour."""
    def near(x: str, y: str) -> bool:      # too alike to tell apart, e.g. two red clubs
        return sum(abs(int(x[k:k + 2], 16) - int(y[k:k + 2], 16)) for k in (1, 3, 5)) < 90

    out = {}
    for k, i in enumerate(ids):
        col = viz.line(pset.team[i])
        out[i] = PALETTE[k] if any(near(col, u) for u in out.values()) else col
    return out


def charts(ids: list[int]) -> None:
    """The five player charts. One player: full detail. Two to four: overlaid or grouped."""
    col, one = colours(ids), len(ids) == 1
    raw = c.table("players").set_index("player_id").web_name
    logs = {i: pg[pg.player_id == i].sort_values("kickoff_time").reset_index(drop=True) for i in ids}
    short = c.table("teams").set_index("team_id").short_name

    def xlab(h: pd.DataFrame) -> list[str]:
        return [f"GW{g} {short[o]}" for g, o in zip(h.gw, h.opponent_team_id)] if one else [f"GW{g}" for g in h.gw]

    a, b = st.columns(2)
    fig = go.Figure()
    for i in ids:
        h = logs[i]
        fig.add_scatter(x=xlab(h), y=h.expected_goal_involvements.cumsum().round(2), name=f"{raw[i]} xGI",
                        line=dict(color=col[i], dash="dash", width=2), mode="lines")
        fig.add_scatter(x=xlab(h), y=(h.goals_scored + h.assists).cumsum(), name=f"{raw[i]} goals + assists",
                        line=dict(color=col[i], width=3), mode="lines+markers",
                        **({"fill": "tonexty", "fillcolor": viz._rgba(col[i], 0.15)} if one else {}))
    fig.update_layout(title="Cumulative xGI against goals + assists", yaxis_title="Cumulative")
    with a:
        viz.chart(fig, "Dashed = chances (xGI), solid = goals and assists. Solid below dashed means he is owed "
                       "returns; solid above means he has been finishing above his chances.", height=340, key="c_xgi")

    fig = go.Figure()
    for i in ids:
        h = logs[i]
        kind = ["Started" if s else "Came on" if m > 0 else "Did not play" for s, m in zip(h.starts, h.minutes)]
        if one:
            for name, colour in (("Started", viz.GOOD), ("Came on", viz.WARN)):
                sel = [k == name for k in kind]
                fig.add_bar(x=[x for x, s in zip(xlab(h), sel) if s], y=h.minutes[sel], name=name, marker_color=colour)
            out = [k == "Did not play" for k in kind]
            fig.add_scatter(x=[x for x, s in zip(xlab(h), out) if s], y=[0] * sum(out), mode="markers", name="Did not play",
                            marker=dict(symbol="x", size=11, color=viz.BAD))
            fig.update_xaxes(categoryorder="array", categoryarray=xlab(h))
        else:
            fig.add_bar(x=xlab(h), y=h.minutes, name=raw[i], marker_color=col[i],
                        marker_pattern_shape=["" if k == "Started" else "/" for k in kind])
    fig.update_layout(title="Minutes per match", yaxis=dict(title="Minutes", range=[-4, 96]), barmode="group")
    with b:
        viz.chart(fig, "Look for a run of full starts (secure) or a drift to the bench. "
                       + ("Green = started, amber = came on, red cross = did not play."
                          if one else "Solid = started, hatched = came on or did not play."), height=340, key="c_min")

    a, b = st.columns(2)
    done = [g for g in c.finished_gws() if g >= 2]
    fig = go.Figure()
    for i in ids:
        h = logs[i].groupby("gw", as_index=False).total_points.sum()
        fig.add_bar(x=[f"GW{g}" for g in h.gw], y=h.total_points, name=f"{raw[i]} points", marker_color=col[i],
                    opacity=0.75)
        past = pd.Series({g: c.past_proj(g, stamp).set_index("player_id").xp.get(i) for g in done}).dropna()
        fig.add_scatter(x=[f"GW{g}" for g in past.index], y=past.round(2), name=f"{raw[i]} xP beforehand",
                        mode="lines+markers", line=dict(color=viz.TEXT if one else col[i], width=2, dash="dot"))
    fig.update_layout(title="Points per gameweek against the projection made beforehand", yaxis_title="Points", barmode="group")
    with a:
        viz.chart(fig, "Bars = points scored, dotted line = what the model projected before each gameweek "
                       "(from GW2, without the injury flags of the time). Bars swinging around a steady line is "
                       "normal variance; a line that keeps missing one way is a model miss.", height=340, key="c_pts")

    if one:
        d = proj[proj.player_id == ids[0]].sort_values("gw")
        fig = viz.stacked_parts(viz.parts_frame(d), [f"GW{g}<br>{o}" for g, o in zip(d.gw, d.opp)],
                                horizontal=False, title=f"xP by part, GW{gws[0]}-{gws[-1]}")
    else:
        fig = go.Figure()
        for i in ids:
            d = proj[proj.player_id == i].sort_values("gw")
            fig.add_bar(x=[f"GW{g}" for g in d.gw], y=d.xp.round(2), name=raw[i], marker_color=col[i],
                        hovertext=d.opp, hovertemplate="%{x} %{hovertext}: %{y:.2f}<extra></extra>")
        fig.update_layout(barmode="group", title=f"xP by gameweek, GW{gws[0]}-{gws[-1]}", yaxis_title="xP")
    with b:
        viz.chart(fig, "Which gameweeks carry his value, and from what. Tall goal and assist blocks depend on the "
                       "fixture; the grey appearance block is there every week he starts."
                  if one else "Who is ahead in which gameweek. Hover for the opponent.", height=340, key="c_xp")

    pc = pv.percentiles(ids, players, pg)
    fig = go.Figure()
    for i in ids:
        d = pc[pc.player_id == i]
        fig.add_bar(y=d.metric, x=d.percentile.round(0), name=raw[i], orientation="h", marker_color=col[i],
                    text=[f"{v:.2f}" for v in d.value], textposition="auto",
                    hovertemplate="%{y}: percentile %{x:.0f}<extra></extra>")
    fig.add_vline(x=50, line_color=viz.MUTED, line_dash="dot")
    fig.update_layout(barmode="group", title="Percentile within his position", xaxis=dict(range=[0, 100], title="Percentile"),
                      yaxis=dict(autorange="reversed", tickfont=dict(family=viz.SANS)))
    viz.chart(fig, f"100 = best among players of the same position with {pv.PCT_MIN_MINUTES}+ minutes "
                   f"({', '.join(str(int(pc[pc.player_id == i].peers.iloc[0])) + ' ' + pset.position[i] for i in ids)} "
                   "in the pool). The number on each bar is the raw value. Look for bars past the dotted line at 50.",
              height=120 + 70 * len(ids) + 120, key="c_pct")


if len(ids) > 1:
    charts(ids)
    st.subheader("Side by side")
    c.show(pv.compare(ids, players, proj, nm, c.top1k()).round(2))
    grid = proj[proj.player_id.isin(ids)]
    xp = grid.pivot(index="gw", columns="player_id", values="xp").rename(columns=nm.to_dict())
    opp = grid.pivot(index="gw", columns="player_id", values="opp").rename(columns=nm.to_dict())
    table = pd.DataFrame({"GW": xp.index})
    for name in xp.columns:
        table[f"{name} fixture"] = opp[name].values
        table[f"{name} xP"] = xp[name].round(2).values
    st.subheader("xP by gameweek")
    c.show(table)
    st.caption(c.top1k_caption() + " Per-90 figures are this season's raw rates.")
    st.stop()

pid = ids[0]
p = players.set_index("player_id").loc[pid]
st.subheader(f"{nm[pid]}  |  {p.first_name} {p.second_name}, {p.team}, {p.position}")
if p.news:
    st.warning(f"{p.news} (chance of playing next round: "
               f"{'not given' if pd.isna(p.chance_of_playing_next_round) else str(int(p.chance_of_playing_next_round)) + '%'})")
m = st.columns(6)
m[0].metric("Price", f"{p.now_cost / 10:.1f}m", f"{p.cost_change_start / 10:+.1f}m since GW1", delta_color="off")
m[1].metric("Points", int(p.total_points))
m[2].metric("Owned by", f"{p.selected_by_percent:.1f}%")
m[3].metric("Top 1k owned", f"{c.top1k().get(pid, 0):.1f}%")
m[4].metric(f"xP GW{gws[0]}", f"{proj[(proj.player_id == pid) & (proj.gw == gws[0])].xp.iloc[0]:.2f}")
m[5].metric(f"xP GW{gws[0]}-{gws[-1]}", f"{proj[proj.player_id == pid].xp.sum():.1f}")

charts(ids)

st.subheader(f"Projection, GW{gws[0]}-{gws[-1]}")
c.show(pv.projection_rows(pid, proj, c.PARTS).round(2))
st.caption("Chance of starting comes from recent starts (latest matches weigh most), after any boost. "
           "Available is FPL's injury flag. Fixture multiplier scales goals and assists: above 1 = easier "
           "than his club's average fixture. Team xG and Opponent xG are the model's expected goals for his "
           "club and against it.")
a, b = st.columns(2)
with a:
    st.markdown("**Model inputs (blended rates)**")
    c.show(pv.model_rates(pid, proj).round(3))
with b:
    st.markdown("**Set pieces**")
    c.show(pv.set_pieces(pid, players))
    st.caption("FPL's listed order: 1 = first choice. '-' = not listed.")

st.subheader("This season, match by match")
log = pv.match_log(pid, c.table("player_gw"), c.table("teams"))
c.show(log.round(2), height=420)
a, b = st.columns(2)
with a:
    st.markdown("**Season totals and per-90 rates**")
    c.show(pv.season_rates(pid, players).round(2))
with b:
    st.markdown("**Past seasons**")
    past = pv.last_season(pid, c.table("player_seasons"))
    if len(past):
        c.show(past)
    else:
        st.write("No past Premier League season on file.")

st.subheader("Ownership and price")
trend = log.sort_values("GW").drop_duplicates("GW", keep="last")
tx = [f"GW{g}" for g in trend.GW]
club = viz.line(p.team)
a, b, d = st.columns(3)
with a:
    viz.chart(go.Figure(go.Scatter(x=tx, y=trend["Owned by"], mode="lines+markers", line=dict(color=club, width=3)))
              .update_layout(title="Managers owning him"), "Rising = the crowd is buying.", height=260, key="t_own")
with b:
    viz.chart(go.Figure(go.Bar(x=tx, y=trend["Net transfers"],
                               marker_color=[viz.GOOD if v >= 0 else viz.BAD for v in trend["Net transfers"]]))
              .update_layout(title="Net transfers in"), "Green = more bought than sold that week.", height=260, key="t_net")
with d:
    viz.chart(go.Figure(go.Scatter(x=tx, y=trend["Price"], mode="lines+markers", line=dict(color=club, width=3, shape="hv")))
              .update_layout(title="Price (m)"), "Steps up follow heavy buying.", height=260, key="t_price")
st.caption(f"Transfers this gameweek so far: {int(p.transfers_in_event):,} in, {int(p.transfers_out_event):,} out.")

st.subheader("Record against upcoming opponents")
upcoming = proj[(proj.player_id == pid) & (proj.n_fixtures > 0)].opp.str.split(" + ", regex=False).explode()
opps = list(dict.fromkeys(o.split("(")[0] for o in upcoming))
c.show(pv.record_vs(pid, players, c.table("history_gw"), opps).round(2))
st.caption("Display only, not in xP. Matches he played against each club since 2022-23 (xG from 2022-23 GW16 "
           "onward). A handful of matches says very little.")
