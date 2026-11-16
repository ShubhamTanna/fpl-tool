"""Top-manager template: what the top N overall managers own, start and captain."""
import pandas as pd

from ..ingest.cache import fetch_json
from ..ingest.fpl_api import BASE

OVERALL_LEAGUE = 314
FOREVER = 24 * 365 * 10  # picks for a finished gameweek never change


def top_entries(n: int, gw: int) -> list[int]:
    """Entry ids of the top n managers overall (50 per standings page)."""
    ids, page = [], 1
    while len(ids) < n:
        data = fetch_json(f"top/gw{gw}/standings_p{page}",
                          f"{BASE}leagues-classic/{OVERALL_LEAGUE}/standings/?page_standings={page}",
                          max_age_hours=24)
        # the table moves while pages are fetched, so a manager can show up on two pages
        ids += [r["entry"] for r in data["standings"]["results"] if r["entry"] not in ids]
        if not data["standings"]["has_next"]:
            break
        page += 1
    return ids[:n]


def fetch_picks(entries: list[int], gw: int, log_every: int = 100) -> pd.DataFrame:
    """One row per manager per squad player for gameweek `gw`."""
    rows = []
    for k, e in enumerate(entries, 1):
        data = fetch_json(f"top/gw{gw}/picks_{e}", f"{BASE}entry/{e}/event/{gw}/picks/", FOREVER)
        for p in data["picks"]:
            rows.append({"entry": e, "player_id": p["element"], "multiplier": p["multiplier"],
                         "is_captain": p["is_captain"], "is_vice_captain": p["is_vice_captain"],
                         "chip": data["active_chip"]})
        if k % log_every == 0:
            print(f"  picks {k}/{len(entries)}", flush=True)
    return pd.DataFrame(rows)


def template_table(picks: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Per player, as a share of the scanned managers:
      owned_pct      in the 15-man squad
      start_pct      in the starting XI (multiplier > 0)
      captain_pct    captained
      eo_pct         effective ownership = average multiplier x 100
                     (bench = 0, starter = 1, captain = 2, triple captain = 3)
    A player at 150% EO hurts you by 1.5x his points if you do not own him.
    """
    n = picks.entry.nunique()
    t = picks.groupby("player_id").agg(
        owned_pct=("entry", "size"), start_pct=("multiplier", lambda m: (m > 0).sum()),
        captain_pct=("is_captain", "sum"), vice_pct=("is_vice_captain", "sum"),
        eo_pct=("multiplier", "sum")) * 100 / n
    info = players.set_index("player_id")[["web_name", "position", "team", "now_cost", "selected_by_percent"]]
    out = info.join(t, how="inner").rename(columns={"selected_by_percent": "overall_owned_pct"})
    out["price"] = out.pop("now_cost") / 10
    return out.sort_values("eo_pct", ascending=False).reset_index()
