"""Rebuild everything the app reads: data tables, projections, ticker, signals, history."""
import pandas as pd

from .ingest import fpl_api
from .ingest.build import build_all, build_fixtures
from .ingest.cache import PROCESSED_DIR
from .ingest.history import build_history
from .insights.signals import underperformers
from .insights.ticker import fixture_ticker
from .model.xp import project

TABLES = ["teams", "players", "fixtures", "events", "player_gw", "player_seasons"]
FOREVER = 24 * 365 * 10
TICKER_GWS = 6


def load_tables() -> dict[str, pd.DataFrame]:
    return {n: pd.read_parquet(PROCESSED_DIR / f"{n}.parquet") for n in TABLES}


def new_matches_played() -> bool:
    """True if FPL shows finished fixtures that data/processed/player_gw does not have yet."""
    fx = build_fixtures(fpl_api.fixtures(0))
    done = set(fx.loc[fx.finished, "fixture_id"])
    have = set(pd.read_parquet(PROCESSED_DIR / "player_gw.parquet", columns=["fixture_id"]).fixture_id)
    return not done <= have


def rebuild_derived(tables: dict | None = None) -> dict:
    """Projections, fixture ticker, underperformer signal and the all-seasons history table."""
    t = tables or load_tables()
    proj, _ = project(t)
    proj.to_parquet(PROCESSED_DIR / "projections.parquet", index=False)
    gws = sorted(proj.gw.unique())[:TICKER_GWS]
    fixture_ticker(t["player_gw"], t["fixtures"], t["teams"], gws).to_parquet(PROCESSED_DIR / "ticker.parquet", index=False)
    underperformers(t["players"], t["player_gw"], flagged_only=False).to_parquet(
        PROCESSED_DIR / "signals.parquet", index=False)
    build_history()
    return {"players": len(t["players"]), "matches": int(t["player_gw"].fixture_id.nunique()),
            "next_gw": int(gws[0])}


def refresh(progress=None) -> dict:
    """Fetch fresh FPL data and rebuild everything.

    Prices, injury news and fixtures are always re-fetched (two requests). Player match
    histories (one request per player, about a second each) are re-fetched only when FPL shows
    matches that the stored data lacks; otherwise the cached copies are reused.
    The top-1,000 template is not refreshed here: run scripts/build_template.py (about 17 minutes).
    """
    full = new_matches_played()
    tables = build_all(max_age_hours=0, history_max_age_hours=0 if full else FOREVER, progress=progress)
    return {**rebuild_derived(tables), "full_history": full}
