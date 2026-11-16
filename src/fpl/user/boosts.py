"""Manual boosts: Shubham's own adjustments to a player's projection (eye test, new manager).

Two types:
  output   multiplies the player's goal and assist points (1.2 = 20% more)
  minutes  replaces his chance of starting (0.9 = starts 90% of the time)

Every boost is logged with its date and reason and is never deleted: cancelling one cuts its
end gameweek short and stamps it. Once a boost has ended it is scored against actual points.
"""
from datetime import datetime, timezone

TYPES = {"output": (0.1, 3.0), "minutes": (0.0, 1.0)}   # allowed range of `value`


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(boosts: list[dict], player_id: int, web_name: str, kind: str, value: float, start_gw: int,
        end_gw: int, reason: str) -> tuple[list[dict], list[str]]:
    """Returns (boosts, problems). Nothing is added if there are problems."""
    errs = []
    if kind not in TYPES:
        errs.append(f"type must be one of {sorted(TYPES)}")
    elif not TYPES[kind][0] <= value <= TYPES[kind][1]:
        errs.append(f"a {kind} boost must be between {TYPES[kind][0]} and {TYPES[kind][1]}")
    if end_gw < start_gw:
        errs.append("the end gameweek is before the start gameweek")
    if not reason.strip():
        errs.append("a reason is required")
    if any(b["player_id"] == player_id and b["type"] == kind and not b["cancelled_at"]
           and b["start_gw"] <= end_gw and start_gw <= b["end_gw"] for b in boosts):
        errs.append(f"{web_name} already has a {kind} boost covering those gameweeks")
    if errs:
        return boosts, errs
    rec = {"id": 1 + max((b["id"] for b in boosts), default=0), "player_id": int(player_id),
           "web_name": web_name, "type": kind, "value": float(value), "start_gw": int(start_gw),
           "end_gw": int(end_gw), "reason": reason.strip(), "created_at": _now(), "cancelled_at": None}
    return boosts + [rec], []


def cancel(boosts: list[dict], boost_id: int, last_finished_gw: int) -> list[dict]:
    """Stop a boost now. It keeps the gameweeks already played, so it can still be scored."""
    return [{**b, "end_gw": min(b["end_gw"], last_finished_gw), "cancelled_at": _now()}
            if b["id"] == boost_id and not b["cancelled_at"] else b for b in boosts]


def applies(b: dict) -> bool:
    """False for a boost cancelled before it covered any gameweek."""
    return b["end_gw"] >= b["start_gw"]


def for_model(boosts: list[dict]) -> list[dict]:
    """The boosts in the form project() takes."""
    return [b for b in boosts if applies(b)]


def live(boosts: list[dict], next_gw: int) -> list[dict]:
    """Boosts that still affect an upcoming gameweek."""
    return [b for b in boosts if applies(b) and b["end_gw"] >= next_gw]


def ended(boosts: list[dict], last_finished_gw: int) -> list[dict]:
    """Boosts whose every gameweek has been played: ready to score."""
    return [b for b in boosts if applies(b) and b["end_gw"] <= last_finished_gw]
