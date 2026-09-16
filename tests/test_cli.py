"""Tests for anticharon.cli: help subcommand routing (unaffected by the
pricing-engine-v2 rework)."""

import argparse
import io
from contextlib import redirect_stderr, redirect_stdout

from anticharon.cli import cmd_help


def _build_parsers():
    parser = argparse.ArgumentParser(prog="anticharon")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run help")
    model_p = subparsers.add_parser("model", help="Model help")
    model_subparsers = model_p.add_subparsers(dest="model_action")
    model_subparsers.add_parser("discover", help="Discover help")
    return parser, subparsers, model_subparsers


def test_help_top_level():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=[]))
    assert code == 0
    assert "anticharon" in f.getvalue()


def test_help_subcommand():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["run"]))
    assert code == 0
    assert "run" in f.getvalue()


def test_help_nested_subcommand():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["model", "discover"]))
    assert code == 0
    assert "discover" in f.getvalue()


def test_help_unknown_target():
    parser, subparsers, model_subparsers = _build_parsers()
    f_err = io.StringIO()
    with redirect_stderr(f_err):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["unknown"]))
    assert code == 2
    assert "unknown help target 'unknown'" in f_err.getvalue()
