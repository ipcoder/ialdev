# imview — interactive image grid

`iad.vis.imview` is the anywidget-based image grid for marimo and Jupyter. It
replaces JSON heatmaps with binary pixel transport and client-side rendering.

## Capabilities

| Feature | Where | Notes |
|---------|-------|-------|
| Multi-panel grids | Python layout | Regular `(rows, cols)` or mosaic strings |
| Scalar + RGB panels | `data.py` | Auto-detect; grayscale RGB collapsed to scalar |
| Colormaps + clim | Frontend | LUTs built in Python, applied in browser |
| Pan / zoom | `grid.ts` | Per-panel view window; nearest-neighbor upscale |
| Pixel inspect | `inspect.ts` | Fixed-width coordinate/value readout |
| Axis ticks | `labels.ts` | Follow visible window during pan/zoom |
| Colorbars | Python layout + renderer | Scalar panels only |
| Static oversampling | `data.py` | One-time integer downsample in Python |
| `figsize` sizing | `data.py` + CSS | Reference CSS px; 240 px min per dimension |
| `max_zoom` / `downsample` | `data.py` | Control buffer resolution vs. transfer size |
| Data budget readout | Toolbar | MB / Mpx sent vs. full; red when over budget |
| Resolution badge | `labels.ts` | Per-panel `(N:1)` ratio, updates with zoom |
| In-place updates | `ImageGrid.update_data` | Same shapes; reuses prep kwargs |
| marimo / Jupyter | `api.py` | Auto backend; `.ui` for layout composition |

## Architecture

```
Python                              Browser (imgrid.js)
─────────────────────────────────   ────────────────────────────────
imgrid()                              index.ts (entry)
  └─ prepare_grid / data.py             ├─ GridModel (trait bridge)
       layout, downsample, pack         ├─ Canvas2DRenderer
  └─ ImageGridWidget.create             ├─ LabelsOverlay (ticks, titles)
       traitlets → binary buffers       ├─ controls (toolbar)
  └─ ImageGrid wrapper                  ├─ inspect (hover readout)
       display / update_data             └─ grid (pan/zoom)
```

**Static oversampling:** Python chooses an integer downsample factor per panel,
packs buffers once, and sends them over anywidget binary comm. The frontend
draws a sub-window of the buffer for pan/zoom. Upscaling past buffer detail
uses nearest-neighbor interpolation; downscaling stays smooth.

**Layout:** All panel rects, colorbar positions, and canvas size are computed
in Python (`_display_layout`) as reference CSS pixels. The frontend scales
to the display width (driven by `figsize`) while preserving aspect ratio.

## Package layout

```
vis/
├── IMVIEW.md                 # this file
├── README.md                 # package overview + install
├── js/                       # TypeScript sources (build → static/imgrid.js)
│   └── src/
│       ├── index.ts          # anywidget render entry, wiring
│       ├── model.ts          # trait getters (panels, view, data_*)
│       ├── canvas.ts         # HiDPI canvas sync
│       ├── grid.ts           # pan/zoom, view state
│       ├── controls.ts       # toolbar, data readout, clim/cmap toggles
│       ├── inspect.ts        # pixel hover readout
│       ├── labels.ts         # titles, axis ticks, resolution badge
│       ├── selection.ts      # panel selection state
│       ├── colormap.ts       # scalar recoloring
│       ├── types.ts          # PanelMeta, ViewState, …
│       └── renderer/
│           ├── Renderer.ts   # interface
│           └── Canvas2DRenderer.ts
├── src/iad/vis/
│   ├── gridcore.py           # shared grid/mosaic/resize helpers
│   ├── mutils.py             # marimo mogrid(); backend='wgt' → imview
│   └── imview/
│       ├── __init__.py       # exports imgrid, ImageGrid
│       ├── api.py            # imgrid(), ImageGrid
│       ├── data.py           # prepare_grid*, layout, downsample
│       ├── widget.py         # anywidget traits + apply_prepared
│       ├── colormaps.py      # matplotlib LUT → bytes
│       └── static/
│           ├── imgrid.js     # built bundle
│           └── imgrid.css
└── tests/test_imview.py
```

## Public API

### `imgrid(...)`

Main entry point. Returns an `ImageGrid` unless `out=` requests a component.

```python
from iad.vis.imview import imgrid

grid = imgrid(
    left, right, diff,
    titles=["left", "right", "diff"],
    figsize=(900, None),
    max_zoom=2,
    clim="auto",
)
```

### `ImageGrid`

| Attribute / method | Description |
|--------------------|-------------|
| `.widget` | Raw anywidget instance (traits, buffers) |
| `.ui` | marimo `mo.ui.anywidget(...)` when backend is marimo |
| `.value` | `{'cursor', 'selection', 'view'}` reactive state |
| `.panels` | Python `PanelData` list from preparation |
| `.update_data(data)` | Replace buffers in place (dict by title or sequence) |

### marimo usage

```python
# Single grid — return as last expression
grid = imgrid(a, b, figsize=(800, None))

# Stack multiple grids — use .ui
mo.vstack([grid1.ui, grid2.ui])

# Reactive readout
grid.value["cursor"]  # current hover panel + coords
```

Via `mutils`:

```python
from iad.vis.mutils import mogrid, Backend

mogrid(a, b, backend=Backend.WGT, figsize=(800, 600), max_zoom=2)
```

### Preparation API (lower level)

```python
from iad.vis.imview.data import prepare_grid, prepare_grid_from_parsed

prepared = prepare_grid(img, titles=["a"], figsize=(600, 400), max_zoom=1.5)
# prepared.panels, prepared.canvas_size, prepared.sent_bytes, …
```

## Key parameters

### `figsize=(width, height)`

Target grid size in CSS pixels. Either dimension may be `None`:

- `(800, None)` — fit width 800, height from aspect ratio + chrome
- `(None, 600)` — fit height 600
- `(800, 600)` — fit inside both bounds

Panel aspect ratios always match the source images. Each dimension has a
**240 px minimum** (`_MIN_PANEL_PX`).

### `max_zoom` vs `downsample`

Mutually exclusive.

| Mode | Effect |
|------|--------|
| *(default)* | Auto factor from `max_pixels` budget |
| `max_zoom=2` | Buffer ≥ 2× panel display size (crisp 2× zoom headroom) |
| `max_zoom='full'` | Factor 1 — full resolution sent |
| `downsample=4` | Fixed 4× block-mean downsample |

When `max_zoom` or `downsample` is set explicitly and total sent pixels exceed
`max_pixels * n_panels`, the toolbar readout turns red (`data_over_budget`).

### `update_data`

```python
grid.update_data({"left": new_left, "right": new_right})
grid.update_data([arr0, arr1])  # panel order
```

Arrays must match original shapes. Uses the same `prep_kwargs` as initial
creation (cmap, clim, figsize, downsample, …).

## Widget traits (Python ↔ JS)

| Trait | Direction | Purpose |
|-------|-----------|---------|
| `panels` | → JS | Metadata: layout, clim, factor, source dims |
| `buffers` | → JS | Binary pixel data (float32 scalar / uint8 RGBA) |
| `luts` | → JS | Colormap byte blobs |
| `canvas_width/height` | → JS | Reference layout size |
| `data_sent_*`, `data_full_*` | → JS | Transfer accounting |
| `view` | ↔ | `{scale, tx, ty}` pan/zoom |
| `cursor`, `selection` | ← JS | Inspect / selection state |
| `cbar`, `ticks`, `show_grid`, `adj_clim` | ↔ | Display toggles |

## Frontend modules

| Module | Role |
|--------|------|
| `Canvas2DRenderer` | Draw panels, colorbars, grid overlay; nearest upscale |
| `LabelsOverlay` | DOM overlay for titles, ticks (pan/zoom-aware), res badge |
| `attachPanZoom` | Wheel zoom + drag pan; updates `view` trait |
| `attachInspect` | Hover readout with tabular-nums formatting |
| `buildToolbar` | Cmap/clim controls, data MB/Mpx readout |
| `GridModel` | Typed accessors over anywidget model traits |

## Build (developers)

```bash
cd vis/js && npm install && npm run build
# writes vis/src/iad/vis/imview/static/imgrid.js
```

Run tests:

```bash
pixi run pytest vis/tests/test_imview.py
```

## Related backends

| Module | Backend | Use case |
|--------|---------|----------|
| `iad.vis.imview` | anywidget | Interactive notebooks (this doc) |
| `iad.vis.insight` | matplotlib | Desktop / static figures |
| `iad.vis.plgrid` | Plotly | Lightweight overview plots |
| `iad.vis.mutils.mogrid` | switchable | marimo helper; `backend='wgt'` → imview |
