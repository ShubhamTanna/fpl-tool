# FPL Tool

Personal Fantasy Premier League tool for one team. Local only.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then set FPL_TEAM_ID
```

## Run the app

From the project root:

```
.venv/bin/streamlit run app/streamlit_app.py
```

Pages: My team, Drafts, Player, Boosts, Scout, Projections, Model lab. The Refresh data button on My team
fetches new FPL data and rebuilds the projections. Drafts and boosts are stored in `data/user/` (not committed);
use the export button on Drafts or Boosts for a backup.

## Rebuild from the command line

```
.venv/bin/python scripts/build_data.py          # FPL data tables
.venv/bin/python scripts/build_projections.py   # projections (no boosts)
.venv/bin/python scripts/build_insights.py      # ticker and underperformer signal
.venv/bin/python scripts/build_template.py      # top-1,000 template, about 17 minutes
.venv/bin/python scripts/plan_team.py --team-id <ID>
```

## Tests

```
.venv/bin/python -m pytest tests
```

## Backtest and tuning (Step 6)

```
python -c "import sys; sys.path.insert(0,'src'); from fpl.ingest.history import build_history; build_history()"
python scripts/run_trials.py          # every tuning trial, writes data/processed/trial_log.csv
python scripts/backtest.py            # before/after results for every season
python scripts/backtest_threshold.py  # transfer-threshold simulation
```
