"""Every tunable number in the projection model, in one place.

Dials change only through the backtest (scripts/run_trials.py): a new value is kept only if
the hold-out season improves. data/processed/trial_log.csv records every trial.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Dials:
    minutes_half_life: float = 3    # matches: minutes change fast, so recent games dominate
    rate_half_life: float = 8       # matches: per-90 output is noisy, so use a longer memory
    prior_90s: float = 5            # this-season rate is blended with a prior worth this many full matches
    prev_season_shrink: float = 5   # last season's rate is itself pulled to the position mean by this many matches
    max_p_start: float = 0.95       # nobody is a certain starter
    team_half_life: float = 8       # matches: memory of the team attack/defence ratings
    team_prior_matches: float = 3   # pull of team ratings toward league average
    # Step 6 candidates. Each is on only if the backtest accepted it (see trial_log.csv).
    conceded_ratio: bool = False    # scale expected goals conceded by actual team goals per xG
    dc_matchup: bool = False        # scale a player's defensive-action rate by his opponent
    dc_dist: str = "negbin"         # spread of the defensive-action count: "poisson" or "negbin"
    dc_minutes_mix: bool = True     # treat a full 90 and an early substitution as separate cases
    ratio_prev_weight: float = 1.0  # weight of last season in the goals/xG, assists/xA, conceded ratios


DIALS = Dials()
