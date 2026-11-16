"""Tuning protocol: one dial at a time, tuned on past seasons, accepted on the hold-out.

For each trial:
  1. Every candidate value is scored on the tune set. The best one is taken forward.
  2. If the best candidate does not beat the current value on the tune set, stop:
     the hold-out is not looked at.
  3. Otherwise the hold-out is scored once, for that one value. The change is kept only if
     hold-out RMSE falls.

A change aimed at one part of the score (clean sheets, defensive contribution) is judged on
that part alone: RMSE of the part's projected vs actual points, and its projected/actual
ratio must not move further from 1. Judging it on total RMSE would mix in the errors of the
other parts (a part can be fixed and the total still get worse because another part is off).
Total RMSE is logged either way.

RMSE (root mean squared error) is the yardstick, not mean absolute error. xP is meant to be
an average, and the average is what minimises squared error. Absolute error is minimised by
the median, which for FPL points (mostly 0-2, occasionally 10+) sits well below the average,
so chasing it would push every projection down. MAE is still reported.
"""
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

from ..model.dials import Dials
from .harness import run_season, season_data

KEYS = ["rmse", "mae", "corr", "part_rmse", "part_ratio"]
LOG_COLS = (["trial", "dial", "old", "new", "judged_on", "tune_set"]
            + [f"tune_{k}_{v}" for k in KEYS for v in ("old", "new")] + ["holdout_set"]
            + [f"holdout_{k}_{v}" for k in KEYS for v in ("old", "new")] + ["decision"])


class Lab:
    """Runs and remembers season replays, so a (season, dials) pair is computed once."""

    def __init__(self, history: pd.DataFrame, scoring: dict):
        self.history, self.scoring = history, scoring
        self._seasons, self._runs = {}, {}

    def rows(self, dials: Dials, spans: list[tuple[str, int, int]]) -> pd.DataFrame:
        """Replayed player-gameweeks for spans like [("2024-25", 2, 38)]."""
        out = []
        for season, lo, hi in spans:
            if season not in self._seasons:
                self._seasons[season] = season_data(self.history, season, self.scoring)
            key = (season, tuple(asdict(dials).items()))
            if key not in self._runs:
                self._runs[key] = run_season(self._seasons[season], dials)
            r = self._runs[key]
            out.append(r[r.gw.between(lo, hi)])
        return pd.concat(out, ignore_index=True)


def score(rows: pd.DataFrame, part: str | None = None) -> dict:
    err, played = rows.xp - rows.pts, rows[rows.mins > 0]
    out = {"rmse": float(np.sqrt((err ** 2).mean())), "mae": float(err.abs().mean()),
           "corr": float(played.xp.corr(played.pts)), "part_ratio": np.nan, "part_rmse": np.nan}
    if part:
        out["part_rmse"] = float(np.sqrt(((rows[f"xp_{part}"] - rows[f"a_{part}"]) ** 2).mean()))
        out["part_ratio"] = float(rows[f"xp_{part}"].sum() / rows[f"a_{part}"].sum())
    return out


def _span_name(spans) -> str:
    return ", ".join(f"{s} GW{lo}-{hi}" for s, lo, hi in spans)


def run_trial(lab: Lab, log: list[dict], base: Dials, dial: str, candidates: list, tune: list, holdout: list,
              part: str | None = None) -> Dials:
    """Test `candidates` for one dial. Appends one row per candidate to `log`. Returns the dials to keep."""
    old, m = getattr(base, dial), "part_rmse" if part else "rmse"
    t_old = score(lab.rows(base, tune), part)
    tried = {v: score(lab.rows(replace(base, **{dial: v}), tune), part) for v in candidates}
    best = min(tried, key=lambda v: tried[v][m])
    keep, h_old, h_new = base, None, None
    if tried[best][m] < t_old[m]:
        new = replace(base, **{dial: best})
        h_old, h_new = score(lab.rows(base, holdout), part), score(lab.rows(new, holdout), part)
        ok = h_new[m] < h_old[m]
        if part:
            ok = ok and abs(h_new["part_ratio"] - 1) <= abs(h_old["part_ratio"] - 1)
        if ok:
            keep = new
    for v, t_new in tried.items():
        row = {"trial": len({r["trial"] for r in log}) + 1 if v == candidates[0] else log[-1]["trial"],
               "dial": dial, "old": old, "new": v,
               "judged_on": f"{part} points RMSE" if part else "total RMSE", "tune_set": _span_name(tune), "holdout_set": _span_name(holdout)}
        for k in KEYS:
            row[f"tune_{k}_old"], row[f"tune_{k}_new"] = t_old[k], t_new[k]
        if v != best:
            row["decision"] = "not taken forward (another value was better on tune)"
        elif h_new is None:
            row["decision"] = "rejected on tune (hold-out not looked at)"
        else:
            for k in KEYS:
                row[f"holdout_{k}_old"], row[f"holdout_{k}_new"] = h_old[k], h_new[k]
            row["decision"] = "ACCEPTED" if keep is not base else "rejected on hold-out"
        log.append(row)
    return keep


def log_frame(log: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(log).reindex(columns=LOG_COLS)
    df[["old", "new"]] = df[["old", "new"]].astype(str)
    return df
