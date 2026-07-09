# ialdev-vis

Visualization utilities for the `iad` toolbox, published as `ialdev-vis` and imported as `iad.vis`.

Use this package for quick image grids, histograms, Matplotlib helpers, custom colormaps, interactive annotation widgets, Jupyter logging, and optional Qt/3D visualization tools.

## Install

```bash
pip install ialdev-vis
```

Optional extras:

```bash
pip install "ialdev-vis[qt]"
pip install "ialdev-vis[jupyter]"
pip install "ialdev-vis[notebook]"   # anywidget interactive image grid (imview)
pip install "ialdev-vis[marimo]"
pip install "ialdev-vis[3d]"
pip install "ialdev-vis[all]"
```

Requires Python `>=3.10`.

## Highlights

- `imgrid` and `imhist` for fast inspection of images and distributions.
- `iad.vis.imview.imgrid` — interactive notebook image grid (marimo / Jupyter) via anywidget; pixel data sent once as binary buffers with client-side colormap, clim, zoom and cross-panel inspection.
- Matplotlib helpers for figure capture and conversion to arrays/PIL images.
- Built-in custom colormaps.
- Polygon-to-mask helpers and interactive ROI tools.
- Optional Qt image viewer and optional `ipyvolume`/Open3D 3D views.

## Examples

```python
from iad.vis.insight import imgrid, imhist

imgrid(left_image, right_image, titles=["left", "right"], clim="auto")
imhist(left_image, right_image, titles=["left", "right"])
```

```python
from iad.vis.mpl_utils import fig2img

pil_image = fig2img(figure)
```

### Interactive image grid in marimo / Jupyter (`imview`)

```python
from iad.vis.imview import imgrid

grid = imgrid(left, right, diff, titles=["left", "right", "diff"], clim="auto")
grid.ui          # in marimo: reactive anywidget; cross-panel readout via grid.value
```

Rebuild the frontend after editing TypeScript (widget developers only):

```bash
cd vis/js && npm install && npm run build
# or: pixi run build-imview-js   (requires pixi feature build-js / nodejs)
```

**Roadmap:** WebGL renderer (large images), ROI / line-profile tools, live histogram panel, linked selections into pandas/marimo cells, mosaic layouts.

**Note:** `iad.vis.plgrid` remains a lightweight Plotly overview option; desktop/Qt inspection still uses `iad.vis.insight.imgrid` (matplotlib).
