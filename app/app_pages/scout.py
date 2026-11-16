"""Scout: ranked lists of candidates who are not in the squad."""
import pandas as pd
import streamlit as st

import common as c
from fpl.insights import scout as sc
from fpl.insights import signals as sg

st.title("Scout")
st.caption("Lists of players to look at, none of them in your squad. These are prompts for your own judgement: "
           "none of the rules below has been backtested. Understat-based signals (zone matchup, long shots, "
           "set-piece xG) are still blocked because understat.com is offline.")
stamp = c.data_stamp()
players, pg, proj, nm = c.table("players"), c.table("player_gw"), c.proj(), c.names()
p, own = players.set_index("player_id"), c.top1k()
mine = set(c.my_team(stamp)["squad"])
gws5 = c.gameweeks()[:5]
xp5 = c.xp_grid(gws5).sum(axis=1)
XP5 = f"xP GW{gws5[0]}-{gws5[-1]}"


def candidates(ids: list[int], extra: pd.DataFrame, key: str) -> None:
    """Show a candidate table (squad players removed) with a button to open the chosen player."""
    keep = [i for i in ids if i not in mine and i in p.index]
    if not keep:
        st.write("Nobody outside your squad passes this rule right now.")
        return
    df = pd.DataFrame({"Player": nm.reindex(keep).values, "Pos": p.position[keep].values, "Club": p.team[keep].values,
                       "Price": (p.now_cost[keep] / 10).values, "Owned %": p.selected_by_percent[keep].values,
                       "Top 1k %": own.reindex(keep).fillna(0).values, XP5: xp5.reindex(keep).values})
    df = pd.concat([df, extra.set_index("player_id").reindex(keep).reset_index(drop=True)], axis=1)
    ev = st.dataframe(df.round(2), hide_index=True, width="stretch", on_select="rerun",
                      selection_mode="single-row", key=f"tbl_{key}")
    rows = ev.selection.rows
    if st.button("Open player page", key=f"open_{key}", disabled=not rows,
                 help="Select a row first (click the box at its left edge)."):
        st.session_state.player_pick = [keep[rows[0]]]
        st.switch_page("app_pages/player.py")


st.subheader("1. xG underperformers")
st.markdown(
    f"Rule: midfielders and forwards with at least {sg.MIN_MINUTES} minutes who pass all four tests. "
    f"xGI per 90 in the top {round((1 - sg.XGI_PERCENTILE) * 100)}% of the position; goals + assists at least "
    f"{sg.MIN_GAP:.1f} below xGI; started {sg.SECURE_STARTS} of his club's last 5, or minutes rising; owned by "
    f"under {sg.MAX_OWNERSHIP:.0f}% of managers. Ranked by the gap, biggest first.")
u = sg.underperformers(players, pg, flagged_only=True)
candidates(u.player_id.tolist(), u[["player_id", "minutes", "xgi_p90", "xgi", "g_a", "gap", "starts_last5"]].rename(
    columns={"minutes": "Mins", "xgi_p90": "xGI/90", "xgi": "xGI", "g_a": "G+A", "gap": "G+A minus xGI",
             "starts_last5": "Starts (last 5)"}), "under")

st.subheader("2. Minutes rising")
st.markdown(
    f"Rule: over his club's last {sc.RISE_WINDOW} matches against the {sc.RISE_WINDOW} before, more starts, at "
    f"least {sc.MIN_MINUTES_RISE} more minutes, and at least {sc.MIN_RECENT_MINUTES} minutes in the recent window. "
    "Ranked by the rise in minutes.")
m = sc.minutes_rising(pg)
candidates(m.player_id.tolist(), m.rename(columns={
    "starts_prev3": "Starts (3 before)", "starts_last3": "Starts (last 3)", "mins_prev3": "Mins (3 before)",
    "mins_last3": "Mins (last 3)", "minutes_rise": "Rise in mins"}), "rising")

st.subheader("3. Best xP per million")
st.markdown(
    f"Rule: top {sc.VALUE_TOP_N} per position by xP for GW{gws5[0]}-{gws5[-1]} divided by price, among players "
    f"with at least a {sc.VALUE_MIN_START:.0%} chance of starting GW{gws5[0]} (after injury flags). "
    "Cheap players always lead this list: it shows value for money, not who scores most.")
v = sc.value(proj, gws5)
pos = st.segmented_control("Position", c.POSITIONS, default="MID", key="value_pos")
vv = v[v.position == pos]
candidates(vv.player_id.tolist(), vv[["player_id", "xp_per_m", "start"]].rename(
    columns={"xp_per_m": "xP per m", "start": "Chance of starting"}), "value")

st.subheader("4. Fixture swing")
st.markdown(
    f"Rule: for each club, expected goals per match over the next {sc.SWING_WINDOW} gameweeks against the last "
    f"{sc.SWING_WINDOW}, both priced with today's team ratings, so the swing is only the change in opponents and "
    f"venues. The {sc.SWING_TOP_CLUBS} biggest improvements are shown, each with its "
    f"{sc.SWING_PLAYERS_PER_CLUB} highest-xP players outside your squad.")
sw = sc.fixture_swing(pg, c.table("fixtures"), c.table("teams"), c.gameweeks())
side = st.segmented_control("Side", ["Attack", "Defence"], default="Attack", key="swing_side")
if side == "Attack":
    top = sw.nlargest(sc.SWING_TOP_CLUBS, "attack_swing")
    c.show(top[["team", "last_for", "next_for", "attack_swing", "fixtures"]].rename(columns={
        "team": "Club", "last_for": "xG per match, last 5", "next_for": "xG per match, next 5",
        "attack_swing": "Swing", "fixtures": "Next fixtures"}).round(2))
    pool = players[players.position.isin(["MID", "FWD"])]
else:
    top = sw.nlargest(sc.SWING_TOP_CLUBS, "defence_swing")
    c.show(top[["team", "last_against", "next_against", "defence_swing", "fixtures"]].rename(columns={
        "team": "Club", "last_against": "xG against per match, last 5", "next_against": "xG against per match, next 5",
        "defence_swing": "Swing (fewer conceded)", "fixtures": "Next fixtures"}).round(2))
    pool = players[players.position.isin(["GKP", "DEF"])]
pool = pool[~pool.player_id.isin(mine) & (pool.status != "u")].assign(xp=lambda d: d.player_id.map(xp5))
ids = []
for club in top.team:
    ids += pool[pool.team == club].nlargest(sc.SWING_PLAYERS_PER_CLUB, "xp").player_id.tolist()
swing_col = "attack_swing" if side == "Attack" else "defence_swing"
extra = pd.DataFrame({"player_id": ids, "Club swing": [top.set_index("team")[swing_col][p.team[i]] for i in ids]})
candidates(ids, extra, "swing")

st.caption(f"{XP5} includes any boost. " + c.top1k_caption())
