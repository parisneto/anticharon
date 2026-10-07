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


@pytest.fixture(autouse=True)
def isolate_host_environment(monkeypatch, tmp_path_factory):
    """The suite must not depend on what is installed on the machine running it (Rule 8): a
    developer's own Hermes CLI/config would otherwise be detected and rewrite test shortlists.
    HOME is a temp dir, HERMES_* / ANTICHARON_* are unset, and `hermes` is not on the path.
    A test that needs any of these sets it itself (explicit patches win over this default)."""
    import shutil

    for name in ("HERMES_CONFIG", "HERMES_HOME", "ANTICHARON_CONFIG", "ANTICHARON_DATA_DIR", "XDG_CONFIG_HOME",
                 "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None if cmd == "hermes" else real_which(cmd, *a, **k))
