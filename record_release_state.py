#!/usr/bin/env python3
"""
Read/write ``.release-state.json`` — the per-package "last published" record
(commit SHA + version) that ``bump_changed_packages.py`` uses to detect
changes relative to what's actually live on PyPI, instead of guessing a git
branch ref.

Usage:
  ./record_release_state.py <folder> <version>            # record HEAD as the publish commit
  ./record_release_state.py <folder> <version> --sha SHA   # record an explicit commit
  ./record_release_state.py --show                         # print current state

Called automatically by ``publish_pypi`` after each successful ``flit publish``.
Use it manually to bootstrap or fix an entry, or to record an out-of-band
publish (e.g. the root ``ialgdev`` meta-package via ``twine``).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / ".release-state.json"


def load_release_state() -> dict[str, dict[str, str]]:
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {STATE_FILE}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {STATE_FILE}, got {type(data).__name__}")
    return data


def write_release_state(state: dict[str, dict[str, str]]) -> None:
    ordered = {key: state[key] for key in sorted(state)}
    STATE_FILE.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def current_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def record(folder: str, version: str, sha: str | None) -> str:
    resolved_sha = sha or current_head()
    state = load_release_state()
    state[folder] = {"sha": resolved_sha, "version": version}
    write_release_state(state)
    return resolved_sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", help="Workspace folder (e.g. vis, algutils)")
    parser.add_argument("version", nargs="?", help="Version just published")
    parser.add_argument("--sha", help="Commit to record (default: current HEAD)")
    parser.add_argument("--show", action="store_true", help="Print current state and exit")
    args = parser.parse_args()

    if args.show:
        print(json.dumps(load_release_state(), indent=2))
        return 0

    if not args.folder or not args.version:
        parser.error("folder and version are required unless --show is given")

    resolved_sha = record(args.folder, args.version, args.sha)
    print(f"Recorded {args.folder} {args.version} @ {resolved_sha[:12]} in {STATE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
