"""Section 1: fetch FPL data (cached) and write the clean tables to data/processed/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl.ingest.build import build_all  # noqa: E402

if __name__ == "__main__":
    for name, df in build_all().items():
        print(f"{name:10s} {len(df):>6,} rows x {df.shape[1]} cols")
