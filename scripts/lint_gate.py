#!/usr/bin/env python3
"""Deterministic changed-line lint gate (PE2-010).

Fails only on Ruff findings that are BOTH:
  1. on a line added/modified relative to the merge-base with `main`, AND
  2. not an exact "<rule> <file>:<line>" fingerprint present in the approved
     baseline file (docs/standards/lint_baseline_legacy.txt).

Findings on lines this branch did not touch are pre-existing/out-of-scope
legacy debt (AGENTS.md Rule 13) and never block this gate, regardless of rule
code. This is a per-location fingerprint exemption, not a blanket per-rule-code
exemption: a genuinely new finding of an already-baselined code at a different
file/line still fails.

Usage: uv run python scripts/lint_gate.py [base_ref]
  base_ref defaults to "main".
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
)
BASELINE_FILE = REPO_ROOT / "docs" / "standards" / "lint_baseline_legacy.txt"
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def load_baseline() -> set[str]:
    fingerprints = set()
    for line in BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fingerprints.add(line)
    return fingerprints


def changed_lines(base_ref: str) -> dict[str, set[int]]:
    """Map relative file path -> set of line numbers added/modified since base_ref."""
    diff = subprocess.run(
        ["git", "diff", "-U0", f"{base_ref}...HEAD", "--", "src", "tests"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    result: dict[str, set[int]] = {}
    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/"):]
            result.setdefault(current_file, set())
        elif line.startswith("@@") and current_file is not None:
            m = HUNK_RE.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                continue
            result[current_file].update(range(start, start + count))
    return result


def ruff_findings() -> list[dict]:
    proc = subprocess.run(
        ["uv", "run", "ruff", "check", "src", "tests", "--output-format=json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if not proc.stdout.strip():
        return []
    return json.loads(proc.stdout)


def main() -> int:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "main"
    baseline = load_baseline()
    touched = changed_lines(base_ref)
    findings = ruff_findings()

    new_violations = []
    for finding in findings:
        rel_file = str(Path(finding["filename"]).relative_to(REPO_ROOT))
        row = finding["location"]["row"]
        if row not in touched.get(rel_file, set()):
            continue  # pre-existing, untouched line -- out of scope
        fingerprint = f"{finding['code']} {rel_file}:{row}"
        if fingerprint in baseline:
            continue  # explicitly approved deferral
        new_violations.append(fingerprint)

    if new_violations:
        print("Lint gate FAILED: new finding(s) on changed lines outside the approved baseline:")
        for v in sorted(new_violations):
            print(f"  {v}")
        print("\n--- AUTO-RATCHET INSTRUCTIONS FOR TEST/QA AGENT ---")
        print("If these failures are NOT new violations, but simply legacy findings that have:")
        print("  A) Shifted to a new line number due to structural edits, OR")
        print("  B) Had their total count reduced (organically fixed)")
        print("You are AUTHORIZED by AGENTS.md Rule 13 to Auto-Ratchet (regenerate) the baseline file")
        print("to match the new line numbers and reduced debt count without human sign-off.")
        print("Verify via Git Diff, regenerate the baseline, and re-run this gate.")
        return 1

    print("Lint gate PASSED: no new findings on changed lines outside the approved baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
