"""CLI contract tests — enforce the agent-friendly interface guarantees.

These tests run `monitor.py` as a subprocess against a hermetic empty-channel
config so no network is hit. They guard the contract that AI agent callers
depend on (advertised in README "For AI agents"):

  * --help works without a TTY and lists all flags
  * Exit code 0 on graceful skip (no candidates)
  * Final stdout line always starts with "RESULT "
  * Missing env vars fail BEFORE any side effect, with a non-zero exit code
    and a stderr message that names the missing var

If any of these break, downstream agents break — so these tests should fail
loud on regression.
"""
import json
import subprocess
import sys
import textwrap

import pytest

from .conftest import PROJECT_ROOT


MONITOR = str(PROJECT_ROOT / "monitor.py")


def _run(args, env=None, cwd=None):
    # Always use absolute path to monitor.py so cwd can be a temp dir
    # (where config.yaml / channels.yaml fixtures live).
    return subprocess.run(
        [sys.executable, MONITOR, *args],
        capture_output=True,
        text=True,
        cwd=cwd or PROJECT_ROOT,
        env=env,
    )


def _hermetic_env(extra=None):
    """Env with only what's needed; nothing inherited from the test runner."""
    base = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
    if extra:
        base.update(extra)
    return base


@pytest.fixture
def empty_setup(tmp_path):
    """Tiny config + empty channels.yaml + reports dir — no network calls happen."""
    (tmp_path / "config.yaml").write_text(
        textwrap.dedent(
            """
            project:
              name: "Test"
              language: "en"
              repo_fallback: "owner/repo"
            discovery:
              top_n: 1
              fallback_buffer: 0
              shorts_min_duration_sec: 60
            report:
              output_dir: "reports"
            notification:
              channel: "none"
            """
        ).strip(),
        encoding="utf-8",
    )
    (tmp_path / "channels.yaml").write_text("channels: []\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    return tmp_path


def test_help_exits_zero_and_lists_required_flags():
    result = _run(["--help"])
    assert result.returncode == 0
    for flag in ["--config", "--days", "--top", "--no-process", "--no-email", "--channels-limit"]:
        assert flag in result.stdout, f"--help is missing {flag}"


def test_dry_run_with_no_channels_emits_result_line(empty_setup):
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    last_line = result.stdout.strip().splitlines()[-1]
    assert last_line.startswith("RESULT "), f"last line was: {last_line!r}"
    assert "processed=0" in last_line
    assert "succeeded=0" in last_line
    assert "failed=0" in last_line


def test_missing_anthropic_key_aborts_before_processing(empty_setup):
    # Don't pass --no-process, so processing path is requested → key required
    env = _hermetic_env()  # no ANTHROPIC_API_KEY
    result = _run(
        ["--no-email", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode != 0
    assert "ANTHROPIC_API_KEY" in result.stderr


def test_missing_gmail_vars_aborts_when_emailing_via_gmail(empty_setup):
    # Override config to use gmail channel
    (empty_setup / "config.yaml").write_text(
        textwrap.dedent(
            """
            notification:
              channel: "gmail"
            """
        ).strip(),
        encoding="utf-8",
    )
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})  # no GMAIL_*
    result = _run(
        ["--no-process", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode != 0
    assert "GMAIL_USER" in result.stderr


def test_no_email_skips_gmail_validation(empty_setup):
    # gmail channel + --no-email should NOT require GMAIL_* vars
    (empty_setup / "config.yaml").write_text(
        textwrap.dedent(
            """
            notification:
              channel: "gmail"
            """
        ).strip(),
        encoding="utf-8",
    )
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_invalid_config_fails_with_clear_message(empty_setup):
    (empty_setup / "config.yaml").write_text(
        "notification:\n  channel: 'carrier-pigeon'\n", encoding="utf-8"
    )
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode != 0
    assert "notification.channel" in result.stderr


def test_help_lists_output_flag():
    result = _run(["--help"])
    assert "--output" in result.stdout


def test_output_json_emits_parseable_object_on_empty_run(empty_setup):
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email", "--output", "json",
         "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload == {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "report_path": None,
        "report_url": None,
        "videos": [],
    }


def test_output_json_keeps_logs_on_stderr(empty_setup):
    """Stdout must be JSON-only so agents can json.loads(result.stdout) without preprocessing."""
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email", "--output", "json",
         "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    # stderr should contain log lines; stdout should be exclusively JSON
    json.loads(result.stdout)  # no exception = clean
    assert "INFO" in result.stderr or "WARNING" in result.stderr


def test_output_text_default_emits_result_line(empty_setup):
    """Default output mode is unchanged from before --output was added."""
    env = _hermetic_env({"ANTHROPIC_API_KEY": "sk-test"})
    result = _run(
        ["--no-process", "--no-email",
         "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0
    assert result.stdout.strip().startswith("RESULT ")


def test_output_invalid_choice_rejected_by_argparse():
    result = _run(["--output", "xml"])
    assert result.returncode != 0
    assert "invalid choice" in result.stderr.lower() or "--output" in result.stderr


def test_help_lists_dry_run_flag():
    result = _run(["--help"])
    assert "--dry-run" in result.stdout


def test_dry_run_flag_alone_skips_processing_and_email(empty_setup):
    """--dry-run is shorthand for --no-process --no-email — no env vars needed."""
    env = _hermetic_env()  # no ANTHROPIC_API_KEY, no GMAIL_*
    result = _run(
        ["--dry-run", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip().startswith("RESULT ")


def test_dry_run_with_gmail_channel_does_not_require_gmail_vars(empty_setup):
    (empty_setup / "config.yaml").write_text(
        "notification:\n  channel: 'gmail'\n", encoding="utf-8"
    )
    env = _hermetic_env()
    result = _run(
        ["--dry-run", "--config", "config.yaml", "--channels-file", "channels.yaml"],
        env=env,
        cwd=empty_setup,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
