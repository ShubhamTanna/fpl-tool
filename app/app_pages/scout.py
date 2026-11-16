"""Scout: ranked lists of candidates who are not in the squad. Click a point or a row to open the player."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
from fpl.insights import scout as sc
from fpl.insights import signals as sg

st.title("Scout")
st.caption("Players to look at. These are prompts for your own judgement: none of the rules below has been "
           "backtested. Click a point in a chart or a row in a table to open that player's page. "
           "Understat-based signals (zone matchup, long shots, set-piece xG) are still blocked because "
           "understat.com is offline.")
stamp = c.data_stamp()
players, pg, proj, nm = c.table("players"), c.table("player_gw"), c.proj(), c.names()
p, own = players.set_index("player_id"), c.top1k()
mine = set(c.my_team(stamp)["squad"])
gws5 = c.gameweeks()[:5]
xp5 = c.xp_grid(gws5).sum(axis=1)
XP5 = f"xP GW{gws5[0]}-{gws5[-1]}"
st.session_state.setdefault("scout_nonce", 0)
NONCE = st.session_state.scout_nonce


def open_player(pid: int) -> None:
    st.session_state.scout_nonce += 1          # new widget keys, so the click is not replayed on return
    st.session_state.player_pick = [int(pid)]
    st.switch_page("app_pages/player.py")


def clickable(fig: go.Figure, caption: str, key: str, height: int = 420) -> None:
    """Draw a chart whose points carry a player id in customdata; a click opens that player."""
    ev = viz.chart(fig, caption, height=height, key=f"{key}_{NONCE}", select=True)
    pts = ev.selection.points if ev and ev.selection else []
    if pts and pts[0].get("customdata") is not None:
        cd = pts[0]["customdata"]
        open_player(cd[0] if isinstance(cd, (list, tuple)) else cd)


def candidates(ids: list[int], extra: pd.DataFrame, key: str) -> None:
    """Candidate table (squad players removed). Clicking a row opens the player."""
    keep = [i for i in ids if i not in mine and i in p.index]
    if not keep:
        st.write("Nobody outside your squad passes this rule right now.")
        return
    df = pd.DataFrame({"Player": nm.reindex(keep).values, "Pos": p.position[keep].values, "Club": p.team[keep].values,
                       "Price": (p.now_cost[keep] / 10).values, "Owned %": p.selected_by_percent[keep].values,
                       "Top 1k %": own.reindex(keep).fillna(0).values, XP5: xp5.reindex(keep).values})
    df = pd.concat([df, extra.set_index("player_id").reindex(keep).reset_index(drop=True)], axis=1)
    ev = c.show(df, decimals=2, on_select="rerun", selection_mode="single-row", key=f"tbl_{key}_{NONCE}")
    if ev.selection.rows:
        open_player(keep[ev.selection.rows[0]])


def hover(ids) -> list[str]:
    return [f"{nm[i]} ({p.team[i]}, {p.position[i]}) {p.now_cost[i] / 10:.1f}m" for i in ids]


# ------------------------------------------------------------------ 1
st.subheader("1. xG underperformers")
st.markdown(
    f"Rule: midfielders and forwards with at least {sg.MIN_MINUTES} minutes who pass all four tests. "
    f"xGI per 90 in the top {round((1 - sg.XGI_PERCENTILE) * 100)}% of the position; goals + assists at least "
    f"{sg.MIN_GAP:.1f} below xGI; started {sg.SECURE_STARTS} of his club's last 5, or minutes rising; owned by "
    f"under {sg.MAX_OWNERSHIP:.0f}% of managers. Ranked by the gap, biggest first.")
allu = sg.underperformers(players, pg, flagged_only=False)
allu["ga_p90"] = allu.g_a / allu.minutes * 90
u = allu[allu.flag]
rest = allu[~allu.flag]
top = max(allu.xgi_p90.max(), allu.ga_p90.max()) * 1.05
fig = go.Figure()
fig.add_scatter(x=[0, top], y=[0, top], mode="lines", line=dict(color=viz.MUTED, dash="dot"), name="Goals + assists = xGI",
                hoverinfo="skip")
fig.add_scatter(x=rest.xgi_p90, y=rest.ga_p90, mode="markers", name="Other attackers", customdata=rest.player_id,
                marker=dict(color=viz.MUTED, size=8, opacity=0.55), text=hover(rest.player_id),
                hovertemplate="%{text}<br>xGI/90 %{x:.2f}, G+A/90 %{y:.2f}<extra></extra>")
fig.add_scatter(x=u.xgi_p90, y=u.ga_p90, mode="markers+text", name="Flagged", customdata=u.player_id,
                marker=dict(color=viz.ACCENT, size=13, line=dict(color=viz.TEXT, width=1)),
                text=[p.web_name[i] for i in u.player_id], textposition="top center", textfont=dict(color=viz.TEXT),
                hovertext=hover(u.player_id), hovertemplate="%{hovertext}<br>xGI/90 %{x:.2f}, G+A/90 %{y:.2f}<extra></extra>")
fig.update_layout(title=f"Chances against returns, attackers with {sg.MIN_MINUTES}+ minutes",
                  xaxis_title="xGI per 90", yaxis_title="Goals + assists per 90")
clickable(fig, "Below the dotted line = fewer goals and assists than his chances were worth. Look for points far "
               "to the right (high xGI) and well below the line. Flagged players also pass the minutes and "
               "ownership tests.", "under")
candidates(u.player_id.tolist(), u[["player_id", "minutes", "xgi_p90", "xgi", "g_a", "gap", "starts_last5"]].rename(
    columns={"minutes": "Mins", "xgi_p90": "xGI/90", "xgi": "xGI", "g_a": "G+A", "gap": "G+A minus xGI",
             "starts_last5": "Starts (last 5)"}), "under")

# ------------------------------------------------------------------ 2
st.subheader("2. Minutes rising")
st.markdown(
    f"Rule: over his club's last {sc.RISE_WINDOW} matches against the {sc.RISE_WINDOW} before, more starts, at "
    f"least {sc.MIN_MINUTES_RISE} more minutes, and at least {sc.MIN_RECENT_MINUTES} minutes in the recent window. "
    "Ranked by the rise in minutes.")
m = sc.minutes_rising(pg)
m = m[~m.player_id.isin(mine) & m.player_id.isin(p.index)]
SLOPES = 15
ms = m.assign(xp=m.player_id.map(xp5)).nlargest(SLOPES, "xp")
fig = go.Figure()
for r in ms.itertuples():
    col = viz.line(p.team[r.player_id])
    fig.add_scatter(x=["3 matches before", "Last 3 matches"], y=[r.mins_prev3, r.mins_last3], mode="lines+markers+text",
                    line=dict(color=col, width=2), marker=dict(size=9, color=col), customdata=[r.player_id] * 2,
                    text=["", p.web_name[r.player_id]], textposition="middle right", textfont=dict(color=viz.TEXT, size=11),
                    hovertext=hover([r.player_id] * 2), hovertemplate="%{hovertext}<br>%{x}: %{y} minutes<extra></extra>",
                    showlegend=False)
fig.update_layout(title=f"Minutes in each window: the {len(ms)} risers with the highest {XP5}",
                  yaxis=dict(title="Minutes", range=[-10, 285]), xaxis=dict(range=[-0.3, 1.9], tickfont=dict(family=viz.SANS)))
clickable(fig, "Each line is one player, in his club colour. Steep lines ending near 270 have gone from the "
               "fringe to playing every minute: check whether it is a new role or cover for an injury.", "rising", 520)
candidates(m.player_id.tolist(), m.rename(columns={
    "starts_prev3": "Starts (3 before)", "starts_last3": "Starts (last 3)", "mins_prev3": "Mins (3 before)",
    "mins_last3": "Mins (last 3)", "minutes_rise": "Rise in mins"}), "rising")

# ------------------------------------------------------------------ 3
st.subheader("3. Value and differentials")
st.markdown(
    f"Rule for the table: top {sc.VALUE_TOP_N} per position by xP for GW{gws5[0]}-{gws5[-1]} divided by price, "
    f"among players with at least a {sc.VALUE_MIN_START:.0%} chance of starting GW{gws5[0]} (after injury flags). "
    "The charts show every such player. Cheap players always lead on value: it shows points per pound, not who "
    "scores most.")
pos = st.segmented_control("Position", c.POSITIONS, default="MID", key="value_pos")
first = proj[proj.gw == gws5[0]].set_index("player_id")
pool = players[(players.position == pos) & (players.status != "u")].player_id
pool = [i for i in pool if first.p_start_used.get(i, 0) * first.avail.get(i, 0) >= sc.VALUE_MIN_START]


def scatter(x: pd.Series, xtitle: str, title: str) -> go.Figure:
    fig = go.Figure()
    for group, ids, kw in (("Not in my squad", [i for i in pool if i not in mine], dict(size=10, symbol="circle")),
                           ("In my squad", [i for i in pool if i in mine],
                            dict(size=15, symbol="diamond", line=dict(color=viz.TEXT, width=2)))):
        fig.add_scatter(x=x.reindex(ids), y=xp5.reindex(ids).round(2), mode="markers", name=group, customdata=ids,
                        marker=dict(color=[viz.line(p.team[i]) for i in ids], **kw), text=hover(ids),
                        hovertemplate="%{text}<br>" + xtitle + " %{x:.1f}, xP %{y:.1f}<extra></extra>")
    fig.update_layout(title=title, xaxis_title=xtitle, yaxis_title=XP5)
    return fig


clickable(scatter(p.now_cost / 10, "Price (m)", f"Price against {XP5}: {pos}"),
          "Up and to the left is better: more points for less money. Colour = club. Diamonds are your players: "
          "anyone above and left of a diamond beats him on both counts.", "value")
a, b = st.columns(2)
with a:
    clickable(scatter(p.selected_by_percent, "Owned by all managers (%)", "Ownership against xP"),
              "Top left = differentials: high xP that few managers own.", "diff_all", 380)
with b:
    clickable(scatter(own.reindex(p.index).fillna(0), "Owned by top 1,000 (%)", "Top-1,000 ownership against xP"),
              "Top right = template players the best managers hold: not owning them is the risk.", "diff_top", 380)
v = sc.value(proj, gws5)
vv = v[v.position == pos]
candidates(vv.player_id.tolist(), vv[["player_id", "xp_per_m", "start"]].rename(
    columns={"xp_per_m": "xP per m", "start": "Chance of starting"}), "value")

# ------------------------------------------------------------------ 4
st.subheader("4. Fixture swing")
st.markdown(
    f"Rule: for each club, expected goals per match over the next {sc.SWING_WINDOW} gameweeks against the last "
    f"{sc.SWING_WINDOW}, both priced with today's team ratings, so the swing is only the change in opponents and "
    f"venues. The table lists the {sc.SWING_TOP_CLUBS} biggest improvements, each with its "
    f"{sc.SWING_PLAYERS_PER_CLUB} highest-xP players outside your squad.")
sw = sc.fixture_swing(pg, c.table("fixtures"), c.table("teams"), c.gameweeks())
a, b = st.columns(2)
for holder, col, title, cap in (
        (a, "attack_swing", "Attack: change in expected goals scored per match",
         "Right of zero = easier opponents ahead for the club's attackers than in the last five gameweeks."),
        (b, "defence_swing", "Defence: change in expected goals conceded per match (positive = fewer)",
         "Right of zero = the club should concede less than in the last five gameweeks: good for its defenders.")):
    d = sw.sort_values(col)
    fig = go.Figure(go.Bar(x=d[col].round(2), y=d.team, orientation="h", marker_color=[viz.line(t) for t in d.team],
                           text=d.fixtures, textposition="none", hovertemplate="%{y}: %{x:+.2f}<br>%{text}<extra></extra>"))
    fig.add_vline(x=0, line_color=viz.MUTED)
    fig.update_layout(title=title, xaxis_title="Goals per match", yaxis=dict(tickfont=dict(family=viz.MONO)))
    with holder:
        viz.chart(fig, cap, height=520, key=f"swing_{col}")
side = st.segmented_control("Side", ["Attack", "Defence"], default="Attack", key="swing_side")
if side == "Attack":
    top5 = sw.nlargest(sc.SWING_TOP_CLUBS, "attack_swing")
    spool = players[players.position.isin(["MID", "FWD"])]
else:
    top5 = sw.nlargest(sc.SWING_TOP_CLUBS, "defence_swing")
    spool = players[players.position.isin(["GKP", "DEF"])]
spool = spool[~spool.player_id.isin(mine) & (spool.status != "u")].assign(xp=lambda d: d.player_id.map(xp5))
ids = []
for club in top5.team:
    ids += spool[spool.team == club].nlargest(sc.SWING_PLAYERS_PER_CLUB, "xp").player_id.tolist()
swing_col = "attack_swing" if side == "Attack" else "defence_swing"
candidates(ids, pd.DataFrame({"player_id": ids, "Club swing": [top5.set_index("team")[swing_col][p.team[i]] for i in ids],
                              "Next fixtures": [top5.set_index("team").fixtures[p.team[i]] for i in ids]}), "swing")

st.caption(f"{XP5} includes any boost. " + c.top1k_caption())
