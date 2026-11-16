"""Step 6b: replay every season with the Step 5 model ("before") and the current dials ("after").

Writes data/processed/backtest_summary.parquet, backtest_components.parquet and
backtest_buckets.parquet so the app can show them.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fpl.backtest.harness import HOLDOUT, LIVE, TUNE, buckets, components, load_history, summarise  # noqa: E402
from fpl.backtest.trials import Lab  # noqa: E402
from fpl.model.dials import DIALS  # noqa: E402
from fpl.model.scoring import load_scoring  # noqa: E402
from run_trials import BASELINE  # noqa: E402

P = ROOT / "data" / "processed"
ROLE = {**{s: "tune" for s in TUNE}, HOLDOUT: "hold-out", LIVE: "live"}


def main() -> None:
    lab = Lab(load_history(), load_scoring())
    summ, comp, buck = [], [], []
    for model, dials in [("before", BASELINE), ("after", DIALS)]:
        runs = {s: lab.rows(dials, [(s, 2, 38)]) for s in ROLE}
        runs["all past seasons"] = pd.concat([runs[s] for s in TUNE + [HOLDOUT]])
        for season, rows in runs.items():
            tag = {"model": model, "season": season, "role": ROLE.get(season, "tune + hold-out")}
            summ.append({**tag, **summarise(rows)})
            comp.append(components(rows).assign(**tag))
            buck.append(buckets(rows).assign(**tag))
    summ, comp, buck = pd.DataFrame(summ), pd.concat(comp), pd.concat(buck)
    buck["xp_bucket"] = buck.xp_bucket.astype(str)
    summ.to_parquet(P / "backtest_summary.parquet", index=False)
    comp.to_parquet(P / "backtest_components.parquet", index=False)
    buck.to_parquet(P / "backtest_buckets.parquet", index=False)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("== Summary (xi = average actual points of the best XI incl. captain, per gameweek)")
    cols = ["season", "role", "model", "player_gws", "proj_pts", "actual_pts", "mae", "rmse", "mae_played",
            "corr_played", "corr_played_ppg", "xi_model", "xi_ppg"]
    print(summ.sort_values(["season", "model"], ascending=[True, False])[cols].round(3).to_string(index=False))
    print("\n== Projected / actual points by part of the score")
    print(comp.pivot_table(index=["season", "model"], columns="part", values="ratio", sort=False).round(2).to_string())
    print("\n== Points by part, all past seasons")
    c = comp[comp.season == "all past seasons"].pivot(index="part", columns="model", values="projected")
    c["actual"] = comp[(comp.season == "all past seasons") & (comp.model == "after")].set_index("part").actual
    print(c[["before", "after", "actual"]].round(0).to_string())
    print("\n== By xP bucket, all past seasons")
    b = buck[buck.season == "all past seasons"]
    print(b.pivot(index="xp_bucket", columns="model", values=["player_gws", "mean_xp", "mean_actual"])
          .reindex(["<1", "1-2", "2-3", "3-4", "4-5", "5-6", "6+"]).round(2).to_string())


if __name__ == "__main__":
    main()
