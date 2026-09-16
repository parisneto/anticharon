"""Shared pytest fixtures for the Anticharon test suite."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_DIR = Path(__file__).parent.parent / "docs" / "sample"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_dir() -> Path:
    return SAMPLE_DIR
