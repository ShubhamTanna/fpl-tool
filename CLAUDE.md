# FPL Tool - Project Brief

Personal Fantasy Premier League decision tool built by Shubham Tanna.
Goal: better FPL decisions from free data - projections, squad optimization, transfer planning, captaincy, and a few targeted insights.
Started 16 Nov 2026 (season 2026-27, GW10 current at start).

---

## How to work with Shubham (read first)

- **One section at a time.** Build a section, show the result, stop. Do not start the next section until he approves.
- **Be direct.** No yes-man answers. Push back on flawed logic or unrealistic scope. No filler.
- **Never invent numbers.** Every figure shown comes from data or code that ran. Label estimates as estimates.
- **Build only what is asked.** No extra docs, files or features beyond the current section.
- **Explain in plain words.** He is strong in Python and Excel, beginner in SQL. Explain modelling choices briefly so he learns the method.
- **End every substantive explanation** with a short note on which consulting frameworks shaped it (MECE, hypothesis-driven, 80/20, pyramid principle, etc.) and how.
- **Batch tool calls** where possible. Speed matters, but correctness wins.

---

## Scope

### v1 (build now)
1. Data layer
2. Projections (expected points per player per GW)
3. Optimizer (squad builder, transfer planner, XI/bench/captain)
4. Quick insights (top-manager template, xG-underperformer signal, attack/defence fixture ticker)
5. Streamlit app, deployed to Streamlit Community Cloud from the GitHub repo

### v2 (later)
- Chip planner (Wildcard, Free Hit, Bench Boost, Triple Captain; two of each per season, split GW1-19 / GW20-38)
- Odds-calibrated team goal expectations and clean-sheet probabilities
- Flank-matchup signal (see "Shubham's methods")
- Team grade
- Backtest of Shubham's methods on past seasons

### v3 (much later)
- Public multi-user version on shubhamtanna.in

### Cut (do not build)
- AI chat assistant
- Price-change predictor (thresholds are hidden; low value)
- Full BPS simulator (approximate bonus from BPS/bonus history instead)
- FBref data (blocks automated access)

---

## Verified facts (checked 16 Nov 2026 from bootstrap-static)

Read scoring and rules from `game_config` at runtime. Never hardcode them. Values at check time:

- Goals: GKP 10, DEF 6, MID 5, FWD 4. Assist 3.
- Clean sheet: GKP 4, DEF 4, MID 1, FWD 0. Goals conceded: GKP/DEF -1 (per 2).
- Defensive contribution: 2 pts for DEF, MID, FWD (0 for GKP). Thresholds are NOT in game_config. 2025/26 rules were DEF 10 CBIT, MID/FWD 12 CBIRT - confirm current rules before hardcoding.
- Minutes: 60+ = 2, 1-59 = 1. Saves: 1 per 3. Pen save 5, pen miss -2, YC -1, RC -3, OG -2.
- Squad: 15 players, 2 GKP / 5 DEF / 5 MID / 3 FWD, max 3 per club, budget 1000 (= 100.0m).
- XI: 1 GKP, 3-5 DEF, 2-5 MID, 1-3 FWD.
- Free transfers: up to 4 extra can be banked (max 5). Extra transfers cost 4 points each.
- Selling price: `element_sell_at_purchase_price` is False, so the 50% profit rule applies (sell = purchase price + half of the rise, rounded down).
- Chips: wildcard, freehit, bboost, 3xc - one each in GW1-19 and one each in GW20-38.

---

## Data sources (all free)

### FPL API (primary) - `https://fantasy.premierleague.com/api/`
- `bootstrap-static/` - players (109 fields incl. xG, xA, xGI, xGC, defensive_contribution, CBIT, recoveries, tackles, starts, penalty and set-piece order, ownership, transfers), teams, events, game_config
- `fixtures/` - all fixtures with team difficulty
- `element-summary/{player_id}/` - per-match history and upcoming fixtures
- `event/{gw}/live/` - live GW stats
- `entry/{team_id}/` , `entry/{team_id}/history/`, `entry/{team_id}/transfers/`, `entry/{team_id}/event/{gw}/picks/` - Shubham's team
- `leagues-classic/314/standings/?page_standings=N` - overall league, for the top-manager scan

### Understat - `https://understat.com`
- Player/team xG, xA, shot-level data with pitch coordinates (needed for v2 flank signal).
- The old embedded-JSON format did not appear on the league page at check time. Find the current data endpoint before building the loader.

### Historical FPL data - GitHub `vaastav/Fantasy-Premier-League`
- Past seasons per-GW data for model training and backtests. Its 2026-27 data stops around GW6, so never use it for current data.

### Betting odds (v2) - free tiers, need an API key
- SportsGameOdds free Amateur tier or OddsPapi free tier. Match markets (1X2, over/under, BTTS) are enough to derive team goal expectations and clean-sheet probability. Confirm whether goalscorer props are on the free tier.
- Keys go in `.env`. Never commit keys.

### Data etiquette
- Cache every raw response to `data/raw/` with a timestamp. Re-fetch only when stale.
- Rate-limit bulk calls (top-manager scan, element-summary loops) to about 1 request per second.

---

## Repo layout

```
fpl-tool/
  CLAUDE.md
  README.md
  requirements.txt
  .env.example
  .gitignore            # data/raw, .env, .venv, __pycache__
  data/
    raw/                # cached API responses (gitignored)
    processed/          # clean parquet tables
    manual/             # hand-maintained CSVs (e.g. player_side.csv for v2)
  src/fpl/
    ingest/             # fetchers + cache
    model/              # minutes, attack, defence, team ratings, xP
    optimize/           # MILP models + constraint checker
    insights/           # template, signals, tickers
  app/
    streamlit_app.py
  tests/
```

Stack: Python 3.11+, pandas, requests, pyarrow, PuLP (or highspy), streamlit. DuckDB allowed for queries.

---

## Build order (stop for approval after each)

### 0. Setup
venv, requirements, .gitignore, link to Shubham's GitHub repo.
**Check:** one script fetches bootstrap-static and prints current GW and player count.

### 1. Data layer
Fetch + cache + clean. Outputs:
- `players` (one row per player, current snapshot)
- `player_gw` (one row per player per match played, from element-summary history)
- `fixtures` (past and upcoming, with home/away, GW, including doubles and blanks)
- `teams`
- Understat merge: map Understat players to FPL ids. Report match rate and list unmatched players with significant minutes. Do not drop them silently.

**Check:** row counts, no orphan team ids, every upcoming GW has its fixture count (doubles/blanks visible).

### 2. Projections v1 - expected points (xP) per player per GW, next 8 GWs
Break xP into separate parts:
- **Minutes:** P(start) and expected minutes from recent starts/minutes (recency-weighted), injury flags (`chance_of_playing_next_round`, `news`).
- **Team strength:** attack and defence ratings per team from xG for/against, recency-weighted, home/away adjusted. Expected team goals per fixture, then Poisson for clean-sheet and goals-conceded probabilities.
- **Attack:** player xG/90 and xA/90, recency-weighted, shrunk toward a prior (previous season or position average) to handle small samples, times opponent defensive strength.
- **Defensive contribution:** per-90 CBIT/CBIRT distribution, then P(reaching the threshold) per match.
- **GK saves**, **bonus** (bonus per 90 from history), cards (season rate).
- Combine using game_config scoring. Doubles sum both fixtures; blanks = 0.

**Check:** show the top 20 by position for next GW and next 5 GWs. Report correlation of last GW's projections against actual points (report it, don't tune to it).

### 3. Optimizer (MILP)
- **a. Squad builder:** best 15 from scratch over a horizon. Budget, 2/5/5/3, max 3 per club, valid XI, captain double. Small weights for bench.
- **b. Transfer planner:** load Shubham's team by FPL ID. Selling prices via the 50% rule (purchase prices from the transfers endpoint). Horizon 1-5 GWs, banking free transfers (max 5), -4 per extra, future GWs weighted down. The free-transfer count may not be public: derive it by replaying transfer history, or let Shubham enter it.
- **c. Weekly picks:** XI, bench order, captain, vice-captain.
- A separate constraint-checker function validates every output.

**Check:** run on Shubham's real team for the current GW. Show the plan and the xP gain versus making no transfers.

### 4. Quick insights
- **Top-manager template:** picks of the top N overall managers (start with N = 1000). Ownership %, captaincy split, effective ownership.
- **Underperformer signal (the Barry method):** attackers with high xGI/90, actual G+A well below xGI, secure or rising minutes, low ownership. A table to review, not an auto-buy.
- **Fixture ticker:** separate attack and defence difficulty for each team, next 6 GWs, from the team ratings (not the official FDR).

### 5. Streamlit app + deploy
Pages: My Team (transfers + captain), Squad Builder, Projections, Template, Signals, Fixtures.
Deploy on Streamlit Community Cloud from the GitHub repo. Shubham links it from shubhamtanna.in later.

---

## Phase 2 (approved by Shubham, 16 Nov 2026)

Sections 0-5 are built. Phase 2 replaces the remaining v1/v2 plan above where they conflict.

### Direction change
- This is a **personal tool for Shubham's own team only**. No public version, no deploy. Run locally with Streamlit.
- Every screen is about his team: his squad, his drafts, candidates to bring in.
- He wants detail, not abstraction: raw FPL (and later Understat) statistics visible in the interface, with the xP breakdown next to them.
- He will not hand-tune the model dials. Dials change only through the backtest (Step 6).
- His team ID is 108672. It is stored in `.env` as `FPL_TEAM_ID` (not committed) and the app reads it from there. No ID input box.

### Review findings (measured 16 Nov 2026, backtest of GW4-10, 4,672 player-gameweeks)
- Totals are calibrated: 6,206 projected vs 6,394 actual points.
- Clean sheets under-projected: 851 vs 1,066. Defensive contribution under-projected: 400 vs 514. Goals over-projected: 946 vs 864. Assists: 535 vs 495.
- Goalkeepers who start are under-projected: 3.05 vs 3.78 per match.
- Projections are too flat: for GW11 Palmer (9.8m) 3.77, E.Le Fee (5.7m) 4.88. The squad builder starts no midfielder above 6.7m and the planner captains a defender in GW12.
- Edge over a naive baseline is small: correlation among players who played 0.31 vs 0.27 for points-per-game; the model's top 11 averaged 4.55 points vs 4.51.
- The app's Projections caption hardcodes 0.60 / 0.37 (GW10 only). Remove hardcoded results from the UI.
- Injured players with no return date recover 25 points of availability per GW (Saka projected 13.6 xP over GW11-18 while "unknown return date").
- The transfer planner makes a transfer in 4 of 5 weeks for small gains. No lock, ban or transfer cap.
- load_team reads the squad as of the last finished GW; transfers already made for the next GW are not applied.
- No data refresh in the app; st.cache_data never expires. No tests/ folder.

### Step 6 - Backtest harness, projection fixes, defender matchup (BUILD THIS NEXT)

**6a. Historical data.** Load past seasons from GitHub `vaastav/Fantasy-Premier-League` (`data/<season>/gws/merged_gw.csv`). Checked 16 Nov 2026:
- 2023-24, 2024-25 and 2025-26 have per-GW xG and starts for the whole season. 2022-23 has them only from GW16 (corrected 17 Nov 2026): it is used as "last season" for 2023-24, not replayed. 2021-22 and earlier have none: do not use them.
- Only 2025-26 has defensive_contribution. Scoring rules differ by season (defensive-contribution points did not exist before 2025-26): score each season with its own rules, and test the DC part on 2025-26 and 2026-27 only.
- Player ids change every season. Map across seasons with the `code` field, not `id`.

**6b. Harness.** One function replays any past GW: project it using only data from before it, then compare with actual points. Report per season and overall:
- mean absolute error per player
- correlation among players who played
- average actual points of the model's best XI (valid formation, with captain) vs the same from points-per-game
- calibration by component (goals, assists, clean sheets, DC, bonus, saves) and by xP bucket
Save results to data/processed/ so the app can show them.

**6c. Tuning protocol (strict).**
- Tune on 2023-24 and 2024-25. Hold out 2025-26: it is looked at only to accept or reject a change.
- Change one dial at a time. Keep a change only if the hold-out season improves.
- Log every trial (dial, old value, new value, tune result, hold-out result) to a table in the repo.
- Never tune on 2026-27 data. It is the live check.

**6d. Fixes to test through the harness, in this order.**
1. Clean-sheet and goals-conceded bias (check team ratings from player-summed xG vs actual goals conceded; consider a conceded-goals conversion ratio like the one used for goals).
2. Flatness: weight on last season (PRIOR_90S, PREV_SEASON_SHRINK), rate half-life.
3. Goalkeeper under-projection (saves and bonus).
4. Injuries with no return date: replace the +25 per GW timer with something tested or conservative.
5. **Defender matchup (Shubham's signal):** for each club, how many defensive actions opposing DEF/MID/FWD record against it, relative to average. Use it as a fixture multiplier on the DC rate. Keep only if the DC calibration and hold-out error improve.
6. Also test whether Poisson fits the DC count (it may be over-dispersed).

**6e. Optimizer change (Shubham's rule: pick well, roll transfers).** Add a minimum-gain threshold: a transfer is suggested only if it adds more than X xP over the horizon. X is a visible setting, default chosen from the backtest.

**Check for Step 6:** show before/after tables for tune seasons and hold-out, the trial log, and the GW11 top 10 per position before/after. Then stop.

### Step 7 result (built 17 Nov 2026, sections A to H, one commit each)

Run from the project root: `.venv/bin/streamlit run app/streamlit_app.py`. After editing code under `src/` or `app/common.py`, restart the app (page files reload on their own, imported modules do not).

Pages (`app/app_pages/`), shared helpers in `app/common.py`:
- **My team**: loads team 108672 from `.env`, applies transfers already made for the next gameweek, plan with lock / ban / max transfers per gameweek / minimum gain / horizon, refresh-data button, deadline in IST, xP by part for every player, top-1,000 ownership, tickers with his clubs first.
- **Drafts**: unlimited drafts in `data/user/drafts.json` (name, start gameweek, note). Created from a copy of the real team or from the squad builder. Swaps enforce budget, positions and 3-per-club. An edit is stored under the gameweek it takes effect. Comparison with the real team: actual points for played gameweeks, projected points ahead, running difference.
- **Player**: match log, per-90 rates, past seasons, xP by gameweek with its inputs, set pieces, ownership and price trend, record against upcoming opponents (display only), compare mode for 2 to 4 players.
- **Boosts**: output (multiplies goal and assist points) and minutes (replaces chance of starting), in `data/user/boosts.json`. They feed `project(boosts=...)`, so every page uses them; boosted players are marked `[boost]`. Never deleted: cancelling cuts the end gameweek and stamps it. Ended boosts are scored: xP without, xP with, actual.
- **Scout**: xG underperformers, minutes rising, xP per million, fixture swing. Rules and thresholds are printed on the page and live in `src/fpl/insights/signals.py` and `scout.py`. None is backtested.
- **Projections**: the full table with every part.
- **Model lab**: backtest summary, calibration, trial log, dials, threshold backtest. Read-only.

The old Template, Signals, Fixtures and Squad builder pages are gone: ownership is a column, tickers are on My team, signals are in Scout, the squad builder is a way to start a draft.

Method notes:
- The app builds projections live from the data tables (`common.proj`), so boosts apply at once. `projections.parquet` is the no-boost copy the scripts write.
- A past gameweek (draft actuals, boost scoring) is re-projected from the matches before it, without the injury flags of the time, which nobody publishes.
- A draft's actual score is its auto-picked XI with the captain doubled: no automatic substitutions, no chips. The real team's score is FPL's official one minus hits. The two are not like for like.
- Refresh re-fetches prices, news and fixtures every time, and every player's match history (about 12 minutes) only when FPL shows matches the stored data lacks. It does not re-scan the top-1,000 template: run `scripts/build_template.py` (about 17 minutes).
- Tests: `.venv/bin/python -m pytest tests` (team loader, draft rules, boost application).

### Step 7 - original outline (kept for reference)
- My Team: plan with lock / ban / max-transfers / threshold controls; apply transfers already made this GW; refresh-data button; deadline in IST.
- Drafts: unlimited saved draft teams, separate from the real team, each stored with its start GW. Show projected points forward and actual points once played, side by side with the real team.
- Player page: full match-by-match FPL stats, xP breakdown, record vs upcoming opponents (display only), Understat shots when available.
- Scout: each signal as a ranked list of candidates for his team.
- Manual boosts: Shubham enters a multiplier for a player (eye test, new manager). Every boost is logged with date and reason and later scored against actual points.
- Model lab: dials, trial log, backtest results.
- Styling: plain, his site's colours and type through Streamlit theme config.

### Step 8 - Understat signals (blocked: understat.com still offline at 18:30 IST, 16 Nov 2026)
- Zone matchup (left / centre / right), long-shot matchup, team set-piece xG. Each must pass the harness before it enters xP.
- Record vs a specific opponent and reverse fixture: display only unless the harness shows value (expected: none).

### Step 6 result and decisions (17 Nov 2026)

Step 6 is built, approved and pushed (commit e97a49e). Nine trials, two accepted: defensive-action counts use a negative binomial spread (`dc_dist`) and treat a full 90 and an early substitution separately (`dc_minutes_mix`). Overall error is unchanged; defensive-contribution calibration on the hold-out moved from 0.75 to 0.88. The defender-matchup signal failed twice and is off. Full record: `data/processed/trial_log.csv`.

Decisions Shubham has made (do not re-ask):
- Team ID 108672, in `.env`, read by the app.
- Checked against the FPL site on 17 Nov 2026: 2 free transfers and 2.1m bank for GW11 are correct.
- Drafts and boosts live in `data/user/` (gitignored), with an export button for backup.
- Transfer threshold default 2.0 xP, a visible setting. The backtest could not choose it; it is his rule.
- Flatness is closed. Bucket calibration is fine, and Palmer vs Le Fee reflects this season's xGI with identical minutes. Do not investigate the minutes model. Stop tuning dials. Trials 7 and 8 stay.
- The Step 6 judgement calls are accepted: RMSE as the acceptance yardstick, part-specific fixes judged on their own part, defensive-contribution trials tuned on 2025-26 GW2-19 and accepted on GW20-38.
- An injury with no return date holds FPL's chance flat (untested, cautious).
- Section 5 deploy is cancelled. The app is local only.
- Step 7 is built in one run, sections A to H, without stopping for approval between sections.

### Theme (Step 7A)

Taken from shubhamtanna.in on 17 Nov 2026: paper `#e8e7e2`, panel `#dfded8`, ink `#121211`, muted `#5d5b56`, rule `#c7c5bd`, accent red `#ff0000` (accent text `#c8141a`); Playfair Display 900 headings, Newsreader body, JetBrains Mono labels; square corners; tabular figures. Set in `.streamlit/config.toml`, plus four CSS rules in `app/common.py`.

Could not be matched in Streamlit:
- Table headers. The site uses 11px uppercase mono headers and right-aligned ruled rows. Streamlit draws tables on a canvas, which takes colours and the body font from the theme but no header styling.
- The site's 18px body and very large display headings. The app uses 16px and smaller headings to stay data-dense.
- The dark "night" bands and the hero imagery. Not used.
- Fonts load from Google Fonts, so they need an internet connection; offline the app falls back to system serif fonts.

## Shubham's methods (encode as signals, test later)

1. **Form x zone matchup (v2):** an in-form player facing a team that is weak in his zone (e.g. a right winger vs a weak left side). Needs:
   - `data/manual/player_side.csv` - side/zone for the 40-60 realistic picks, tagged by hand
   - team weakness by channel (left/centre/right) from Understat shot coordinates conceded, last 6 matches
   - Caveat: shot location only approximates where an attack came from (a cross from the right often ends in a central shot). State this wherever the signal is shown.
2. **xG underperformer + secure minutes + low ownership (v1):** buy before goals, price and ownership catch up. Example: Thierno Barry (Everton), owned since GW1 of 2026-27.
3. **More methods to come.** Shubham will write them as explicit rules ("buy when X and Y").

He reports doing well above average in FPL. These methods have not been tested on data yet. The v2 backtest compares each method against the official FDR baseline on past seasons. Never claim a method works until that test has run.

---

## Open items
- Transfers already made for the next gameweek: the handling is covered by tests on made-up data only. No pending transfer existed on 17 Nov 2026, so it has not been seen working on the real team. Check it the first time a transfer is made before a deadline.
- The top-1,000 template is from GW10 and is not refreshed by the app's button.
- The Scout rules and the optimizer settings (DECAY, bench weights, FT_VALUE, MIN_GAIN) are judgement calls with no backtest behind them.
- Odds API key (v2)
- Understat merge (Section 1) deferred: understat.com was offline on 16 Nov 2026 ("We will come back soon"). When it is back, find the current data endpoint, build the loader and report the FPL id match rate.
- Defensive-contribution thresholds: DEF 10 CBIT and MID 12 CBIRT confirmed from GW1-10 data (16 Nov 2026). FWD 12 is still an assumption: the data only narrows it to 11-16.
