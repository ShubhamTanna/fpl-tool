"""Pages carried over from Section 5. Each is replaced or folded in during Step 7."""
import pandas as pd
import streamlit as st

from common import PARTS, POSITIONS, gameweeks, player_rows, proj, rules, run_squad, show, table
from fpl.insights import signals as sig_rules


def page_squad_builder() -> None:
    st.title("Squad Builder")
    st.caption("The best 15 from scratch under the game rules, for the gameweeks you choose.")
    r = rules()
    c1, c2 = st.columns(2)
    horizon = c1.slider("Gameweeks to optimise", 1, len(gameweeks()), 5)
    budget = c2.number_input("Budget (m)", 80.0, 120.0, r.budget / 10, 0.5)
    with st.spinner("Solving..."):
        res, errs = run_squad(horizon, round(budget * 10))
    gws = [g["gw"] for g in res["gws"]]
    first = res["gws"][0]
    m = st.columns(3)
    m[0].metric("Squad cost", f"{res['cost'] / 10:.1f}m")
    m[1].metric(f"XI + captain xP, GW{gws[0]}", f"{first['xp']:.1f}")
    m[2].metric("Rule check", "Pass" if not errs else "FAIL")
    if errs:
        st.error("; ".join(errs))
    role = {first["captain"]: "Captain", first["vice"]: "Vice"}
    ids = first["xi"] + first["bench"]
    show(player_rows(ids, gws, {
        "Slot": ["XI"] * len(first["xi"]) + [f"Bench {k}" for k in range(1, len(first["bench"]) + 1)],
        "Role": [role.get(i, "") for i in ids]}), height=563)
    st.caption(f"XI, bench and captain shown are for GW{gws[0]}. Later gameweeks count 10% less each.")


def page_projections() -> None:
    st.title("Projections")
    st.caption("Expected points (xP) per player, built from minutes, team strength, xG/xA, clean sheets, "
               "saves, defensive contribution, bonus and cards.")
    proj_, gws = proj(), gameweeks()
    c1, c2, c3, c4 = st.columns(4)
    lo, hi = c1.select_slider("Gameweeks", gws, (gws[0], gws[0]))
    pos = c2.multiselect("Position", POSITIONS, POSITIONS)
    clubs = c3.multiselect("Club", sorted(proj_.team.unique()))
    max_price = c4.number_input("Max price (m)", 3.5, 20.0, 20.0, 0.5)
    d = proj_[proj_.gw.between(lo, hi) & proj_.position.isin(pos) & (proj_.now_cost <= max_price * 10)]
    if clubs:
        d = d[d.team.isin(clubs)]
    agg = d.groupby(["player_id", "web_name", "position", "team", "now_cost"], as_index=False).agg(
        opp=("opp", ", ".join), xmins=("xmins", "sum"), **{c: (c, "sum") for c in PARTS}, xp=("xp", "sum"))
    agg["Price"] = agg.now_cost / 10
    agg["xP per m"] = agg.xp / agg.Price
    out = agg.sort_values("xp", ascending=False).rename(columns={
        "web_name": "Player", "position": "Pos", "team": "Club", "opp": "Fixtures", "xmins": "xMins",
        "xp": "xP", **PARTS})
    cols = ["Player", "Pos", "Club", "Price", "Fixtures", "xMins", "xP", "xP per m"] + list(PARTS.values())
    show(out[cols].round(2), height=600)
    st.caption("Known weak spots: players back from injury are underrated, one big match can inflate a "
               "defender's goal threat, and team ratings rest on few matches. Backtest results are on the "
               "Model lab page.")


def page_template() -> None:
    st.title("Template")
    picks, t = table("top_picks"), table("template")
    n = picks.entry.nunique()
    gw = gameweeks()[0] - 1
    st.caption(f"What the top {n:,} overall managers held in GW{gw}. Effective ownership (EO) is the average "
               "multiplier: bench 0, starter 1, captain 2. At 150% EO, a player costs you 1.5x his points "
               "if you do not own him.")
    c1, c2 = st.columns([2, 1])
    out = t.rename(columns={"web_name": "Player", "position": "Pos", "team": "Club", "price": "Price",
                            "owned_pct": "Owned %", "start_pct": "Started %", "captain_pct": "Captain %",
                            "eo_pct": "EO %", "overall_owned_pct": "All managers %"})
    cols = ["Player", "Pos", "Club", "Price", "Owned %", "Started %", "Captain %", "EO %", "All managers %"]
    with c1:
        st.subheader("Ownership")
        show(out[cols].round(1), height=600)
    with c2:
        st.subheader("Captaincy")
        cap = out[out["Captain %"] >= 1].sort_values("Captain %", ascending=False)
        st.bar_chart(cap, x="Player", y="Captain %", sort=False, horizontal=True)
        chips = picks.drop_duplicates("entry").chip.fillna("none").value_counts()
        st.subheader("Chips played")
        show(chips.rename_axis("Chip").reset_index(name="Managers"))


def page_signals() -> None:
    st.title("Signals")
    st.subheader("xG underperformers")
    st.caption("Attackers creating chances that have not yet turned into goals and assists, with secure "
               "minutes and low ownership. A list to review, not a buy list: this method has not been backtested.")
    s = table("signals")
    st.markdown(
        f"A player is flagged when he passes all four tests: xGI per 90 in the top "
        f"{round((1 - sig_rules.XGI_PERCENTILE) * 100)}% of his position (min {sig_rules.MIN_MINUTES} minutes); "
        f"goals + assists at least {sig_rules.MIN_GAP:.1f} below xGI; started {sig_rules.SECURE_STARTS} of his "
        f"club's last 5, or minutes rising; owned by under {sig_rules.MAX_OWNERSHIP:.0f}% of managers.")
    names = {"web_name": "Player", "position": "Pos", "team": "Club", "price": "Price", "owned_pct": "Owned %",
             "minutes": "Minutes", "xgi_p90": "xGI/90", "xgi": "xGI", "g_a": "G+A", "gap": "G+A minus xGI",
             "starts_last5": "Starts (last 5)", "high_xgi": "High xGI", "underperforming": "Underperforming",
             "secure_or_rising": "Secure minutes", "low_owned": "Low owned"}
    base = list(names.values())[:11]
    st.markdown(f"**Flagged: {int(s.flag.sum())} of {len(s)} attackers**")
    show(s[s.flag].rename(columns=names)[base].round(2))
    if st.toggle("Show near misses (3 of 4 tests, underperforming)"):
        near = s[(s.tests_passed == 3) & s.underperforming]
        show(near.rename(columns=names)[base + ["High xGI", "Secure minutes", "Low owned"]].round(2))


def _ticker_grid(ticker: pd.DataFrame, value: str, best_high: bool):
    vals = ticker.pivot(index="team", columns="gw", values=value)
    text = ticker.assign(cell=ticker.opp + "  " + ticker[value].map("{:.2f}".format)).pivot(
        index="team", columns="gw", values="cell")
    order = vals.sum(axis=1).sort_values(ascending=not best_high).index
    vals, text = vals.loc[order], text.loc[order]
    lo, hi = vals.values.min(), vals.values.max()

    def colour(_):
        score = (vals - lo) / (hi - lo)              # 0..1, low to high
        good = score if best_high else 1 - score     # 1 = good fixture
        return good.map(lambda g: f"background-color: rgba({'46,160,67' if g >= 0.5 else '218,54,51'}, "
                                  f"{abs(g - 0.5) * 1.2:.2f})")

    text.columns = [f"GW{g}" for g in text.columns]
    vals.columns = text.columns
    text.insert(0, "Total", vals.sum(axis=1).round(2))
    return text.style.apply(colour, axis=None, subset=list(vals.columns)).format({"Total": "{:.2f}"})


def page_fixtures() -> None:
    st.title("Fixtures")
    st.caption("Attack and defence outlook from our own xG-based team ratings, not the official FDR. "
               "Green = good fixture. Best run of fixtures at the top. Ratings rest on few matches, "
               "so small gaps are noise.")
    ticker = table("ticker")
    a, d = st.tabs(["For attackers: expected goals scored", "For defenders: expected goals conceded"])
    with a:
        st.dataframe(_ticker_grid(ticker, "xg_for", True), width="stretch", height=740)
    with d:
        st.dataframe(_ticker_grid(ticker, "xg_against", False), width="stretch", height=740)
