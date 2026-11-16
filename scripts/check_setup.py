"""Section 0 check: fetch bootstrap-static, cache it, print current GW and player count."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> None:
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Cache the raw response with a UTC timestamp (data/raw is gitignored).
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"bootstrap-static_{stamp}.json"
    path.write_text(json.dumps(data))

    current = [e for e in data["events"] if e["is_current"]]
    nxt = [e for e in data["events"] if e["is_next"]]
    print(f"Current GW: {current[0]['id'] if current else 'none (pre-season)'}")
    print(f"Next GW:    {nxt[0]['id'] if nxt else 'none'}"
          + (f" (deadline {nxt[0]['deadline_time']})" if nxt else ""))
    print(f"Players:    {len(data['elements'])}")
    print(f"Teams:      {len(data['teams'])}")
    print(f"Cached to:  {path.relative_to(RAW_DIR.parents[1])}")


if __name__ == "__main__":
    main()
