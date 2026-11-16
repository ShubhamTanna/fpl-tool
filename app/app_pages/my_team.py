"""My team: transfer plan, XI, bench and captain for Shubham's own team."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
from fpl import pipeline
from fpl.optimize.checker import check_plan
from fpl.optimize.models import MIN_GAIN, plan_transfers


@st.cache_data(show_spinner=False)
def run_plan(stamp: float, horizon: int, ft_override: int | None, min_gain: float,
             lock: tuple, ban: tuple, max_transfers: int | None):
    r, players, proj = c.rules(), c.table("players"), c.proj()
    gws = c.gameweeks()[:horizon]
    team = dict(c.my_team(stamp))
    if ft_override is not None:
        team["free_transfers"] = ft_override
    plan = plan_transfers(team, proj, players, r, gws, min_gain=min_gain, lock=list(lock), ban=list(ban),
                          max_transfers=max_transfers)
    hold = plan_transfers(team, proj, players, r, gws, allow_transfers=False)
    errs = check_plan(plan, team, players, r) + check_plan(hold, team, players, r)
    return team, plan, hold, errs


st.title("My team")
head = st.container(horizontal=True, vertical_alignment="bottom")
head.caption(f"{c.deadline_text()}. Data last built "
             f"{pd.Timestamp(c.data_stamp(), unit='s', tz='UTC').tz_convert(c.IST):%a %d %b, %H:%M} IST.")
rescan = head.checkbox("Also re-scan top 1,000", help="Re-reads the squads of the top 1,000 managers for the "
                       "ownership columns. One request per manager: about 17 minutes.")
if head.button("Refresh data", help="Fetches prices, injury news and fixtures, then rebuilds projections. "
                                    "After a gameweek it also re-reads every player's match history, "
                                    "which takes about 12 minutes at one request per second."):
    with st.status("Refreshing data...", expanded=True) as status:
        bar = st.progress(0.0, text="Fetching FPL data")
        info = pipeline.refresh(lambda i, n: bar.progress(i / n, text=f"Player histories {i}/{n}"))
        if rescan:
            n = pipeline.rebuild_template(progress=lambda i, n: bar.progress(i / n, text=f"Top managers {i}/{n}"))
            st.write(f"Template re-scanned: {n} managers.")
        st.cache_data.clear()
        status.update(label=f"Done: {info['players']} players, {info['matches']} matches, next GW{info['next_gw']}.",
                      state="complete")
    st.rerun()

stamp = c.data_stamp()
try:
    base_team = c.my_team(stamp)
except Exception as e:  # .env missing, FPL API down
    st.error(f"Could not load your team: {e}")
    st.stop()

lab, p, proj = c.labels(), c.table("players").set_index("player_id"), c.proj()
with st.form("plan_controls"):
    a, b, d, e = st.columns(4)
    horizon = a.slider("Gameweeks to plan", 1, 5, 5)
    min_gain = b.number_input("Minimum gain per transfer (xP)", 0.0, 10.0, MIN_GAIN, 0.5,
                              help="A transfer is suggested only if it adds more than this many xP over the "
                                   "gameweeks planned. Higher = roll transfers more often.")
    max_tr = d.selectbox("Max transfers per gameweek", ["No limit", 0, 1, 2, 3], index=0)
    ft_choice = e.selectbox("Free transfers", ["Work it out", 0, 1, 2, 3, 4, 5],
                            help="FPL does not publish this. 'Work it out' replays your season.")
    f, g = st.columns(2)
    lock = f.multiselect("Lock (never sell)", base_team["squad"], format_func=lab.get)
    ban = g.multiselect("Ban (never buy)", [i for i in lab if i not in base_team["squad"]], format_func=lab.get)
    st.form_submit_button("Update plan", type="primary")

with st.spinner("Solving..."):
    team, plan, hold, errs = run_plan(stamp, horizon, None if ft_choice == "Work it out" else ft_choice,
                                      min_gain, tuple(lock), tuple(ban), None if max_tr == "No limit" else max_tr)
r, nm = c.rules(), c.names()
gws = [x["gw"] for x in plan["gws"]]

st.subheader(team["name"])
if team["pending"]:
    moves = ", ".join(f"{nm[o]} to {nm[i]}" for o, i in team["pending"])
    st.info(f"Transfers already made for GW{gws[0]} are applied: {moves}."
            + (f" Hits taken: {team['hits_taken']}." if team["hits_taken"] else ""))
m = st.columns(4)
m[0].metric("Bank", f"{team['bank'] / 10:.1f}m")
m[1].metric("Free transfers", team["free_transfers"],
            help=f"Replaying your season gives {base_team['free_transfers']}.")
m[2].metric(f"Plan xP, GW{gws[0]}-{gws[-1]}", f"{plan['xp_net']:.1f}",
            f"{plan['xp_net'] - hold['xp_net']:+.1f} vs no transfers")
m[3].metric("Rule check", "Pass" if not errs else "FAIL")
if errs:
    st.error("The plan broke a rule: " + "; ".join(errs))

fig = go.Figure()
fig.add_bar(name="No transfers", x=[f"GW{x}" for x in gws], y=[round(h["xp_net"], 1) for h in hold["gws"]],
            marker_color=viz.MUTED, text=[f"{h['xp_net']:.1f}" for h in hold["gws"]], textposition="outside")
fig.add_bar(name="Plan (after hits)", x=[f"GW{x}" for x in gws], y=[round(g["xp_net"], 1) for g in plan["gws"]],
            marker_color=viz.ACCENT, text=[f"{g['xp_net']:.1f}" for g in plan["gws"]], textposition="outside")
lo = min(h["xp_net"] for h in hold["gws"] + plan["gws"])
fig.update_layout(barmode="group", yaxis=dict(title="xP", range=[lo * 0.85, None]), title="Plan against no transfers")
viz.chart(fig, "Look for the gameweeks where the plan's bar clears the grey one: that is where the transfers pay. "
               "The y-axis does not start at zero. The gain is measured with the same projections that chose "
               "the transfers, so it is an upper estimate.", height=300)

for tab, g, h in zip(st.tabs([f"GW{x}" for x in gws]), plan["gws"], hold["gws"]):
    with tab:
        a, b, d = st.columns(3)
        a.metric("xP after hits", f"{g['xp_net']:.1f}", f"{g['xp_net'] - h['xp_net']:+.1f} vs no transfers")
        b.metric("Free transfers / hits", f"{g['free_transfers']} / {g['hits']}",
                 f"-{g['hits'] * r.hit_cost} pts" if g["hits"] else None, delta_color="inverse")
        d.metric("Bank after", f"{g['bank'] / 10:.1f}m")
        if g["transfers_in"]:
            outs = sorted(g["transfers_out"], key=lambda i: p.position[i])
            ins = sorted(g["transfers_in"], key=lambda i: p.position[i])
            rest = [x for x in gws if x >= g["gw"]]
            xo, xi = c.breakdown(outs, rest), c.breakdown(ins, rest)
            c.show(pd.DataFrame({
                "Out": xo.Player, "Club": xo.Club, f"Out xP GW{rest[0]}-{rest[-1]}": xo.xP,
                "In": xi.Player, "In club": xi.Club, "In price": xi.Price,
                f"In xP GW{rest[0]}-{rest[-1]}": xi.xP, "In top 1k %": xi["Top 1k %"]}), decimals=1)
            grid = c.xp_grid(rest)
            for col, o, i in zip(st.columns(len(outs)), outs, ins):
                f2 = go.Figure()
                f2.add_bar(name=f"Out: {nm[o]}", x=[f"GW{x}" for x in rest], y=grid.loc[o, rest].round(2),
                           marker_color=viz.line(p.team[o]), marker_pattern_shape="/")
                f2.add_bar(name=f"In: {nm[i]}", x=[f"GW{x}" for x in rest], y=grid.loc[i, rest].round(2),
                           marker_color=viz.line(p.team[i]))
                f2.update_layout(barmode="group", yaxis_title="xP")
                with col:
                    viz.chart(f2, "Solid = player coming in, hatched = player going out. Look for weeks where "
                                  "the solid bar is not higher: the swap is not a gain every week.", height=250,
                              key=f"swap_{g['gw']}_{o}_{i}")
        else:
            st.write("No transfers this week: roll the free transfer.")
        viz.chart(viz.pitch(c.cards(g, g["gw"])), c.PITCH_CAPTION, height=560, key=f"pitch_{g['gw']}")
        role = {g["captain"]: "Captain", g["vice"]: "Vice"}
        ids = g["xi"] + g["bench"]
        c.show(c.breakdown(ids, [g["gw"]], {
            "Slot": ["XI"] * len(g["xi"]) + [f"Bench {k}" for k in range(1, len(g["bench"]) + 1)],
            "Role": [role.get(i, "") for i in ids]}), height=563)

st.subheader("Current squad")
ids = team["squad"]
sq = proj[proj.gw.isin(gws) & proj.player_id.isin(ids)].groupby("player_id")[list(c.PARTS)].sum()
sq = sq.loc[sq.sum(axis=1).sort_values(ascending=False).index]
viz.chart(viz.stacked_parts(viz.parts_frame(sq), [f"{nm[i]} ({p.team[i]})" for i in sq.index],
                            title=f"Where each player's xP comes from, GW{gws[0]}-{gws[-1]}"),
          "Look at what each total is made of: a bar that is mostly grey (appearance points) has little upside; "
          "blue and purple (goals, assists) are the volatile part. Red left of zero = points lost to goals "
          "conceded and cards.", height=470)
c.show(c.breakdown(ids, gws, {
    "Bought": [team["purchase_price"][i] / 10 for i in ids],
    "Sell": [team["sell_price"][i] / 10 for i in ids],
    "Status": [p.status[i] for i in ids], "News": [p.news[i] for i in ids]}), height=563)
st.caption(f"xP and its parts are totals for GW{gws[0]}-{gws[-1]}. Selling prices are estimates from the 50% "
           "rule: purchase price plus half of any rise, rounded down. " + c.top1k_caption())

st.subheader("Fixtures")
every = st.toggle("Show all 20 clubs", value=False)
ticker = c.table("ticker")
mine = sorted(set(p.team[ids]))


def heat(value: str, good_high: bool, title: str) -> go.Figure:
    t = ticker if every else ticker[ticker.team.isin(mine)]
    z = t.pivot(index="team", columns="gw", values=value)
    z = z.loc[z.sum(axis=1).sort_values(ascending=not good_high).index]
    text = t.pivot(index="team", columns="gw", values="opp").loc[z.index]
    label = text + "<br>" + z.map("{:.2f}".format)
    scale = [[0, "#B03A3A"], [0.5, "#2A3441"], [1, "#1F8F52"]]
    fig = go.Figure(go.Heatmap(z=z.values, x=[f"GW{g}" for g in z.columns], y=list(z.index), text=label.values,
                               texttemplate="%{text}", textfont=dict(size=11, family=viz.MONO, color=viz.TEXT),
                               colorscale=scale if good_high else [[0, "#1F8F52"], [0.5, "#2A3441"], [1, "#B03A3A"]],
                               zmin=ticker[value].min(), zmax=ticker[value].max(), showscale=False, xgap=2, ygap=2,
                               hovertemplate="%{y} %{x}: %{z:.2f}<extra></extra>"))
    fig.update_layout(title=title, yaxis=dict(autorange="reversed", tickfont=dict(family=viz.SANS)), xaxis=dict(side="top"))
    return fig


a, b = st.columns(2)
rows = 20 if every else len(mine)
with a:
    viz.chart(heat("xg_for", True, "Attack: expected goals scored"),
              "Green = the club is expected to score more. Use it for your attackers and for captain choices.",
              height=110 + 36 * rows, key="heat_att")
with b:
    viz.chart(heat("xg_against", False, "Defence: expected goals conceded"),
              "Green = the club is expected to concede less. Use it for your defenders and goalkeeper.",
              height=110 + 36 * rows, key="heat_def")
st.caption("From our own xG-based team ratings, not the official FDR. Each cell shows the opponent and the "
           "expected goals; best run at the top. Colours are scaled across all 20 clubs. Ratings rest on few "
           "matches, so small gaps are noise.")
