# Publishing workflow

This repository is a **monorepo** of related Python packages. Each subfolder under the repo root is an independent **Flit** project published to PyPI under an `ialdev-*` name. The repo root holds a **setuptools** meta-package `ialgdev` that aggregates them for `pip install ialgdev`.

Development uses **Pixi** (`pixi.toml`) for a reproducible environment; **packaging metadata** lives in each project’s `pyproject.toml`.

## Package map

| Folder       | PyPI name            | Import namespace   |
|-------------|----------------------|--------------------|
| `algutils/` | `ialdev-core`        | `iad.core`         |
| `fio/`      | `ialdev-io`          | `iad.io`           |
| `imgtools/` | `ialdev-img`         | `iad.img`          |
| `maths/`    | `ialdev-maths`       | `iad.maths`        |
| `dataman/`  | `ialdev-dataman`     | `iad.dataman`      |
| `vis/`      | `ialdev-vis`         | `iad.vis`          |
| `engines/`  | `ialdev-engines`     | `iad.engines`      |
| `annotations/` | `ialdev-annotations` | `iad.annotations` |
| *(root)*    | `ialgdev`            | *(meta, no modules)* |

## Configuration split

| File | Role |
|------|------|
| `pixi.toml` | Dev environment: Python pin, conda tools (`graphviz`), editable path installs, test/build/publish tasks |
| `<pkg>/pyproject.toml` | What **pip/PyPI** install for that package: version, runtime deps, optional extras |
| `pyproject.toml` (root) | Meta-package `ialgdev`: aggregates `ialdev-*` for one-shot installs |

Pixi does **not** duplicate every pip dependency. It installs editable workspace packages; each package’s `[project.dependencies]` is resolved by the PyPI solver. After you bump a sub-package version, **dependents must pin the new release** — use `sync_workspace_deps.py` (below).

## Recommended: one-shot release with `publish-changed`

For a normal release (a handful of packages changed, want to bump + build + publish them), use the orchestrator script instead of running the steps below by hand:

```bash
# Requires a clean working tree (commit/stash first).
./publish-changed              # dry-run: prints changed packages, proposed versions, publish order
./publish-changed --yes        # bump + sync-deps + build + publish, in dependency order
./publish-changed --part minor # non-default bump part
./publish-changed vis dataman  # restrict the initial changed-set (still cascades into pin-bumped dependents)
```

`publish-changed` is a thin wrapper around `bump_changed_packages.py`, `sync_workspace_deps.py`, `flit build`, and `publish_pypi` — it doesn't replace them, and you can still run each manually (steps 1-6 below) for finer control, e.g. publishing a hand-picked subset or recovering from a partial failure.

What it does, in order:

1. Aborts if the working tree isn't clean.
2. Determines the changed-package set from `.release-state.json` (see below), not git branch history.
3. Dry-run by default; `--yes` is required to actually change anything.
4. Bumps versions, syncs dependency pins, then **re-scans**: if `sync_workspace_deps.py` touched a dependent's `pyproject.toml` (a pin-only change), that dependent is folded into the same batch and bumped too. Pin sync is compatibility-aware (see step 4 below), so a bump that stays within a dependent's existing `>=` floor does **not** trigger a cascade. Repeats until no new packages appear, capped at 3 iterations (a cap hit indicates an unexpected dependency cycle and aborts the run).
5. Commits the bump + pin-sync changes as one commit.
6. Builds and publishes only the final batch, in dependency order (not all workspace packages).
7. Records each successful publish into `.release-state.json` (via `record_release_state.py`, also wired into `publish_pypi` directly) and commits that separately.
8. Stops on the first build/publish failure, leaving already-published packages' state committed so a re-run doesn't redo them.

## Typical development iteration

### 1. Set up the environment

```bash
pixi install
```

Use `pixi run <task>` or `pixi shell` for commands inside the env.

### 2. Develop and test

Edit code under `<folder>/src/iad/...`. Run tests from the repo root (see `pytest.ini`):

```bash
pixi run test-packages      # core libraries
pixi run test-integration   # dataman, vis
pixi run test-all           # full suite (includes paths listed in pytest.ini)
```

Build wheels locally without publishing:

```bash
pixi run build-ialdev
# or in one package:
cd algutils && pixi run flit build --no-use-vcs
```

### 3. Bump versions

Detect changes per package and bump `version` in `pyproject.toml` (and `__version__` in `src/**/__init__.py` when present):

```bash
./bump_changed_packages.py --dry-run
./bump_changed_packages.py
# or
pixi run bump-changed-packages

# Only specific packages (folder or PyPI name)
./bump_changed_packages.py dataman --part patch

# Bump even if git reports no changes (e.g. re-release after PyPI 400)
./bump_changed_packages.py dataman --all

# Bump and refresh dependency pins in one step
./bump_changed_packages.py --sync-deps
```

**Change detection is per-package against [`.release-state.json`](.release-state.json)**, not a git branch/merge-base guess: each entry records the git commit and version at the time that package was last published. A package is "changed" if its source differs from that recorded commit. This is what makes detection reliable regardless of your current branch — merging a fix to `master` no longer makes it invisible to the bump script (the old merge-base heuristic could silently collapse to `HEAD`, hiding already-committed-but-unpublished changes).

`publish_pypi` (and `record_release_state.py` directly) update `.release-state.json` after every successful publish, so the recorded commit always reflects what's actually live on PyPI.

Packages with no entry yet in `.release-state.json` (never published, e.g. `engines`, root `ialgdev`) fall back to the previous behavior: compare against the merge-base with `origin/main` / `main` / `origin/master` / `master`, or `HEAD~1`. You can still force this fallback for any package with `--since REF`.

Use `--part minor` or `--part major` when needed. The root `ialgdev` meta-package is patch-bumped automatically when any sub-package is bumped (`--meta auto`).

You can still edit versions by hand; use [semantic versioning](https://semver.org/) in practice.

### 4. Sync dependency pins across the workspace

Sub-packages depend on each other (`ialdev-dataman` → `ialdev-core`, etc.). After bumping versions, update **all** `pyproject.toml` files that reference those distributions so pins match the new releases (`name>=X.Y.Z`).

```bash
# Preview
./sync_workspace_deps.py --dry-run

# Update every workspace pin from current package versions
./sync_workspace_deps.py
# or
pixi run sync-workspace-deps

# Only packages you just bumped (folder or PyPI name)
./sync_workspace_deps.py algutils maths
./sync_workspace_deps.py ialdev-core ialdev-maths
```

CI can enforce up-to-date pins:

```bash
./sync_workspace_deps.py --check
```

The script updates `[project].dependencies` and `[project.optional-dependencies]` in the root and all listed sub-projects. It does **not** bump versions for you.

**Compatibility-aware pins.** A pin is only rewritten when the existing specifier no longer admits the new version. A backward-compatible release stays within an open `>=` floor (e.g. bumping `ialdev-core` to `0.2.7` leaves `ialdev-core>=0.2.5` untouched), so a core bump does **not** cascade a pin-only change into every dependent. A pin is refreshed only when it would otherwise exclude the release — an above-the-release floor (`>=0.2.8`), an upper cap the new version violates (`>=0.2.5,<0.3` vs `0.3.0`), or a bare requirement with no floor. This keeps `publish-changed`'s re-scan from folding in dependents whose code did not change. (If `packaging` is unavailable, the script falls back to always refreshing the floor.)

### 5. Commit

Commit version bumps, synced pins, and `pixi.lock` if the environment changed.

### 6. Publish to PyPI

Configure Flit authentication once (token, keyring, or `~/.pypirc`).

```bash
./publish_pypi algutils dataman
./publish_pypi all          # algutils fio imgtools maths dataman vis only
# or
pixi run publish-pypi algutils
```

`publish_pypi` runs `flit publish` in each package directory that uses `flit_core.buildapi`. It skips packages not in its allowlist (e.g. `annotations`, `engines` today — publish those manually with `cd annotations && flit publish` if needed).

Publish **dependencies before dependents** when multiple packages changed (e.g. `ialdev-core` before `ialdev-dataman`).

After each successful publish, `publish_pypi` records the current commit and version into `.release-state.json` via `record_release_state.py`. **Commit that file** alongside your release commit (step 5) — it's what makes the next `bump_changed_packages.py` run accurate. If you publish manually without `publish_pypi` (e.g. the meta-package via `twine`), update `.release-state.json` yourself: `./record_release_state.py <folder> <version>`.

### Troubleshooting

**HTTP 400 on upload** — PyPI does not allow re-uploading the same `name` + `version`. If `pip index versions ialdev-dataman` already lists your version, bump `version` in `pyproject.toml`, run `./sync_workspace_deps.py`, and publish again.

`publish_pypi` skips packages whose version is already on PyPI (see script output).

**Upload order** — publish `ialdev-core`, `ialdev-io`, `ialdev-maths`, `ialdev-img` before `ialdev-dataman` / `ialdev-vis` so dependency pins resolve on PyPI.

To publish the meta-package from the repo root:

```bash
python -m build
twine upload dist/*
```

*(Root uses setuptools, not Flit.)*

## Checklist (release)

Using `./publish-changed --yes` covers the first six items below in one command; the list is still useful if you're doing a manual or partial release.

- [ ] Code reviewed and tests pass (`pixi run test-all` or targeted tasks)
- [ ] Working tree is clean (`publish-changed` requires this; manual flow: commit or stash first)
- [ ] `version` bumped (`bump_changed_packages.py` or manual) in each changed `<pkg>/pyproject.toml`
- [ ] Root `pyproject.toml` bumped if releasing `ialgdev`
- [ ] `./sync_workspace_deps.py` run (no pending changes with `--check`)
- [ ] Wheels build: `pixi run build-ialdev` or per-package `flit build --no-use-vcs`
- [ ] Packages published in dependency order
- [ ] `.release-state.json` updated (automatic via `publish_pypi`) and committed
- [ ] Tag/release notes updated (if your process uses git tags)

## Optional dependencies

Some features are extras, not installed by default:

| Package | Extra | Example install |
|---------|--------|-----------------|
| `ialdev-core` | `ipython` | `pip install "ialdev-core[ipython]"` |
| `ialgdev` (root) | `annotations`, `dev` | `pip install "ialgdev[annotations]"` |
| `ialdev-vis` | `graphviz`, `jupyter`, … | see `vis/pyproject.toml` |

The default Pixi workspace does not include `ialdev-annotations`; add it locally if you work on that package (`pip install -e ./annotations` or extend `pixi.toml`).

## Python version

The Pixi workspace pins **Python 3.10** (`pixi.toml`). Package `requires-python` may allow broader ranges; avoid syntax that requires 3.11+ unless you raise the Pixi pin and test accordingly.

## NumPy version

All `ialdev-*` packages pin **`numpy>=1.26.4,<2`** so PyPI/pixi installs stay on NumPy 1.x and do not pull NumPy 2 into downstream workspaces that are not ready for it. Publish new package versions after changing this constraint.

**Downstream Pixi workspaces** must use a compatible conda NumPy pin as well (e.g. `numpy = ">=1.26.4,<2"`). If conda selects NumPy 2.x, PyPI packages with `numpy<2` will not solve even when the correct `ialdev-dataman` version is requested.

**Do not use** `ialdev-dataman==0.2.2` from PyPI (metadata incorrectly requires `numpy>=2.0`). Require **`>=0.2.4`** (or newer) where the `<2` cap is published.

**Downstream consumers:** require **`ialdev-dataman>=0.2.4`** (and matching `ialdev-core>=0.2.4`). Older PyPI releases are unsafe for NumPy 1.x envs:

| Release | Problem |
|---------|---------|
| `ialdev-dataman==0.2.2` | Declares `numpy>=2.0` |
| `ialdev-core==0.2.2` | Declares `numpy>=2.0` |
| `0.2.3` | NumPy floor only (`>=1.26.4`), no `<2`; still allows NumPy 2 |

Consider [yanking](https://pypi.org/help/#yanked) `0.2.2` on PyPI so resolvers cannot select it.

## Related files

| Path | Purpose |
|------|---------|
| `publish-changed` | One-shot orchestrator: detect changed packages, bump, sync pins, build, publish (dry-run by default) |
| `bump_changed_packages.py` | Patch/minor/major bump for packages changed since their last recorded PyPI publish (`.release-state.json`), falling back to git history for never-published packages |
| `sync_workspace_deps.py` | Propagate bumped `ialdev-*` versions into dependent `pyproject.toml` files |
| `publish_pypi` | Batch `flit publish` for main sub-packages; records each publish into `.release-state.json` |
| `record_release_state.py` | Reads/writes `.release-state.json`; used by `publish_pypi` and `publish-changed`, or manually for bootstrapping/out-of-band publishes |
| `.release-state.json` | Tracked state: last published commit + version per package; source of truth for change detection |
| `pixi.toml` | Dev env and tasks (`bump-changed-packages`, `sync-workspace-deps`, `build-ialdev`, `publish-changed`, `test-*`, `publish-pypi`) |
| `README.md` | User-facing install and package overview |
