"""Section 1 check: row counts, orphan ids, fixtures per gameweek (doubles/blanks)."""
from pathlib import Path

import pandas as pd

P = Path(__file__).resolve().parents[1] / "data" / "processed"
teams, players, fixtures, pgw = (pd.read_parquet(P / f"{n}.parquet")
                                 for n in ["teams", "players", "fixtures", "player_gw"])

print("== Row counts")
for n, df in [("teams", teams), ("players", players), ("fixtures", fixtures), ("player_gw", pgw)]:
    print(f"  {n:10s} {len(df):>6,} rows x {df.shape[1]} cols")
print(f"  player_gw rows with minutes > 0: {(pgw.minutes > 0).sum():,}")
print(f"  players with at least one player_gw row: {pgw.player_id.nunique()} of {len(players)}")

print("\n== Integrity (every count should be 0)")
tid, pid, fid = set(teams.team_id), set(players.player_id), set(fixtures.fixture_id)
checks = {
    "players with unknown team_id": (~players.team_id.isin(tid)).sum(),
    "fixtures with unknown home/away team": (~fixtures.team_h.isin(tid) | ~fixtures.team_a.isin(tid)).sum(),
    "player_gw with unknown player_id": (~pgw.player_id.isin(pid)).sum(),
    "player_gw with unknown fixture_id": (~pgw.fixture_id.isin(fid)).sum(),
    "player_gw with unknown team/opponent": (~pgw.team_id.isin(tid) | ~pgw.opponent_team_id.isin(tid)).sum(),
    "duplicate player_id in players": players.player_id.duplicated().sum(),
    "duplicate (player_id, fixture_id) in player_gw": pgw.duplicated(["player_id", "fixture_id"]).sum(),
    "player_gw rows on unfinished fixtures": (~pgw.fixture_id.map(fixtures.set_index("fixture_id").finished)).sum(),
}
for k, v in checks.items():
    print(f"  {v:>4}  {k}")

print("\n== Cross-check: season totals in players vs sum of player_gw")
agg = pgw.groupby("player_id")[["minutes", "total_points", "goals_scored", "assists"]].sum()
cmp = players.set_index("player_id")[agg.columns].merge(
    agg, how="left", left_index=True, right_index=True, suffixes=("", "_gw")).fillna(0)
for c in agg.columns:
    print(f"  {c:13s} players={cmp[c].sum():>9,.0f}  player_gw={cmp[c + '_gw'].sum():>9,.0f}"
          f"  players that differ={(cmp[c] != cmp[c + '_gw']).sum()}")

print("\n== Fixtures per gameweek")
long = pd.concat([fixtures[["gw", "team_h", "finished"]].rename(columns={"team_h": "team_id"}),
                  fixtures[["gw", "team_a", "finished"]].rename(columns={"team_a": "team_id"})])
short = teams.set_index("team_id").short_name
print(f"  fixtures with no gameweek assigned: {fixtures.gw.isna().sum()}")
per_team = long.dropna(subset=["gw"]).groupby(["gw", "team_id"]).size().unstack(fill_value=0)
per_team = per_team.reindex(columns=teams.team_id, fill_value=0)
by_gw = fixtures.groupby("gw").agg(fixtures=("fixture_id", "size"), finished=("finished", "sum"))
print("   GW  fixtures  finished  doubles / blanks")
for gw, row in by_gw.iterrows():
    dbl = [short[t] for t in per_team.columns if per_team.loc[gw, t] >= 2]
    blk = [short[t] for t in per_team.columns if per_team.loc[gw, t] == 0]
    note = " ".join(filter(None, [f"DOUBLE: {', '.join(dbl)}" if dbl else "",
                                  f"BLANK: {', '.join(blk)}" if blk else ""])) or "-"
    print(f"  {gw:>3}  {row.fixtures:>8}  {row.finished:>8}  {note}")
