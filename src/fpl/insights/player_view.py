"""Tables for the Player page. Plain pandas, no Streamlit, so each can be run and checked alone."""
import pandas as pd

STATS = ["minutes", "starts", "goals_scored", "assists", "expected_goals", "expected_assists",
         "expected_goal_involvements", "defensive_contribution", "bonus", "bps", "total_points"]
NICE = {"gw": "GW", "minutes": "Mins", "starts": "Start", "goals_scored": "G", "assists": "A",
        "expected_goals": "xG", "expected_assists": "xA", "expected_goal_involvements": "xGI",
        "defensive_contribution": "Def. actions", "bonus": "Bonus", "bps": "BPS", "total_points": "Pts",
        "clean_sheets": "CS", "goals_conceded": "GC", "saves": "Saves", "yellow_cards": "YC", "red_cards": "RC"}


def match_log(pid: int, player_gw: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """Every match of his club this season, newest first."""
    short = teams.set_index("team_id").short_name
    h = player_gw[player_gw.player_id == pid].sort_values("kickoff_time", ascending=False)
    out = pd.DataFrame({"GW": h.gw, "Opponent": h.opponent_team_id.map(short) + h.was_home.map({True: " (H)", False: " (A)"}),
                        "Score": h.team_h_score.astype("Int64").astype(str) + "-" + h.team_a_score.astype("Int64").astype(str)})
    for c in STATS:
        out[NICE[c]] = h[c]
    out["Price"] = h.value / 10
    out["Owned by"] = h.selected
    out["Net transfers"] = h.transfers_balance
    return out.reset_index(drop=True)


def season_rates(pid: int, players: pd.DataFrame) -> pd.DataFrame:
    """This season's totals and per-90 rates (raw, not the blended rates the model uses)."""
    p = players.set_index("player_id").loc[pid]
    n90 = p.minutes / 90
    rows = [("Goals", p.goals_scored), ("Assists", p.assists), ("xG", p.expected_goals), ("xA", p.expected_assists),
            ("xGI", p.expected_goal_involvements), ("Defensive actions", p.defensive_contribution),
            ("Saves", p.saves), ("Bonus", p.bonus), ("BPS", p.bps), ("Points", p.total_points)]
    return pd.DataFrame({"Stat": [r[0] for r in rows], "Total": [float(r[1]) for r in rows],
                         "Per 90": [float(r[1]) / n90 if n90 > 0 else float("nan") for r in rows]})


def last_season(pid: int, player_seasons: pd.DataFrame) -> pd.DataFrame:
    """Season totals for every past Premier League season FPL holds, newest first."""
    s = player_seasons[player_seasons.player_id == pid].sort_values("season_name", ascending=False)
    cols = ["season_name", "total_points", "minutes", "starts", "goals_scored", "assists", "expected_goals",
            "expected_assists", "clean_sheets", "defensive_contribution", "bonus", "start_cost", "end_cost"]
    out = s[cols].rename(columns={**NICE, "season_name": "Season", "start_cost": "Start price", "end_cost": "End price"})
    out[["Start price", "End price"]] = out[["Start price", "End price"]] / 10
    return out.reset_index(drop=True)


def projection_rows(pid: int, proj: pd.DataFrame, parts: dict) -> pd.DataFrame:
    """xP for each upcoming gameweek with the inputs behind it."""
    d = proj[proj.player_id == pid].sort_values("gw")
    out = pd.DataFrame({
        "GW": d.gw, "Fixture": d.opp, "Available": d.avail, "Chance of starting": d.p_start_used,
        "xMins": d.xmins, "Fixture multiplier": d.att_mult, "Team xG": d.team_xg, "Opponent xG": d.opp_xg,
        "P(clean sheet)": d.p_cs, "P(def. contribution)": d.p_dc})
    for c, label in parts.items():
        out[label] = d[c]
    out["xP"] = d.xp
    out["Boosted"] = d.boosted.map({True: "yes", False: ""})
    return out.reset_index(drop=True)


def model_rates(pid: int, proj: pd.DataFrame) -> pd.DataFrame:
    """The blended per-90 rates the model uses: this season (recent matches weigh more) mixed with last season."""
    r = proj[proj.player_id == pid].iloc[0]
    rows = [("xG per 90", r.xg_p90), ("xA per 90", r.xa_p90), ("Defensive actions per 90", r.dc_p90),
            ("Saves per 90", r.saves_p90), ("Bonus per 90", r.bonus_p90),
            ("Chance of starting (before injury news and boosts)", r.p_start),
            ("Chance of a substitute appearance", r.p_sub), ("Minutes when starting", r.min_start),
            ("P(60+ minutes | starts)", r.p60)]
    return pd.DataFrame(rows, columns=["Input", "Value"])


def set_pieces(pid: int, players: pd.DataFrame) -> pd.DataFrame:
    p = players.set_index("player_id").loc[pid]
    rows = [("Penalties", p.penalties_order), ("Direct free kicks", p.direct_freekicks_order),
            ("Corners and indirect free kicks", p.corners_and_indirect_freekicks_order)]
    return pd.DataFrame({"Set piece": [r[0] for r in rows],
                         "Order": ["-" if pd.isna(r[1]) else str(int(r[1])) for r in rows]})


def record_vs(pid: int, players: pd.DataFrame, history: pd.DataFrame, opponents: list[str]) -> pd.DataFrame:
    """His past matches against each upcoming opponent, all seasons on file. Display only: not in xP."""
    code = players.set_index("player_id").code[pid]
    short = history[["season", "team_id", "team"]].drop_duplicates().set_index(["season", "team_id"]).team
    h = history[(history.code == code) & (history.minutes > 0)].copy()
    h["opp"] = [short.get((s, t)) for s, t in zip(h.season, h.opponent_team_id)]
    rows = []
    for o in opponents:
        m = h[h.opp == o]
        rows.append({"Opponent": o, "Matches": len(m), "Mins": int(m.minutes.sum()), "G": int(m.goals_scored.sum()),
                     "A": int(m.assists.sum()), "xG": m.expected_goals.sum(), "xA": m.expected_assists.sum(),
                     "Pts": int(m.total_points.sum()),
                     "Pts per match": m.total_points.mean() if len(m) else float("nan"),
                     "Seasons": ", ".join(sorted(m.season.unique()))})
    return pd.DataFrame(rows)


def compare(ids: list[int], players: pd.DataFrame, proj: pd.DataFrame, names: pd.Series, top1k: pd.Series) -> pd.DataFrame:
    """One row per player: price, ownership, season output and xP ahead."""
    p = players.set_index("player_id").loc[ids]
    n90 = (p.minutes / 90).where(p.minutes > 0)
    gws = sorted(proj.gw.unique())
    xp = proj[proj.player_id.isin(ids)].pivot(index="player_id", columns="gw", values="xp").loc[ids]
    first = proj[proj.gw == gws[0]].set_index("player_id").loc[ids]
    return pd.DataFrame({
        "Player": names.reindex(ids).values, "Pos": p.position.values, "Club": p.team.values,
        "Price": (p.now_cost / 10).values, "Owned %": p.selected_by_percent.values,
        "Top 1k %": top1k.reindex(ids).fillna(0).values, "Mins": p.minutes.values, "Starts": p.starts.values,
        "G": p.goals_scored.values, "A": p.assists.values, "Pts": p.total_points.values,
        "xG/90": (p.expected_goals / n90).values, "xA/90": (p.expected_assists / n90).values,
        "Def. actions/90": (p.defensive_contribution / n90).values, "Pts/90": (p.total_points / n90).values,
        "Chance of starting": first.p_start_used.values, f"xP GW{gws[0]}": xp[gws[0]].values,
        f"xP GW{gws[0]}-{gws[min(4, len(gws) - 1)]}": xp[gws[:5]].sum(axis=1).values,
        f"xP GW{gws[0]}-{gws[-1]}": xp.sum(axis=1).values})


PCT_MIN_MINUTES = 270      # players with fewer minutes are left out of the comparison pool
PCT_METRICS = {"xG per 90": "expected_goals", "xA per 90": "expected_assists",
               "xGI per 90": "expected_goal_involvements", "Def. actions per 90": "defensive_contribution",
               "Bonus per 90": "bonus"}


def percentiles(ids: list[int], players: pd.DataFrame, player_gw: pd.DataFrame) -> pd.DataFrame:
    """Where each player ranks among players of his position with PCT_MIN_MINUTES+ minutes.
    100 = best in the position. Minutes share = his minutes / the minutes his club has played."""
    p = players.set_index("player_id")
    club_mins = player_gw.groupby("team_id").fixture_id.nunique() * 90
    stats = pd.DataFrame({k: p[c] / p.minutes * 90 for k, c in PCT_METRICS.items()})
    stats["Minutes share"] = p.minutes / p.team_id.map(club_mins)
    pool = p.minutes >= PCT_MIN_MINUTES
    rows = []
    for i in ids:
        peers = stats[pool & (p.position == p.position[i])]
        for m in stats.columns:
            v = stats.loc[i, m]
            rows.append({"player_id": i, "metric": m, "value": v,
                         "percentile": (float(((peers[m] < v).mean() + (peers[m] == v).mean() / 2) * 100)
                                        if p.minutes[i] > 0 else float("nan")),   # ties share the middle rank
                         "peers": len(peers)})
    return pd.DataFrame(rows)
