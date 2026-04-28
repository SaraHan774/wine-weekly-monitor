"""Tests for monitor.py — pure helpers (with_retry, format_duration, build_report).

The pipeline (main, process_video) is covered by tests/test_cli_contract.py.
"""
from datetime import datetime, timezone

import pytest

from monitor import build_report, format_duration, with_retry


def test_format_duration_handles_zero():
    assert format_duration(0) == "—"


def test_format_duration_minutes_seconds():
    assert format_duration(125) == "2m 5s"


def test_format_duration_hours_minutes():
    assert format_duration(3700) == "1h 1m"


def test_with_retry_returns_value_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert with_retry(fn, attempts=3) == "ok"
    assert len(calls) == 1


def test_with_retry_succeeds_on_second_attempt():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("transient")
        return "ok"

    assert with_retry(fn, attempts=2, backoff_sec=0.0) == "ok"
    assert len(calls) == 2


def test_with_retry_raises_after_exhausting_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError, match="permanent"):
        with_retry(fn, attempts=3, backoff_sec=0.0)
    assert len(calls) == 3


def test_with_retry_attempts_one_means_no_retry():
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        with_retry(fn, attempts=1, backoff_sec=0.0)
    assert len(calls) == 1


def _entry(**overrides):
    base = {
        "channel_name": "Test Channel",
        "title": "Test Title",
        "url": "https://youtube.com/watch?v=abc",
        "view_count": 1234,
        "published": datetime(2026, 4, 20, tzinfo=timezone.utc),
        "duration": 600,
        "short_summary": "short",
        "long_summary": "long",
        "status": "ok",
        "failed_stage": None,
    }
    base.update(overrides)
    return base


def _cfg():
    return {
        "project": {"name": "Test"},
        "report": {"title_pattern": "{project_name} — {year}-W{week:02d}"},
    }


def test_build_report_includes_title_with_substitutions():
    report = build_report([_entry()], 2026, 17, _cfg())
    assert "# Test — 2026-W17" in report


def test_build_report_lists_each_entry():
    entries = [_entry(title="A"), _entry(title="B")]
    report = build_report(entries, 2026, 17, _cfg())
    assert "1. [Test Channel] A" in report
    assert "2. [Test Channel] B" in report


def test_build_report_marks_failed_entry_with_stage():
    entry = _entry(status="failed", failed_stage="transcribe", short_summary="[처리 실패 (transcribe): boom]")
    report = build_report([entry], 2026, 17, _cfg())
    assert "failed at transcribe" in report
    assert "[처리 실패 (transcribe): boom]" in report


def test_build_report_handles_empty_entries():
    report = build_report([], 2026, 17, _cfg())
    assert "Videos analyzed:** 0" in report


def test_build_report_formats_view_count_with_commas():
    report = build_report([_entry(view_count=12345678)], 2026, 17, _cfg())
    assert "12,345,678" in report
