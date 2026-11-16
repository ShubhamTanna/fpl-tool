"""FPL Tool - Streamlit app. Run with: streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.ingest.team import load_team  # noqa: E402
from fpl.insights import signals as sig_rules  # noqa: E402
from fpl.optimize.checker import check_lineup, check_plan, check_squad  # noqa: E402
from fpl.optimize.models import MIN_GAIN, build_squad, plan_transfers  # noqa: E402
from fpl.optimize.rules import load_rules  # noqa: E402

P = ROOT / "data" / "processed"
PARTS = {"xp_app": "Appearance", "xp_goals": "Goals", "xp_assists": "Assists", "xp_cs": "Clean sheet",
         "xp_conceded": "Conceded", "xp_saves": "Saves", "xp_dc": "Def. contribution",
         "xp_bonus": "Bonus", "xp_cards": "Cards"}
POSITIONS = ["GKP", "DEF", "MID", "FWD"]

st.set_page_config(page_title="FPL Tool", page_icon=":soccer:", layout="wide")


@st.cache_data
def table(name: str) -> pd.DataFrame:
    return pd.read_parquet(P / f"{name}.parquet")


@st.cache_resource
def rules():
    return load_rules()


def gameweeks() -> list[int]:
    return sorted(int(g) for g in table("projections").gw.unique())


def xp_grid(gws: list[int]) -> pd.DataFrame:
    proj = table("projections")
    return proj[proj.gw.isin(gws)].pivot(index="player_id", columns="gw", values="xp")


def player_rows(ids: list[int], gws: list[int], extra: dict | None = None) -> pd.DataFrame:
    """Display table for a list of players: name, position, club, price and xP per gameweek."""
    p, xp = table("players").set_index("player_id"), xp_grid(gws)
    df = pd.DataFrame({"Player": p.web_name[ids].values, "Pos": p.position[ids].values,
                       "Club": p.team[ids].values, "Price": (p.now_cost[ids] / 10).values})
    for k, v in (extra or {}).items():
        df[k] = v
    for g in gws:
        df[f"GW{g}"] = xp.loc[ids, g].round(2).values
    return df


def show(df: pd.DataFrame, **kw) -> None:
    st.dataframe(df, hide_index=True, width="stretch", **kw)


@st.cache_data(show_spinner=False)
def run_plan(team_id: int, horizon: int, ft_override: int | None, min_gain: float):
    r, players, proj = rules(), table("players"), table("projections")
    gws = gameweeks()[:horizon]
    team = load_team(team_id, players, table("player_gw"), gws[0] - 1, r.sell_fee, r.max_free_transfers)
    derived_ft = team["free_transfers"]
    if ft_override:
        team["free_transfers"] = ft_override
    plan = plan_transfers(team, proj, players, r, gws, min_gain=min_gain)
    hold = plan_transfers(team, proj, players, r, gws, allow_transfers=False)
    errs = check_plan(plan, team, players, r) + check_plan(hold, team, players, r)
    return team, derived_ft, plan, hold, errs


@st.cache_data(show_spinner=False)
def run_squad(horizon: int, budget: int):
    r, players = rules(), table("players")
    gws = gameweeks()[:horizon]
    res = build_squad(table("projections"), players, r, gws, budget=budget)
    errs = check_squad(res["squad"], players, r)
    for g in res["gws"]:
        errs += check_lineup(g["xi"], g["bench"], g["captain"], g["vice"], g["squad"], players, r)
    return res, errs


# ---------------------------------------------------------------- pages

def page_my_team() -> None:
    st.title("My Team")
    st.caption("Transfer plan, starting XI and captain for your team, from the xP projections.")
    c1, c2, c3, c4 = st.columns(4)
    team_id = c1.number_input("FPL team ID", min_value=1, value=None, step=1, format="%d",
                              help="The number in the URL of your Points page: /entry/<ID>/event/10")
    horizon = c2.slider("Gameweeks to plan", 1, 5, 5)
    ft_choice = c3.selectbox("Free transfers", ["Work it out", 1, 2, 3, 4, 5],
                             help="FPL does not publish this. 'Work it out' replays your season.")
    min_gain = c4.number_input("Minimum gain per transfer (xP)", 0.0, 10.0, MIN_GAIN, 0.5,
                               help="A transfer is suggested only if it adds more than this many xP over "
                                    "the gameweeks planned. Higher = roll transfers more often.")
    if not team_id:
        st.info("Enter your FPL team ID to build a plan.")
        return
    try:
        with st.spinner("Loading your team and solving (about 15 seconds)..."):
            team, derived_ft, plan, hold, errs = run_plan(int(team_id), horizon,
                                                          None if ft_choice == "Work it out" else ft_choice,
                                                          min_gain)
    except Exception as e:  # bad id, FPL API down, or no feasible plan
        st.error(f"Could not build a plan for team {team_id}: {e}")
        return

    r, p = rules(), table("players").set_index("player_id")
    gws = [g["gw"] for g in plan["gws"]]
    gain = plan["xp_net"] - hold["xp_net"]
    st.subheader(team["name"])
    m = st.columns(4)
    m[0].metric("Bank", f"{team['bank'] / 10:.1f}m")
    m[1].metric("Free transfers", team["free_transfers"],
                help=f"Replaying your season gives {derived_ft}. Check it against the FPL site.")
    m[2].metric(f"Plan xP, GW{gws[0]}-{gws[-1]}", f"{plan['xp_net']:.1f}", f"{gain:+.1f} vs no transfers")
    m[3].metric("Rule check", "Pass" if not errs else "FAIL")
    if errs:
        st.error("The plan broke a rule: " + "; ".join(errs))
    st.caption("The gain is measured against the same projections that chose the transfers, so read it as "
               "an upper estimate. Each move is often worth 1-2 xP a week, which is inside the projection error.")

    for tab, g, h in zip(st.tabs([f"GW{g}" for g in gws]), plan["gws"], hold["gws"]):
        with tab:
            a, b, c = st.columns(3)
            a.metric("xP after hits", f"{g['xp_net']:.1f}", f"{g['xp_net'] - h['xp_net']:+.1f} vs no transfers")
            b.metric("Free transfers / hits", f"{g['free_transfers']} / {g['hits']}",
                     f"-{g['hits'] * r.hit_cost} pts" if g["hits"] else None, delta_color="inverse")
            c.metric("Bank after", f"{g['bank'] / 10:.1f}m")
            if g["transfers_in"]:
                outs = sorted(g["transfers_out"], key=lambda i: p.position[i])
                ins = sorted(g["transfers_in"], key=lambda i: p.position[i])
                xp = xp_grid([g["gw"]])[g["gw"]]
                show(pd.DataFrame({
                    "Out": [f"{p.web_name[i]} ({p.team[i]})" for i in outs],
                    "Out xP": [round(xp[i], 2) for i in outs],
                    "In": [f"{p.web_name[i]} ({p.team[i]})" for i in ins],
                    "In price": [p.now_cost[i] / 10 for i in ins],
                    "In xP": [round(xp[i], 2) for i in ins]}))
            else:
                st.write("No transfers this week: roll the free transfer.")
            role = {g["captain"]: "Captain", g["vice"]: "Vice"}
            ids = g["xi"] + g["bench"]
            show(player_rows(ids, [g["gw"]], {
                "Slot": ["XI"] * len(g["xi"]) + [f"Bench {k}" for k in range(1, len(g["bench"]) + 1)],
                "Role": [role.get(i, "") for i in ids]}))

    with st.expander("Current squad and selling prices"):
        ids = team["squad"]
        show(player_rows(ids, gws[:1], {
            "Bought": [team["purchase_price"][i] / 10 for i in ids],
            "Sell": [team["sell_price"][i] / 10 for i in ids],
            "Status": [p.status[i] for i in ids]}))
        st.caption("Selling prices are estimates from the 50% rule: purchase price plus half of any rise, rounded down.")


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
    proj, gws = table("projections"), gameweeks()
    c1, c2, c3, c4 = st.columns(4)
    lo, hi = c1.select_slider("Gameweeks", gws, (gws[0], gws[0]))
    pos = c2.multiselect("Position", POSITIONS, POSITIONS)
    clubs = c3.multiselect("Club", sorted(proj.team.unique()))
    max_price = c4.number_input("Max price (m)", 3.5, 20.0, 20.0, 0.5)
    d = proj[proj.gw.between(lo, hi) & proj.position.isin(pos) & (proj.now_cost <= max_price * 10)]
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
               "defender's goal threat, and team ratings rest on few matches. In a backtest on GW10 the "
               "correlation with actual points was 0.60 across all players and 0.37 among those who played.")


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


pages = [st.Page(page_my_team, title="My Team", icon=":material/person:", default=True),
         st.Page(page_squad_builder, title="Squad Builder", icon=":material/construction:"),
         st.Page(page_projections, title="Projections", icon=":material/trending_up:"),
         st.Page(page_template, title="Template", icon=":material/groups:"),
         st.Page(page_signals, title="Signals", icon=":material/notifications:"),
         st.Page(page_fixtures, title="Fixtures", icon=":material/calendar_month:")]
nav = st.navigation(pages)
ev = table("events")
nxt = ev[~ev.finished].iloc[0]
st.sidebar.caption(f"Next: GW{int(nxt.gw)}, deadline {nxt.deadline_time:%a %d %b %H:%M} UTC")
nav.run()
