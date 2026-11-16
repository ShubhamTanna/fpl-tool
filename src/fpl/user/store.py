"""Shubham's own records (drafts, boosts): JSON files in data/user/, which is never committed."""
import io
import json
import zipfile
from pathlib import Path

from ..config import ROOT

USER_DIR = ROOT / "data" / "user"


def load(name: str, default, folder: Path = USER_DIR):
    path = folder / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else default


def save(name: str, data, folder: Path = USER_DIR) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{name}.json.tmp"
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(folder / f"{name}.json")      # write-then-rename: a crash cannot leave half a file


def export_zip(folder: Path = USER_DIR) -> bytes:
    """Every file in data/user/ as one zip, for the backup button."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.glob("*.json")):
            z.write(f, f.name)
    return buf.getvalue()
