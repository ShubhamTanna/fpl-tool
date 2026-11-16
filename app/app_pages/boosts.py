"""Boosts: Shubham's manual adjustments, logged and later scored against what happened."""
import json

import pandas as pd
import streamlit as st

import common as c
from fpl.model.xp import project
from fpl.user import boosts as bo
from fpl.user import store

st.title("Boosts")
st.caption("Your own adjustment to a player's projection, for what the data cannot see (eye test, new manager, "
           "role change). Boosts feed My team, Drafts, Player, Scout and Projections, where boosted players "
           f"are marked '{c.BOOST_MARK.strip()}'. Every boost is logged and scored once it has ended.")
stamp, nxt = c.data_stamp(), c.next_gw()
players, lab = c.table("players"), c.labels()
raw = c.table("players").set_index("player_id").web_name
log = store.load("boosts", [])
done = c.finished_gws()

with st.form("new_boost", clear_on_submit=True):
    a, b = st.columns([2, 1])
    order = players.sort_values("total_points", ascending=False).player_id.tolist()
    pid = a.selectbox("Player (type to search)", order, format_func=lab.get)
    kind = b.segmented_control("Type", ["output", "minutes"], default="output")
    d, e, f = st.columns(3)
    mult = d.number_input("Output: multiplier on goals and assists", 0.1, 3.0, 1.2, 0.05,
                          help="1.2 = 20% more goal and assist points. Used when the type is output.")
    start_pct = e.number_input("Minutes: chance of starting (%)", 0, 100, 90, 5,
                               help="Replaces the model's chance of starting. Used when the type is minutes.")
    end_gw = f.number_input("End gameweek", nxt, 38, min(38, nxt + 2), help=f"The boost runs from GW{nxt} to this gameweek.")
    reason = st.text_input("Reason (required)")
    if st.form_submit_button("Add boost", type="primary"):
        value = mult if kind == "output" else start_pct / 100
        log, errs = bo.add(log, pid, raw[pid], kind, value, nxt, end_gw, reason)
        if errs:
            st.error("; ".join(errs))
        else:
            store.save("boosts", log)
            st.rerun()


def describe(b: dict) -> str:
    return f"x{b['value']:.2f} goals and assists" if b["type"] == "output" else f"starts {b['value']:.0%}"


st.subheader("In force")
live = bo.live(log, nxt)
if live:
    with_b, without = c.proj(), c.base_proj(stamp)
    rows = []
    for b in live:
        span = lambda d: d[(d.player_id == b["player_id"]) & d.gw.between(max(b["start_gw"], nxt), b["end_gw"])].xp.sum()  # noqa: E731
        rows.append({"Player": b["web_name"], "Type": b["type"], "Boost": describe(b),
                     "Gameweeks": f"GW{b['start_gw']}-{b['end_gw']}", "xP without": span(without),
                     "xP with": span(with_b), "Change": span(with_b) - span(without),
                     "Reason": b["reason"], "Added": b["created_at"][:10]})
    c.show(pd.DataFrame(rows).round(2))
    st.caption("xP without / with: totals over the boost's remaining gameweeks. 'with' includes every boost on that player.")
    a, b_ = st.columns([3, 1], vertical_alignment="bottom")
    which = a.selectbox("Cancel a boost", [b["id"] for b in live], format_func=lambda i: next(
        f"{b['web_name']}: {describe(b)}, GW{b['start_gw']}-{b['end_gw']}" for b in live if b["id"] == i))
    if b_.button("Cancel boost"):
        store.save("boosts", bo.cancel(log, which, max(done)))
        st.rerun()
else:
    st.write("No boosts in force.")


@st.cache_data(show_spinner=False)
def score(boost_json: str, stamp: float) -> dict:
    """Model xP without the boost, with it, and actual points, over the boost's gameweeks.
    Each gameweek is projected from the matches before it; injury flags of the time are not available."""
    b = json.loads(boost_json)
    t, pts = c.tables(), c.actual_points(stamp)
    out = {"without": 0.0, "with": 0.0, "actual": 0}
    for gw in range(b["start_gw"], b["end_gw"] + 1):
        for key, boosts in (("without", None), ("with", [b])):
            d, _ = project(t, as_of_gw=gw - 1, horizon=1, use_availability=False, boosts=boosts)
            out[key] += float(d.loc[d.player_id == b["player_id"], "xp"].sum())
        out["actual"] += int(pts[gw].get(b["player_id"], 0)) if gw in pts else 0
    return out


st.subheader("Scored: boosts that have ended")
ended = bo.ended(log, max(done))
if ended:
    rows = []
    for b in ended:
        s = score(json.dumps(b, sort_keys=True), stamp)
        rows.append({"Player": b["web_name"], "Boost": describe(b), "Gameweeks": f"GW{b['start_gw']}-{b['end_gw']}",
                     "xP without boost": s["without"], "xP with boost": s["with"], "Actual points": s["actual"],
                     "Error without": s["without"] - s["actual"], "Error with": s["with"] - s["actual"],
                     "Boost helped": ("no change" if abs(s["with"] - s["without"]) < 0.005 else
                                      "yes" if abs(s["with"] - s["actual"]) < abs(s["without"] - s["actual"]) else "no"),
                     "Reason": b["reason"]})
    df = pd.DataFrame(rows)
    c.show(df.round(2))
    st.caption(f"{(df['Boost helped'] == 'yes').sum()} of {len(df)} ended boosts moved the projection closer to "
               "the actual points. Each gameweek is re-projected from the matches before it, without the injury "
               "flags of the time. A few boosts prove nothing either way: points are noisy.")
else:
    st.write("No boost has ended yet.")

st.subheader("Log")
if log:
    c.show(pd.DataFrame([{"Id": b["id"], "Player": b["web_name"], "Type": b["type"], "Value": b["value"],
                          "From GW": b["start_gw"], "To GW": b["end_gw"], "Reason": b["reason"],
                          "Added (UTC)": b["created_at"], "Cancelled (UTC)": b["cancelled_at"] or ""}
                         for b in reversed(log)]))
else:
    st.write("Nothing logged yet.")
st.download_button("Export drafts and boosts (zip)", store.export_zip(), "fpl-user-data.zip", "application/zip")
