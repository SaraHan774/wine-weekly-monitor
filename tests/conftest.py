"""Shared pytest fixtures.

PROJECT_ROOT is added to sys.path so tests can import top-level modules
(monitor, config, state, discovery, notifier) without packaging.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
