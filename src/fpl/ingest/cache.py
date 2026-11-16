"""Fetch JSON with an on-disk cache.

Every raw response is saved to data/raw/<name>_<UTC timestamp>.json.
A cached copy younger than `max_age_hours` is reused instead of re-fetching.
Network calls are spaced at least MIN_INTERVAL seconds apart.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

HEADERS = {"User-Agent": "Mozilla/5.0"}
MIN_INTERVAL = 1.0  # seconds between network requests
STAMP_FMT = "%Y%m%dT%H%M%SZ"

_last_request = 0.0


def _latest(name: str) -> tuple[Path, datetime] | None:
    """Newest cached file for `name` and the time it was fetched."""
    path = RAW_DIR / name
    files = sorted(path.parent.glob(f"{path.name}_*.json"))
    if not files:
        return None
    stamp = files[-1].stem.rsplit("_", 1)[1]
    return files[-1], datetime.strptime(stamp, STAMP_FMT).replace(tzinfo=timezone.utc)


def fetch_json(name: str, url: str, max_age_hours: float = 6.0):
    """Return JSON for `url`, from cache if fresh, else from the network.

    `name` may contain a sub-folder, e.g. "element-summary/123".
    """
    global _last_request
    hit = _latest(name)
    now = datetime.now(timezone.utc)
    if hit and (now - hit[1]).total_seconds() < max_age_hours * 3600:
        return json.loads(hit[0].read_text())

    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    _last_request = time.monotonic()
    resp.raise_for_status()
    data = resp.json()

    path = RAW_DIR / f"{name}_{now.strftime(STAMP_FMT)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    if hit:  # keep only the newest copy of each response
        hit[0].unlink()
    return data
