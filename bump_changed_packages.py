#!/usr/bin/env python3
"""
Bump ``version`` in workspace ``pyproject.toml`` files for packages with git changes.

Typical release prep::

  ./bump_changed_packages.py --dry-run
  ./bump_changed_packages.py
  ./sync_workspace_deps.py

Usage:
  ./bump_changed_packages.py                    # patch-bump changed packages vs default ref
  ./bump_changed_packages.py dataman algutils   # only consider these folders / dist names
  ./bump_changed_packages.py --since origin/main
  ./bump_changed_packages.py --part minor
  ./bump_changed_packages.py --all              # bump every workspace package
  ./bump_changed_packages.py --sync-deps        # run sync_workspace_deps.py after bumping
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

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

DIST_BY_FOLDER = {folder: dist for folder, dist in WORKSPACE_PACKAGES}
META_FOLDER = "."
META_DIST = "ialgdev"

PROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')
INIT_VERSION_RE = re.compile(r'^(__version__\s*=\s*)"[^"]+"')


def resolve_folders(names: list[str]) -> list[str]:
    if not names:
        return [folder for folder, _ in WORKSPACE_PACKAGES]
    folders: list[str] = []
    for raw in names:
        key = raw.strip().lower().replace("_", "-")
        if key in DIST_BY_FOLDER:
            folders.append(key)
            continue
        for folder, dist in WORKSPACE_PACKAGES:
            if folder == key or dist.lower() == key:
                folders.append(folder)
                break
        else:
            if key in ("ialgdev", ".", "root"):
                folders.append(META_FOLDER)
                continue
            known = ", ".join(sorted(DIST_BY_FOLDER) + ["ialgdev"])
            raise SystemExit(f"Unknown package {raw!r}. Known: {known}")
    return folders


def git_ok() -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def git_rev_exists(ref: str) -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def default_since_ref() -> str:
    for ref in ("origin/main", "main", "origin/master", "master"):
        if git_rev_exists(ref):
            merge_base = subprocess.check_output(
                ["git", "merge-base", "HEAD", ref],
                cwd=ROOT,
                text=True,
            ).strip()
            if merge_base:
                return merge_base
    if git_rev_exists("HEAD~1"):
        return "HEAD~1"
    return "HEAD"


def package_changed(folder: str, since: str) -> bool:
    paths = [folder] if folder != META_FOLDER else [
        "pyproject.toml",
        "README.md",
        "setup.py",
    ]
    diff = subprocess.run(
        ["git", "diff", "--name-only", since, "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if diff.stdout.strip():
        return True
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(untracked.stdout.strip())


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


def bump_version(version: str, part: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", version)
    if not match:
        raise ValueError(f"Cannot bump non-semver version: {version!r}")
    major, minor, patch, suffix = match.groups()
    major_i, minor_i, patch_i = int(major), int(minor), int(patch)
    if part == "major":
        return f"{major_i + 1}.0.0{suffix}"
    if part == "minor":
        return f"{major_i}.{minor_i + 1}.0{suffix}"
    if part == "patch":
        return f"{major_i}.{minor_i}.{patch_i + 1}{suffix}"
    raise ValueError(f"Unknown part: {part!r}")


def write_project_version(pyproject: Path, version: str) -> None:
    lines = pyproject.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project = False
    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
        elif in_project and stripped.startswith("[") and stripped != "[project]":
            in_project = False
        if in_project and PROJECT_VERSION_RE.match(line.rstrip("\n")):
            line = f'version = "{version}"\n'
            replaced = True
        out.append(line)
    if not replaced:
        raise ValueError(f"Could not update version in {pyproject}")
    pyproject.write_text("".join(out), encoding="utf-8")


def find_init_version_files(folder: str) -> list[Path]:
    if folder == META_FOLDER:
        return []
    base = ROOT / folder
    return sorted(base.glob("src/**/__init__.py"))


def write_init_version(init_file: Path, version: str) -> bool:
    lines = init_file.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    replaced = False
    for line in lines:
        match = INIT_VERSION_RE.match(line.rstrip("\n"))
        if match:
            line = f'{match.group(1)}"{version}"\n'
            replaced = True
        out.append(line)
    if not replaced:
        return False
    init_file.write_text("".join(out), encoding="utf-8")
    return True


def pyproject_for_folder(folder: str) -> Path:
    if folder == META_FOLDER:
        return ROOT / "pyproject.toml"
    return ROOT / folder / "pyproject.toml"


def bump_package(folder: str, part: str, dry_run: bool) -> list[str]:
    pyproject = pyproject_for_folder(folder)
    dist = META_DIST if folder == META_FOLDER else DIST_BY_FOLDER[folder]
    old = read_project_version(pyproject)
    new = bump_version(old, part)
    if old == new:
        return []
    rel = pyproject.relative_to(ROOT)
    changes = [f"{rel}: {dist} {old} -> {new}"]
    if not dry_run:
        write_project_version(pyproject, new)
        for init_file in find_init_version_files(folder):
            if write_init_version(init_file, new):
                changes.append(f"{init_file.relative_to(ROOT)}: __version__ -> {new}")
    else:
        for init_file in find_init_version_files(folder):
            text = init_file.read_text(encoding="utf-8")
            if INIT_VERSION_RE.search(text, re.MULTILINE):
                changes.append(f"{init_file.relative_to(ROOT)}: __version__ -> {new}")
    return changes


def run_sync_deps(dry_run: bool) -> None:
    cmd = [sys.executable, str(ROOT / "sync_workspace_deps.py")]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        help="Folder or distribution names (default: all workspace packages)",
    )
    parser.add_argument(
        "--since",
        metavar="REF",
        help="Git ref to compare against (default: merge-base with main, else HEAD~1)",
    )
    parser.add_argument(
        "--part",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Which segment of the semver to increment (default: patch)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Bump all selected packages, not only those with git changes",
    )
    parser.add_argument(
        "--meta",
        choices=("auto", "never", "always"),
        default="auto",
        help="Bump root ialgdev meta-package: auto when any sub-package is bumped (default)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--sync-deps",
        action="store_true",
        help="Run sync_workspace_deps.py after bumping",
    )
    args = parser.parse_args()

    if not git_ok():
        print("Not a git repository; use --all to bump without change detection.", file=sys.stderr)
        if not args.all:
            return 1

    since = args.since or default_since_ref()
    folders = resolve_folders(args.packages)

    to_bump: list[str] = []
    for folder in folders:
        if folder == META_FOLDER:
            continue
        if args.all or not git_ok() or package_changed(folder, since):
            to_bump.append(folder)

    if args.meta == "always":
        if META_FOLDER not in to_bump:
            to_bump.append(META_FOLDER)
    elif args.meta == "auto" and to_bump and META_FOLDER not in to_bump:
        to_bump.append(META_FOLDER)

    if not to_bump:
        print(f"No package changes under {folders!r} since {since}.")
        print("Use --all to bump anyway, or change code and retry.")
        return 0

    all_changes: list[str] = []
    for folder in to_bump:
        all_changes.extend(bump_package(folder, args.part, args.dry_run))

    if not all_changes:
        print("Nothing to bump.")
        return 0

    for line in all_changes:
        print(line)

    if args.dry_run:
        print(f"\n{len(to_bump)} package(s) would be bumped ({args.part}); dry run.")
    else:
        print(f"\nBumped {len(to_bump)} package(s) ({args.part}).")

    if args.sync_deps and to_bump:
        print()
        run_sync_deps(args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
