"""Section 4: fixture ticker and underperformer signal (the template has its own script)."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.insights.signals import underperformers  # noqa: E402
from fpl.insights.ticker import fixture_ticker, ticker_view  # noqa: E402

P = ROOT / "data" / "processed"
pd.set_option("display.width", 220)

if __name__ == "__main__":
    t = {n: pd.read_parquet(P / f"{n}.parquet") for n in ["teams", "players", "fixtures", "events", "player_gw"]}
    nxt = int(t["events"].loc[t["events"].finished, "gw"].max()) + 1
    gws = list(range(nxt, min(nxt + 6, 39)))

    ticker = fixture_ticker(t["player_gw"], t["fixtures"], t["teams"], gws)
    ticker.to_parquet(P / "ticker.parquet", index=False)
    print(f"== Attack ticker GW{gws[0]}-{gws[-1]}: expected goals FOR (higher = better for attackers)")
    print(ticker_view(ticker, "xg_for", best_high=True).to_string())
    print(f"\n== Defence ticker GW{gws[0]}-{gws[-1]}: expected goals AGAINST (lower = better for defenders)")
    print(ticker_view(ticker, "xg_against", best_high=False).to_string())

    sig = underperformers(t["players"], t["player_gw"], flagged_only=False)
    sig.to_parquet(P / "signals.parquet", index=False)
    cols = ["web_name", "position", "team", "price", "minutes", "owned_pct", "xgi_p90", "xgi", "g_a", "gap",
            "starts_last5", "mins_prev3", "mins_last3"]
    print(f"\n== Underperformer signal: {sig.flag.sum()} flagged of {len(sig)} attackers with enough minutes")
    print(sig[sig.flag][cols].round(2).to_string(index=False))
    print("\n== Near misses (3 of 4 tests passed, underperforming by 1.0+)")
    near = sig[(sig.tests_passed == 3) & sig.underperforming]
    print(near[cols + ["high_xgi", "secure_or_rising", "low_owned"]].round(2).to_string(index=False))
