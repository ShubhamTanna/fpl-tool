"""Section 4: scan the top N managers' picks.  Usage: python scripts/build_template.py [--n 1000]"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.insights.template import fetch_picks, template_table, top_entries  # noqa: E402

P = ROOT / "data" / "processed"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    a = ap.parse_args()
    players, events = pd.read_parquet(P / "players.parquet"), pd.read_parquet(P / "events.parquet")
    gw = int(events.loc[events.finished, "gw"].max())
    entries = top_entries(a.n, gw)
    picks = fetch_picks(entries, gw)
    picks.to_parquet(P / "top_picks.parquet", index=False)
    table = template_table(picks, players)
    table.to_parquet(P / "template.parquet", index=False)
    print(f"Top {picks.entry.nunique()} managers, GW{gw}: {len(table)} different players owned")
    print("Chips active:", picks.drop_duplicates("entry").chip.fillna("none").value_counts().to_dict())
    cols = ["web_name", "position", "team", "price", "owned_pct", "start_pct", "captain_pct", "eo_pct", "overall_owned_pct"]
    print(table[cols].head(30).round(1).to_string(index=False))
