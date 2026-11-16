"""Projections: xP for every player, with every part of it."""
import streamlit as st

import common as c

st.title("Projections")
st.caption("Expected points (xP) per player, built from minutes, team strength, xG/xA, clean sheets, saves, "
           "defensive contribution, bonus and cards. Boosted players are marked and include their boost.")
proj, gws, nm = c.proj(), c.gameweeks(), c.names()
a, b, d, e = st.columns(4)
lo, hi = a.select_slider("Gameweeks", gws, (gws[0], gws[0]))
pos = b.multiselect("Position", c.POSITIONS, c.POSITIONS)
clubs = d.multiselect("Club", sorted(proj.team.unique()))
max_price = e.number_input("Max price (m)", 3.5, 20.0, 20.0, 0.5)
sel = proj[proj.gw.between(lo, hi) & proj.position.isin(pos) & (proj.now_cost <= max_price * 10)]
if clubs:
    sel = sel[sel.team.isin(clubs)]
agg = sel.groupby(["player_id", "position", "team", "now_cost"], as_index=False).agg(
    opp=("opp", ", ".join), start=("p_start_used", "mean"), xmins=("xmins", "sum"),
    **{k: (k, "sum") for k in c.PARTS}, xp=("xp", "sum"))
agg["Player"] = agg.player_id.map(nm)
agg["Price"] = agg.now_cost / 10
agg["xP per m"] = agg.xp / agg.Price
agg["Top 1k %"] = agg.player_id.map(c.top1k()).fillna(0)
out = agg.sort_values("xp", ascending=False).rename(columns={
    "position": "Pos", "team": "Club", "opp": "Fixtures", "start": "Chance of starting", "xmins": "xMins",
    "xp": "xP", **c.PARTS})
cols = ["Player", "Pos", "Club", "Price", "Top 1k %", "Fixtures", "Chance of starting", "xMins", "xP", "xP per m"]
c.show(out[cols + list(c.PARTS.values())].round(2), height=640)
st.caption("Known weak spots: players back from injury are underrated, one big match can inflate a defender's "
           "goal threat, and team ratings rest on few matches. Backtest results are on the Model lab page. "
           + c.top1k_caption())
