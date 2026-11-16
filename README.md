# fpl-tool

Personal Fantasy Premier League decision tool: projections, squad optimisation, transfer planning and captaincy from free data.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/check_setup.py
```

## Refresh the data

```bash
python scripts/build_data.py
python scripts/build_projections.py
python scripts/build_insights.py
python scripts/build_template.py
```

## Run the app

```bash
streamlit run app/streamlit_app.py
```

## Backtest and tuning (Step 6)

```
python -c "import sys; sys.path.insert(0,'src'); from fpl.ingest.history import build_history; build_history()"
python scripts/run_trials.py          # every tuning trial, writes data/processed/trial_log.csv
python scripts/backtest.py            # before/after results for every season
python scripts/backtest_threshold.py  # transfer-threshold simulation
```
