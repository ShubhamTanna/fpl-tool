"""Player: everything on file about one player, or 2 to 4 players side by side."""
import pandas as pd
import streamlit as st

import common as c
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

if len(ids) > 1:
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
    st.line_chart(xp, x_label="Gameweek", y_label="xP", alt="xP per gameweek for the chosen players")
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
    c.show(past.round(2)) if len(past) else st.write("No past Premier League season on file.")

st.subheader("Ownership and price")
trend = log.sort_values("GW").drop_duplicates("GW", keep="last").set_index("GW")
a, b, d = st.columns(3)
a.line_chart(trend["Owned by"], y_label="Managers", alt="Number of managers owning the player by gameweek")
b.bar_chart(trend["Net transfers"], y_label="Net transfers in", alt="Net transfers in by gameweek")
d.line_chart(trend["Price"], y_label="Price (m)", alt="Price by gameweek")
st.caption(f"Transfers this gameweek so far: {int(p.transfers_in_event):,} in, {int(p.transfers_out_event):,} out.")

st.subheader("Record against upcoming opponents")
upcoming = proj[(proj.player_id == pid) & (proj.n_fixtures > 0)].opp.str.split(" + ", regex=False).explode()
opps = list(dict.fromkeys(o.split("(")[0] for o in upcoming))
c.show(pv.record_vs(pid, players, c.table("history_gw"), opps).round(2))
st.caption("Display only, not in xP. Matches he played against each club since 2022-23 (xG from 2022-23 GW16 "
           "onward). A handful of matches says very little.")
