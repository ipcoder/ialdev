#!/usr/bin/env python3
"""
Sync ialdev-* dependency pins across workspace pyproject.toml files.

After bumping ``version`` in one or more sub-package ``pyproject.toml`` files, run
this script so every dependent project pins the new releases (``name>=X.Y.Z``).

Usage:
  ./sync_workspace_deps.py              # sync all workspace packages
  ./sync_workspace_deps.py algutils maths   # only refresh pins for those distributions
  ./sync_workspace_deps.py --dry-run
  ./sync_workspace_deps.py --check        # exit 1 if anything would change
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from packaging.specifiers import SpecifierSet
except ImportError:  # pragma: no cover - packaging is normally available
    SpecifierSet = None

ROOT = Path(__file__).resolve().parent

WORKSPACE_PACKAGES: list[tuple[str, str]] = [
    ("algutils", "ialdev-core"),
    ("fio", "ialdev-io"),
    ("imgtools", "ialdev-img"),
    ("maths", "ialdev-maths"),
    ("dataman", "ialdev-dataman"),
    ("vis", "ialdev-vis"),
    ("annotations", "ialdev-annotations"),
    ("engines", "ialdev-engines"),
]

FOLDER_BY_DIST = {dist: folder for folder, dist in WORKSPACE_PACKAGES}
DIST_BY_FOLDER = {folder: dist for folder, dist in WORKSPACE_PACKAGES}

PYPROJECT_PATHS: list[Path] = [ROOT / "pyproject.toml"] + [
    ROOT / folder / "pyproject.toml" for folder, _ in WORKSPACE_PACKAGES
]

PROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')
DEP_LINE_RE = re.compile(
    r'^(\s*)"' r'((?:ialdev-[a-z0-9-]+|ialgdev)(?:\[[^\]]+\])?[^"]*)"' r'(\s*,?\s*)$'
)
INLINE_DEP_ARRAY_RE = re.compile(
    r'^(\s*)([a-zA-Z0-9_.-]+)\s*=\s*\[\s*"'
    r'((?:ialdev-[a-z0-9-]+|ialgdev)(?:\[[^\]]+\])?[^"]*)"\s*\]\s*$'
)
REQ_BODY_RE = re.compile(
    r'^(?P<name>ialdev-[a-z0-9-]+|ialgdev)(?P<extras>\[[^\]]+\])?(?P<spec>.*)$',
    re.IGNORECASE,
)


def resolve_packages(names: list[str]) -> set[str]:
    dists: set[str] = set()
    for raw in names:
        key = raw.strip().lower().replace("_", "-")
        if key in DIST_BY_FOLDER:
            dists.add(DIST_BY_FOLDER[key])
            continue
        for dist in FOLDER_BY_DIST:
            if dist.lower() == key:
                dists.add(dist)
                break
        else:
            if key == "ialgdev":
                dists.add("ialgdev")
                continue
            known = ", ".join(sorted(DIST_BY_FOLDER) + list(FOLDER_BY_DIST) + ["ialgdev"])
            raise SystemExit(f"Unknown package {raw!r}. Known: {known}")
    return dists


def read_project_version(pyproject: Path) -> str:
    in_project = False
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("[") and stripped != "[project]":
            break
        if in_project:
            match = PROJECT_VERSION_RE.match(line)
            if match:
                return match.group(1)
    raise ValueError(f"No [project].version in {pyproject}")


def load_version_map() -> dict[str, str]:
    versions = {
        dist: read_project_version(ROOT / folder / "pyproject.toml")
        for folder, dist in WORKSPACE_PACKAGES
    }
    versions["ialgdev"] = read_project_version(ROOT / "pyproject.toml")
    return versions


def parse_requirement_body(body: str) -> tuple[str, str, str]:
    match = REQ_BODY_RE.match(body)
    if not match:
        raise ValueError(f"Cannot parse workspace requirement body: {body!r}")
    return match.group("name"), match.group("extras") or "", match.group("spec")


def format_requirement(name: str, extras: str, version: str) -> str:
    return f"{name}{extras}>={version}"


def spec_admits(spec: str, version: str) -> bool:
    """True if the existing version specifier already allows *version*.

    A backward-compatible release (patch/minor) stays within an open ``>=`` floor,
    so the dependent's pin need not change — this is what prevents a bump of a
    widely-depended package (e.g. ialdev-core) from cascading into every dependent.
    If packaging is unavailable we return False, falling back to always refreshing
    the floor (the previous behavior).
    """
    if SpecifierSet is None or not spec.strip():
        return False
    try:
        return SpecifierSet(spec).contains(version, prereleases=True)
    except Exception:
        return False


def maybe_update_requirement(
    body: str,
    versions: dict[str, str],
    only_dists: set[str] | None,
) -> tuple[str, bool]:
    name, extras, spec = parse_requirement_body(body)
    if name not in versions:
        return body, False
    if only_dists is not None and name not in only_dists:
        return body, False
    if spec_admits(spec, versions[name]):
        return body, False
    new_body = format_requirement(name, extras, versions[name])
    return new_body, new_body != body


def sync_pyproject(
    path: Path,
    versions: dict[str, str],
    only_dists: set[str] | None,
    write: bool,
) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    section: str | None = None
    in_dep_list = False
    changes: list[str] = []
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if stripped == "[project]":
                section = "project"
            elif stripped == "[project.optional-dependencies]":
                section = "optional"
            else:
                section = None
            in_dep_list = False
            out.append(line)
            continue

        if section == "project" and stripped.startswith("dependencies = ["):
            in_dep_list = True
            out.append(line)
            continue

        if section == "optional":
            inline = INLINE_DEP_ARRAY_RE.match(line.rstrip("\n"))
            if inline:
                indent, _key, body = inline.group(1), inline.group(2), inline.group(3)
                new_body, changed = maybe_update_requirement(body, versions, only_dists)
                if changed:
                    rel = path.relative_to(ROOT)
                    changes.append(f"{rel}: {body!r} -> {new_body!r}")
                    line = f'{indent}{inline.group(2)} = ["{new_body}"]\n'
                out.append(line)
                continue
            if re.match(r"^[a-zA-Z0-9_.-]+\s*=\s*\[", stripped):
                in_dep_list = True
                out.append(line)
                continue

        if in_dep_list and stripped == "]":
            in_dep_list = False
            out.append(line)
            continue

        if in_dep_list:
            match = DEP_LINE_RE.match(line.rstrip("\n"))
            if match:
                indent, body, trail = match.group(1), match.group(2), match.group(3)
                new_body, changed = maybe_update_requirement(body, versions, only_dists)
                if changed:
                    rel = path.relative_to(ROOT)
                    changes.append(f"{rel}: {body!r} -> {new_body!r}")
                    line = f'{indent}"{new_body}"{trail}\n'

        out.append(line)

    if changes and write:
        path.write_text("".join(out), encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        help="Folder or distribution names to sync (default: all workspace packages)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--check", action="store_true", help="Exit 1 if pins are out of date")
    args = parser.parse_args()

    only_dists = resolve_packages(args.packages) if args.packages else None
    version_map = load_version_map()
    write = not args.dry_run and not args.check

    all_changes: list[str] = []
    for pyproject in PYPROJECT_PATHS:
        if pyproject.is_file():
            all_changes.extend(sync_pyproject(pyproject, version_map, only_dists, write=write))

    if not all_changes:
        print("Workspace dependency pins are already up to date.")
        return 0

    for entry in all_changes:
        print(entry)

    if args.dry_run:
        print(f"\n{len(all_changes)} change(s) (dry run, no files modified).")
        return 0
    if args.check:
        print(f"\n{len(all_changes)} pin(s) out of date. Run ./sync_workspace_deps.py")
        return 1

    print(f"\nUpdated {len(all_changes)} requirement(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
