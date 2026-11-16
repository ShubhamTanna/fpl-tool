"""Step 6c/6d: run every tuning trial in order and write the trial log.

Starts from the Step 5 model (BASELINE) and applies the protocol in fpl/backtest/trials.py.
Rerunning reproduces data/processed/trial_log.csv exactly. The dials it ends with are the
defaults in fpl/model/dials.py.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fpl.backtest.harness import HOLDOUT, TUNE, load_history  # noqa: E402
from fpl.backtest.trials import Lab, log_frame, run_trial  # noqa: E402
from fpl.model.dials import Dials  # noqa: E402
from fpl.model.scoring import load_scoring  # noqa: E402

BASELINE = Dials(minutes_half_life=3, rate_half_life=8, prior_90s=5, prev_season_shrink=5, max_p_start=0.95,
                 team_half_life=8, team_prior_matches=3, conceded_ratio=False, dc_matchup=False,
                 dc_dist="poisson", dc_minutes_mix=False, ratio_prev_weight=1.0)

FULL = {"tune": [(s, 2, 38) for s in TUNE], "holdout": [(HOLDOUT, 2, 38)]}
# Defensive contribution only exists from 2025-26, so no tune season has it. Those trials
# are designed on the first half of 2025-26 and accepted on the second half.
DC = {"tune": [(HOLDOUT, 2, 19)], "holdout": [(HOLDOUT, 20, 38)]}

# (dial, candidate values, seasons, part of the score it targets)
TRIALS = [
    ("conceded_ratio", [True], FULL, "cs"),            # fix 1: clean-sheet / goals-conceded bias
    ("ratio_prev_weight", [0.5, 0.25, 0.1], FULL, None),
    ("prior_90s", [2, 3, 8, 12], FULL, None),          # fix 2: flatness
    ("prev_season_shrink", [2, 3, 10, 20], FULL, None),
    ("rate_half_life", [4, 6, 12, 20], FULL, None),
    ("dc_matchup", [True], DC, "dc"),                  # fix 5: defender matchup
    ("dc_dist", ["negbin"], DC, "dc"),                 # fix 6: does Poisson fit?
    ("dc_minutes_mix", [True], DC, "dc"),
    ("dc_matchup", [True], DC, "dc"),                  # matchup again, on top of whatever 6 changed
]


def main() -> Dials:
    lab, log, dials = Lab(load_history(), load_scoring()), [], BASELINE
    for dial, values, spans, part in TRIALS:
        if getattr(dials, dial) in values:
            continue                                   # already accepted earlier
        dials = run_trial(lab, log, dials, dial, values, spans["tune"], spans["holdout"], part)
        print(f"{dial}: now {getattr(dials, dial)}", flush=True)
    df = log_frame(log)
    df.to_csv(ROOT / "data" / "processed" / "trial_log.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    show = ["trial", "dial", "old", "new", "tune_rmse_old", "tune_rmse_new", "tune_part_rmse_old",
            "tune_part_rmse_new", "holdout_rmse_old", "holdout_rmse_new", "holdout_part_rmse_old",
            "holdout_part_rmse_new", "holdout_part_ratio_old", "holdout_part_ratio_new", "decision"]
    print(df[show].round(4).to_string(index=False))
    print("\nFinal dials:", dials)
    return dials


if __name__ == "__main__":
    main()
