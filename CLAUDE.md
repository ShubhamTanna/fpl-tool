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
- Shubham's FPL team ID
- Odds API key (v2)
- Understat merge (Section 1) deferred: understat.com was offline on 16 Nov 2026 ("We will come back soon"). When it is back, find the current data endpoint, build the loader and report the FPL id match rate.
- Current defensive-contribution thresholds
