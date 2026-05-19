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

In every **changed** package, increment `version` in that folder’s `pyproject.toml` (and `__version__` in `__init__.py` if the package defines one, e.g. `dataman`).

Use [semantic versioning](https://semver.org/) in practice: patch for fixes, minor for compatible features, major for breaking changes.

If you change the root meta-package dependencies or release a new aggregate, bump `version` in the root `pyproject.toml` as well.

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

To publish the meta-package from the repo root:

```bash
python -m build
twine upload dist/*
```

*(Root uses setuptools, not Flit.)*

## Checklist (release)

- [ ] Code reviewed and tests pass (`pixi run test-all` or targeted tasks)
- [ ] `version` bumped in each changed `<pkg>/pyproject.toml`
- [ ] Root `pyproject.toml` bumped if releasing `ialgdev`
- [ ] `./sync_workspace_deps.py` run (no pending changes with `--check`)
- [ ] Wheels build: `pixi run build-ialdev` or per-package `flit build --no-use-vcs`
- [ ] Packages published in dependency order
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

## Related files

| Path | Purpose |
|------|---------|
| `sync_workspace_deps.py` | Propagate bumped `ialdev-*` versions into dependent `pyproject.toml` files |
| `publish_pypi` | Batch `flit publish` for main sub-packages |
| `pixi.toml` | Dev env and tasks (`sync-workspace-deps`, `build-ialdev`, `test-*`, `publish-pypi`) |
| `README.md` | User-facing install and package overview |
