#!/usr/bin/env python3
"""supplemental_version_inventory.py

Generate a version‑string inventory for Anticharon user‑facing files.

The script scans the repository for version patterns (`vX.Y.Z` or `X.Y.Z`) and
classifies each match into one of four categories:

* **canonical** – the current package version (taken from `src/anticharon/__init__.py`
  or `pyproject.toml`).
* **historical** – version strings that appear as Git tags (retrieved via `git tag`).
* **third‑party** – versions that belong to dependencies (found in lock files such as
  `uv.lock`).
* **removable** – any other version occurrences that are not covered by the
  three categories; these are candidates for cleanup.

The output is a Markdown report saved as
`docs/plans/ecosystem-ergonomics/version_inventory_report.md`.
"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict
import json, argparse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RE_VERSION = re.compile(r"\bv?\d+\.\d+\.\d+\b")
# Files that are considered user‑facing. Adjust as needed.
USER_FACING_EXTS = {".md", ".txt"}
PYTHON_EXT = ".py"
LOCK_FILES = {"uv.lock", "poetry.lock", "requirements.txt"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # two levels up from this script

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def get_canonical_version() -> str:
    """Return the current package version.

    Preference order:
    1. src/anticharon/__init__.py -> __version__
    2. pyproject.toml -> version field
    """
    init_path = PROJECT_ROOT / "src" / "anticharon" / "__init__.py"
    if init_path.exists():
        content = init_path.read_text()
        m = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        if m:
            return m.group(1)
    # fallback to pyproject.toml
    pyproj = PROJECT_ROOT / "pyproject.toml"
    if pyproj.exists():
        for line in pyproj.read_text().splitlines():
            if line.strip().startswith("version"):
                # e.g. version = "0.5.5"
                m = re.search(r'"([^"]+)"', line)
                if m:
                    return m.group(1)
    return ""

def get_git_tags() -> set:
    """Return a set of version tags from the repository (e.g., v0.5.5)."""
    try:
        result = subprocess.run(["git", "tag"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        tags = {tag.strip() for tag in result.stdout.splitlines() if tag.strip()}
        # Keep only tags that look like versions
        return {t.lstrip('v') for t in tags if RE_VERSION.search(t)}
    except Exception:
        return set()

def is_third_party(file_path: Path) -> bool:
    return file_path.name in LOCK_FILES

def scan_file(file_path: Path) -> list:
    """Return a list of version strings found in *file_path*.
    For Python files we also inspect docstrings via the AST.
    """
    matches = []
    if file_path.suffix == PYTHON_EXT:
        # Scan the whole source for version patterns – this catches docstrings and
        # any literal strings in code.
        text = file_path.read_text(errors="ignore")
        matches.extend(RE_VERSION.findall(text))
    else:
        text = file_path.read_text(errors="ignore")
        matches.extend(RE_VERSION.findall(text))
    return matches

def classify(version: str, canonical: str, historical: set, third_party_files: set) -> str:
    if version == canonical or version == f"v{canonical}":
        return "canonical"
    if version.lstrip('v') in historical:
        return "historical"
    if version in third_party_files:
        return "third‑party"
    return "removable"

# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def main():
    canonical = get_canonical_version()
    historical = get_git_tags()
    third_party_versions = set()
    # Collect all third‑party version strings from lock files first
    for lock_name in LOCK_FILES:
        lock_path = PROJECT_ROOT / lock_name
        if lock_path.is_file():
            third_party_versions.update(RE_VERSION.findall(lock_path.read_text(errors="ignore")))

    inventory = defaultdict(lambda: defaultdict(int))  # file -> version -> count
    classification = {}

    # Walk the repo and inspect user‑facing files plus Python sources.
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix in USER_FACING_EXTS or path.suffix == PYTHON_EXT:
            versions = scan_file(path)
            if not versions:
                continue
            for v in versions:
                inventory[str(path.relative_to(PROJECT_ROOT))][v] += 1
                # Determine classification once (shared for same version)
                if v not in classification:
                    classification[v] = classify(
                        v,
                        canonical,
                        historical,
                        third_party_versions,
                    )

    # Build markdown report
    report_lines = []
    report_lines.append("# Version‑String Inventory Report")
    report_lines.append("")
    report_lines.append(f"**Canonical version:** `{canonical}`")
    report_lines.append("")
    report_lines.append("| File | Version | Count | Classification |")
    report_lines.append("|------|---------|-------|----------------|")
    for file, versions in sorted(inventory.items()):
        for ver, cnt in sorted(versions.items()):
            cls = classification.get(ver, "removable")
            report_lines.append(f"| `{file}` | `{ver}` | {cnt} | {cls} |")
    report = "\n".join(report_lines)

    # Argument handling: by default print, optionally save
    parser = argparse.ArgumentParser(description="Generate version-string inventory.")
    parser.add_argument(
        "--save",
        action="store_true",
        default=False,
        help="Save the report to a markdown file instead of printing.",
    )
    args = parser.parse_args()

    if args.save:
        output_path = PROJECT_ROOT / "docs" / "plans" / "ecosystem-ergonomics" / "version_inventory_report.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Report written to {output_path}")
    else:
        print(report)

if __name__ == "__main__":
    main()
