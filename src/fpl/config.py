"""Personal settings from the .env file in the project root (never committed)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments are skipped."""
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def team_id() -> int:
    """Shubham's FPL team ID: FPL_TEAM_ID from the environment or .env."""
    value = os.environ.get("FPL_TEAM_ID") or read_env().get("FPL_TEAM_ID")
    if not value:
        raise RuntimeError("FPL_TEAM_ID is not set. Copy .env.example to .env and fill it in.")
    return int(value)
