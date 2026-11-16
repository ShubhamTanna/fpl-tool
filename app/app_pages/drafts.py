"""Drafts: saved squads kept apart from the real team, and how they compare with it."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import common as c
import viz
from fpl.user import drafts as dr
from fpl.user import store

HORIZON = 5

st.title("Drafts")
st.caption("Squads you are considering, kept apart from your real team. Stored on this computer only "
           "(data/user/, never committed).")

stamp, r = c.data_stamp(), c.rules()
players, p, nm = c.table("players"), c.table("players").set_index("player_id"), c.names()
gws5 = c.gameweeks()[:HORIZON]
xp5 = c.xp_grid(gws5).sum(axis=1)
all_drafts = store.load("drafts", [])

with st.expander("New draft", expanded=not all_drafts):
    with st.form("new_draft", clear_on_submit=True):
        a, b, d = st.columns([2, 1, 2])
        name = a.text_input("Name")
        start = b.number_input("Start gameweek", 1, 38, c.next_gw())
        source = d.segmented_control("Start from", ["Copy of my team", "Squad builder"], default="Copy of my team")
        note = st.text_input("Note")
        e, f = st.columns(2)
        b_horizon = e.slider("Squad builder: gameweeks to optimise", 1, len(c.gameweeks()), HORIZON)
        b_budget = f.number_input("Squad builder: budget (m)", 80.0, 120.0, r.budget / 10, 0.5)
        if st.form_submit_button("Create draft", type="primary"):
            if not name.strip():
                st.error("Give the draft a name.")
            else:
                if source == "Squad builder":
                    res, errs = c.run_squad(b_horizon, round(b_budget * 10))
                    squad, prices, budget = res["squad"], p.now_cost.to_dict(), round(b_budget * 10)
                else:
                    team = c.my_team(stamp)
                    squad, prices = team["squad"], team["sell_price"]
                    budget = team["bank"] + sum(prices[i] for i in squad)
                    errs = dr.check_draft(squad, sum(prices[i] for i in squad), budget, players, r)
                if errs:
                    st.error("; ".join(errs))
                else:
                    all_drafts.append(dr.new_draft(all_drafts, name.strip(), start, note, squad, prices, budget, source,
                                                   created_gw=c.next_gw()))
                    store.save("drafts", all_drafts)
                    st.rerun()

if not all_drafts:
    st.info("No drafts yet. Create one above.")
    st.stop()

by_id = {d["id"]: d for d in all_drafts}


def title(d: dict) -> str:
    """Draft name, marked wherever its score appears if the start gameweek was already played."""
    return d["name"] + (" (uses hindsight)" if dr.uses_hindsight(d) else "")


pick = st.selectbox("Draft", list(by_id), format_func=lambda i: f"{title(by_id[i])}, from GW{by_id[i]['start_gw']}")
draft = by_id[pick]
squad = dr.current_squad(draft)


def save_draft(new: dict) -> None:
    store.save("drafts", [new if d["id"] == new["id"] else d for d in all_drafts])
    st.rerun()


m = st.columns(4)
m[0].metric("Budget", f"{draft['budget'] / 10:.1f}m")
m[1].metric("Spent", f"{dr.spent(draft) / 10:.1f}m")
m[2].metric("Remaining", f"{dr.remaining(draft) / 10:.1f}m")
errs = dr.check_draft(squad, dr.spent(draft), draft["budget"], players, r)
m[3].metric("Rule check", "Pass" if not errs else "FAIL")
if errs:
    st.error("; ".join(errs))
if draft["note"]:
    st.caption(f"Note: {draft['note']}  |  Source: {draft['source']}  |  Created {draft['created_at'][:10]}")

look = max(c.next_gw(), draft["start_gw"])
res = c.auto_pick(tuple(dr.squad_at(draft, look)), look, stamp) if look in c.gameweeks() else None
if res:
    a, b = st.columns(2)
    with a:
        viz.chart(viz.pitch(c.cards(res, look), f"{title(draft)}: GW{look}, {res['xp']:.1f} xP"), c.PITCH_CAPTION,
                  height=540, key="pitch_draft")
    with b:
        mine_now = c.auto_pick(tuple(c.my_team(stamp)["squad"]), look, stamp) if look == c.next_gw() else None
        if mine_now:
            viz.chart(viz.pitch(c.cards(mine_now, look), f"My team: GW{look}, {mine_now['xp']:.1f} xP"),
                      "Your real squad with the same auto-pick, to compare card by card with the draft.",
                      height=540, key="pitch_mine")
        else:
            st.info("The side-by-side pitch appears for drafts that start by the next gameweek.")
    role = {res["captain"]: "Captain", res["vice"]: "Vice"}
    ids = res["xi"] + res["bench"]
    extra = {"Slot": ["XI"] * len(res["xi"]) + [f"Bench {k}" for k in range(1, len(res["bench"]) + 1)],
             "Role": [role.get(i, "") for i in ids], "Paid": [draft["prices"][str(i)] / 10 for i in ids]}
    c.show(c.breakdown(ids, gws5, extra), height=563)
    st.caption(f"XI, bench and captain are the optimizer's pick for GW{look}. xP and its parts are totals for "
               f"GW{gws5[0]}-{gws5[-1]}. Paid = selling price for players copied from your team, purchase price "
               "for players added here. " + c.top1k_caption())
else:
    c.show(c.breakdown(squad, gws5), height=563)

st.subheader("Swap a player")
a, b = st.columns(2)
order = sorted(squad, key=lambda i: (c.POSITIONS.index(p.position[i]), -xp5.get(i, 0)))
out_id = a.selectbox("Out", order, format_func=lambda i: f"{nm[i]} ({p.team[i]}, {p.position[i]}) "
                                                         f"{draft['prices'][str(i)] / 10:.1f}m | xP {xp5.get(i, 0):.1f}")
cands = players[(players.position == p.position[out_id]) & ~players.player_id.isin(squad) & (players.status != "u")]
cands = sorted(cands.player_id, key=lambda i: -xp5.get(i, 0))
free = dr.remaining(draft) + draft["prices"][str(out_id)]
in_id = b.selectbox("In (type to search)", cands, format_func=lambda i: (
    f"{nm[i]} ({p.team[i]}) {p.now_cost[i] / 10:.1f}m | xP {xp5.get(i, 0):.1f} | "
    f"left {(free - p.now_cost[i]) / 10:.1f}m"))
st.caption(f"xP is the total for GW{gws5[0]}-{gws5[-1]}. 'left' is the budget remaining after the swap; "
           "a negative figure cannot be bought.")
if st.button("Make swap", type="primary"):
    new, errs = dr.swap(draft, out_id, in_id, players, r, c.next_gw())
    if errs:
        st.error("Swap refused: " + "; ".join(errs))
    else:
        save_draft(new)

with st.expander("Rename, edit note or delete"):
    with st.form("edit_draft"):
        new_name = st.text_input("Name", draft["name"])
        new_note = st.text_input("Note", draft["note"])
        new_start = st.number_input("Start gameweek", 1, 38, draft["start_gw"])
        if st.form_submit_button("Save"):
            first = min(int(k) for k in draft["squads"])
            squads = dict(draft["squads"])
            if new_start < first:                      # an earlier start reuses the first squad
                squads[str(int(new_start))] = squads[str(first)]
            save_draft({**draft, "name": new_name.strip() or draft["name"], "note": new_note,
                        "start_gw": int(new_start), "squads": squads})
    sure = st.checkbox("I want to delete this draft", key=f"sure_{pick}")
    if st.button("Delete draft", disabled=not sure):
        store.save("drafts", [d for d in all_drafts if d["id"] != pick])
        st.rerun()

st.subheader("Compare with my team")
chosen = st.multiselect("Drafts to compare", list(by_id), default=[pick], format_func=lambda i: title(by_id[i]))
if chosen:
    team, done = c.my_team(stamp), c.finished_gws()
    first = min(by_id[i]["start_gw"] for i in chosen)
    played, ahead = [g for g in done if g >= first], c.gameweeks()
    gws_all = played + ahead

    def draft_score(d: dict, gw: int):
        if gw < d["start_gw"]:
            return None
        res = c.auto_pick(tuple(dr.squad_at(d, gw)), gw, stamp)
        return None if res is None else (res["actual"] if gw in done else res["xp"])

    official = [team["gw_points"].get(g, 0) - team["gw_hits"].get(g, 0) for g in played]
    same = [c.real_like_for_like(g, stamp) for g in played]
    mine_ahead = [c.auto_pick(tuple(team["squad"]), g, stamp)["xp"] for g in ahead]
    out = pd.DataFrame({"GW": gws_all, "Status": ["played"] * len(played) + ["projected"] * len(ahead),
                        "My team, official": pd.Series(official + [float("nan")] * len(ahead), dtype="float"),
                        "My team, same method": same + mine_ahead})
    base = pd.Series(same + mine_ahead, dtype="float")
    scores = {}
    for i in chosen:
        d = by_id[i]
        scores[i] = pd.Series([draft_score(d, g) for g in gws_all], dtype="float")
        out[title(d)] = scores[i]
        out[f"{title(d)} - mine"] = scores[i] - base
        out[f"{title(d)} running"] = (scores[i] - base).cumsum()

    palette = [viz.ACCENT, "#A78BFA", viz.WARN, "#F472B6", "#4C9AFF"]
    x = [f"GW{g}" for g in gws_all]
    n = len(played)
    fig = go.Figure()

    def add_line(name: str, vals: pd.Series, colour: str, width: float = 2.5) -> None:
        """Cumulative points: solid for played gameweeks, dashed for projected ones."""
        cum = vals.cumsum()
        if n:
            fig.add_scatter(x=x[:n], y=cum[:n].round(1), name=name, mode="lines+markers", legendgroup=name,
                            line=dict(color=colour, width=width))
        fig.add_scatter(x=x[max(n - 1, 0):], y=cum[max(n - 1, 0):].round(1), name=name + " (projected)",
                        mode="lines+markers", legendgroup=name, showlegend=not n,
                        line=dict(color=colour, width=width, dash="dash"))

    add_line("My team, same method", base, viz.TEXT)
    if n:
        fig.add_scatter(x=x[:n], y=pd.Series(official).cumsum(), name="My team, official", mode="lines+markers",
                        line=dict(color=viz.MUTED, width=1.5, dash="dot"))
    for k, i in enumerate(chosen):
        add_line(title(by_id[i]), scores[i], palette[k % len(palette)])
    fig.update_layout(title=f"Cumulative points from GW{gws_all[0]}", yaxis_title="Points")
    viz.chart(fig, "Solid = points actually scored, dashed = projected. A draft is ahead of your team where its "
                   "line is above the white one. The dotted grey line is your official FPL score, which also "
                   "counts automatic substitutions, chips and hits.", height=380, key="cum")

    fig = go.Figure()
    for k, i in enumerate(chosen):
        diff = (scores[i] - base).round(1)
        fig.add_bar(x=x, y=diff, name=title(by_id[i]), marker_color=palette[k % len(palette)],
                    marker_pattern_shape=[""] * n + ["/"] * len(ahead))
    fig.add_hline(y=0, line_color=viz.MUTED)
    fig.update_layout(barmode="group", title="Draft minus my team, per gameweek", yaxis_title="Points")
    viz.chart(fig, "Above zero = the draft beat your team that week (same scoring method on both sides). "
                   "Hatched bars are projections, not results.", height=300, key="diff")

    c.show(out, decimals=1)
    st.caption("Like for like: 'My team, same method' and every draft are scored the same way: the squad held "
               "that gameweek, the optimizer's XI chosen from the projection made beforehand, captain doubled, "
               "no automatic substitutions, no chips, no hits. 'My team, official' is FPL's score minus hits. "
               "Differences and running totals use the same-method score. A draft marked 'uses hindsight' was "
               "given a start gameweek that had already been played, so its past score is not a fair test.")

st.download_button("Export drafts and boosts (zip)", store.export_zip(), "fpl-user-data.zip", "application/zip")
