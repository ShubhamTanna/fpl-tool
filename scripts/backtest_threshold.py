"""Step 6e: choose the default minimum-gain threshold for transfers from the backtest."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.backtest.harness import HOLDOUT, TUNE, load_history, season_data  # noqa: E402
from fpl.backtest.transfers import simulate_season  # noqa: E402
from fpl.model.scoring import load_scoring  # noqa: E402
from fpl.optimize.rules import load_rules  # noqa: E402

THRESHOLDS = [0, 0.5, 1, 1.5, 2, 3, 4, 6, 99]   # 99 = never transfer


def main() -> None:
    hist, scoring, rules = load_history(), load_scoring(), load_rules()
    out = pd.concat([simulate_season(season_data(hist, s, scoring), rules, THRESHOLDS) for s in TUNE + [HOLDOUT]])
    out.to_parquet(ROOT / "data" / "processed" / "backtest_threshold.parquet", index=False)
    g = out.groupby(["threshold", "season"])
    pts = g.points.sum().unstack()
    pts["tune total"] = pts[TUNE].sum(axis=1)
    tr = g.transfers.sum().unstack().add_prefix("transfers ")
    pd.set_option("display.width", 220)
    print("Season points (GW4-38) and transfers made, by threshold")
    print(pd.concat([pts, tr], axis=1).to_string())


if __name__ == "__main__":
    main()
