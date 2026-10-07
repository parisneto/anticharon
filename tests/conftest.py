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


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """The default suite is offline and deterministic (Rule 8): any real HTTP request fails the
    test, so a test that forgets to stub a route cannot silently depend on the network.
    `@pytest.mark.live` tests are the only ones allowed to reach it."""
    if request.node.get_closest_marker("live"):
        return

    def refuse(self, method, url, *args, **kwargs):
        raise AssertionError(f"unmocked network request in an offline test: {method} {url}")

    import requests

    monkeypatch.setattr(requests.sessions.Session, "request", refuse)
