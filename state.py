"""Persistent state for cross-run dedupe and channel health tracking.

State lives in <reports_dir>/.processed.json so it's committed alongside reports.
Schema:
  {
    "video_ids": { "<video_id>": "<YYYY-Www processed>", ... },
    "channel_last_seen": { "<channel_id>": "<YYYY-MM-DD>", ... }
  }

Entries older than EXPIRE_DAYS are pruned on load — keeps the file bounded.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

EXPIRE_DAYS = 90


def _state_path(reports_dir: Path) -> Path:
    return reports_dir / ".processed.json"


def load_state(reports_dir: Path) -> Dict[str, Any]:
    path = _state_path(reports_dir)
    if not path.exists():
        return {"video_ids": {}, "channel_last_seen": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"video_ids": {}, "channel_last_seen": {}}
    data.setdefault("video_ids", {})
    data.setdefault("channel_last_seen", {})
    return _prune_expired(data)


def _prune_expired(data: Dict[str, Any]) -> Dict[str, Any]:
    """Drop video_ids whose processed week is older than EXPIRE_DAYS (UTC)."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=EXPIRE_DAYS)
    fresh: Dict[str, str] = {}
    for vid, week_label in data["video_ids"].items():
        try:
            year_str, week_str = week_label.split("-W")
            iso_dt = datetime.fromisocalendar(int(year_str), int(week_str), 7).date()
        except (ValueError, AttributeError):
            continue
        if iso_dt >= cutoff:
            fresh[vid] = week_label
    data["video_ids"] = fresh
    return data


def save_state(reports_dir: Path, state: Dict[str, Any]) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(reports_dir)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def filter_new(videos: list, state: Dict[str, Any]) -> tuple[list, list]:
    """Split candidates into (new, already_processed) by video_id."""
    new, seen = [], []
    for v in videos:
        if v["video_id"] in state["video_ids"]:
            seen.append(v)
        else:
            new.append(v)
    return new, seen


def mark_processed(state: Dict[str, Any], video_id: str, year: int, week: int) -> None:
    state["video_ids"][video_id] = f"{year}-W{week:02d}"


def update_channel_seen(state: Dict[str, Any], channel_id: str) -> None:
    state["channel_last_seen"][channel_id] = datetime.now(timezone.utc).date().isoformat()
