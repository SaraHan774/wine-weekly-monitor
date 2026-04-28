"""Tests for state.py — cross-run dedupe, prune, save/load round-trip."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from state import (
    EXPIRE_DAYS,
    filter_new,
    load_state,
    mark_processed,
    save_state,
    update_channel_seen,
)


def test_load_state_returns_empty_when_no_file(tmp_path):
    state = load_state(tmp_path)
    assert state == {"video_ids": {}, "channel_last_seen": {}}


def test_load_state_returns_empty_on_corrupt_json(tmp_path):
    (tmp_path / ".processed.json").write_text("{not valid json", encoding="utf-8")
    state = load_state(tmp_path)
    assert state == {"video_ids": {}, "channel_last_seen": {}}


def test_save_then_load_round_trip(tmp_path):
    state = {
        "video_ids": {"abc123": "2026-W17"},
        "channel_last_seen": {"UCfoo": "2026-04-20"},
    }
    save_state(tmp_path, state)
    reloaded = load_state(tmp_path)
    assert reloaded == state


def test_save_state_creates_directory_if_missing(tmp_path):
    nested = tmp_path / "deep" / "nested"
    save_state(nested, {"video_ids": {}, "channel_last_seen": {}})
    assert (nested / ".processed.json").exists()


def test_prune_drops_entries_older_than_expire_days(tmp_path):
    today_utc = datetime.now(timezone.utc).date()
    old_week_iso = (today_utc - timedelta(days=EXPIRE_DAYS + 7)).isocalendar()
    fresh_week_iso = today_utc.isocalendar()
    state = {
        "video_ids": {
            "old_vid": f"{old_week_iso.year}-W{old_week_iso.week:02d}",
            "fresh_vid": f"{fresh_week_iso.year}-W{fresh_week_iso.week:02d}",
        },
        "channel_last_seen": {},
    }
    save_state(tmp_path, state)
    reloaded = load_state(tmp_path)
    assert "old_vid" not in reloaded["video_ids"]
    assert "fresh_vid" in reloaded["video_ids"]


def test_prune_keeps_malformed_week_labels_out(tmp_path):
    state = {"video_ids": {"bad": "not-a-week"}, "channel_last_seen": {}}
    save_state(tmp_path, state)
    reloaded = load_state(tmp_path)
    assert reloaded["video_ids"] == {}


def test_filter_new_separates_seen_and_new():
    state = {"video_ids": {"a": "2026-W17"}, "channel_last_seen": {}}
    videos = [{"video_id": "a"}, {"video_id": "b"}, {"video_id": "c"}]
    new, seen = filter_new(videos, state)
    assert [v["video_id"] for v in new] == ["b", "c"]
    assert [v["video_id"] for v in seen] == ["a"]


def test_filter_new_handles_empty_inputs():
    state = {"video_ids": {}, "channel_last_seen": {}}
    new, seen = filter_new([], state)
    assert new == [] and seen == []


def test_mark_processed_writes_video_id_with_iso_week():
    state = {"video_ids": {}, "channel_last_seen": {}}
    mark_processed(state, "vid42", 2026, 17)
    assert state["video_ids"]["vid42"] == "2026-W17"


def test_mark_processed_pads_single_digit_week():
    state = {"video_ids": {}, "channel_last_seen": {}}
    mark_processed(state, "vid42", 2026, 5)
    assert state["video_ids"]["vid42"] == "2026-W05"


def test_update_channel_seen_records_today_in_utc():
    state = {"video_ids": {}, "channel_last_seen": {}}
    update_channel_seen(state, "UCfoo")
    # state.py records UTC date; comparing to local date.today() is wrong across
    # timezones (e.g. KST runs would flake near midnight UTC).
    today_utc = datetime.now(timezone.utc).date().isoformat()
    assert state["channel_last_seen"]["UCfoo"] == today_utc


def test_load_state_normalizes_missing_keys(tmp_path):
    (tmp_path / ".processed.json").write_text("{}", encoding="utf-8")
    state = load_state(tmp_path)
    assert "video_ids" in state and "channel_last_seen" in state
