"""AC-7 / D-7: one help contract for every primary and nested command.

Supported: `<command> [subcommand] -h|--help` and `help <command> [subcommand]`.
Not supported (exit 2 with a hint): `<command> help`, `model help [<sub>]`.
"""

import pytest

from anticharon import cli
from anticharon.cli import build_parser, cmd_help, misplaced_help_hint

PATHS = [
    ("run",), ("check",), ("history",), ("info",), ("mcp",), ("test",), ("calibrate",), ("check-updates",),
    ("update",), ("prompt",), ("help",), ("model",), ("model", "import-hermes"), ("model", "sync"),
    ("model", "add"), ("model", "remove"), ("model", "list"), ("model", "discover"),
]


def _usage(path):
    # `model sync` is an alias of `model import-hermes` and shows its usage.
    path = ("model", "import-hermes") if path == ("model", "sync") else path
    return "usage: anticharon " + " ".join(path)


def test_every_command_is_covered_by_the_help_contract():
    _, subparsers, model_subparsers = build_parser()
    expected = {(name,) for name in subparsers.choices} | {("model", n) for n in model_subparsers.choices}
    assert expected == set(PATHS)


@pytest.mark.parametrize("path", PATHS, ids=" ".join)
@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_flag_help_exits_zero_with_command_specific_usage(path, flag, capsys):
    parser, _, _ = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([*path, flag])
    assert exc.value.code == 0
    assert _usage(path) in capsys.readouterr().out


@pytest.mark.parametrize("path", PATHS, ids=" ".join)
def test_help_subcommand_exits_zero_with_the_same_usage(path, capsys):
    parser, subparsers, model_subparsers = build_parser()
    args = parser.parse_args(["help", *path])
    assert cmd_help(parser, subparsers, model_subparsers, args) == 0
    assert _usage(path) in capsys.readouterr().out


@pytest.mark.parametrize("target", [["foo"], ["model", "foo"], ["run", "extra"], ["model", "add", "extra"]])
def test_invalid_help_targets_fail_clearly(target, capsys):
    parser, subparsers, model_subparsers = build_parser()
    args = parser.parse_args(["help", *target])
    assert cmd_help(parser, subparsers, model_subparsers, args) == 2
    err = capsys.readouterr().err
    assert "unknown help target" in err and "anticharon help" in err


@pytest.mark.parametrize("argv,hint", [
    (["run", "help"], "help run"),
    (["check", "help"], "help check"),
    (["model", "help"], "help model"),
    (["model", "help", "add"], "help model add"),
    (["model", "add", "help"], "help model add"),
    (["--json", "history", "help"], "help history"),
])
def test_misplaced_help_forms_are_rejected_with_a_hint(argv, hint, monkeypatch, capsys):
    assert misplaced_help_hint(argv) == hint
    monkeypatch.setattr("sys.argv", ["anticharon", *argv])
    monkeypatch.setattr("anticharon.manager.add_model",
                        lambda *a, **k: pytest.fail("`model add help` must never be treated as a slug"))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"anticharon {hint}" in err and " -h" in err


@pytest.mark.parametrize("argv", [
    ["model", "discover", "help"], ["help", "run"], ["run", "--dry-run"], ["model", "add", "a/b"],
    ["prompt", "daily_cost_briefing"], ["calibrate", "help"], [],
])
def test_valid_forms_are_not_mistaken_for_misplaced_help(argv):
    assert misplaced_help_hint(argv) is None
