import { buildToolbar } from './controls';
import { attachPanZoom } from './grid';
import { attachInspect } from './inspect';
import { LabelsOverlay } from './labels';
import { GridModel } from './model';
import { Canvas2DRenderer } from './renderer/Canvas2DRenderer';
import { PanelSelection } from './selection';
import type { AnyModel } from './types';

interface RenderContext {
  model: AnyModel;
  el: HTMLElement;
  experimental?: unknown;
}

function lutForPanel(model: GridModel, panelId: number): Uint8Array {
  const panel = model.panels[panelId];
  const luts = model.luts;
  const name = panel?.cmap ?? model.cmaps[panelId] ?? Object.keys(luts)[0];
  return luts[name] ?? new Uint8Array(256 * 4);
}

function syncRenderer(model: GridModel, renderer: Canvas2DRenderer): void {
  const buffers = model.buffers;
  renderer.setBuffers(buffers);
  model.panels.forEach((p, i) => {
    const lut = lutForPanel(model, i);
    renderer.setColormap(p.id, lut);
    const lo = p.clim[0] ?? 0;
    const hi = p.clim[1] ?? 1;
    renderer.setClim(p.id, lo, hi);
    renderer.setPanelOptions(p.id, { showGrid: model.showGrid });
  });
  renderer.setView(model.view);
  renderer.setDrawOptions(model.drawOptions);
}

function render({ model, el }: RenderContext): () => void {
  const gridModel = new GridModel(model);
  const root = document.createElement('div');
  root.className = 'iad-imgrid';
  el.appendChild(root);

  if (gridModel.windowTitle) {
    const title = document.createElement('div');
    title.className = 'iad-imgrid__title';
    title.textContent = gridModel.windowTitle;
    root.appendChild(title);
  }

  const renderer = new Canvas2DRenderer();

  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'iad-imgrid__canvas-wrap';
  const canvas = document.createElement('canvas');
  canvas.className = 'iad-imgrid__canvas';
  canvasWrap.appendChild(canvas);
  const labels = new LabelsOverlay(canvasWrap);

  renderer.init(
    canvas,
    gridModel.panels,
    [gridModel.canvasWidth, gridModel.canvasHeight],
    labels,
  );

  const redraw = () => renderer.draw();

  const selection = new PanelSelection(gridModel.panels.map((p) => p.id));
  selection.onChange(() => {
    renderer.setHighlight(selection.explicit);
    redraw();
  });

  const cleanups: Array<() => void> = [];
  const toolbar = buildToolbar(root, gridModel, renderer, redraw, selection);
  cleanups.push(toolbar.cleanup);

  const resync = () => {
    syncRenderer(gridModel, renderer);
    toolbar.sync();
    redraw();
  };

  root.appendChild(canvasWrap);
  resync();

  const syncDrawOptions = () => {
    renderer.setDrawOptions(gridModel.drawOptions);
    redraw();
  };

  const syncShowGridSeed = () => {
    gridModel.panels.forEach((p) => {
      renderer.setPanelOptions(p.id, { showGrid: gridModel.showGrid });
    });
    toolbar.sync();
    redraw();
  };

  const fits = () => toolbar.bar.scrollWidth <= toolbar.bar.clientWidth + 1;
  const inspect = attachInspect(
    canvas,
    toolbar.info,
    gridModel,
    renderer,
    fits,
  );
  cleanups.push(inspect.cleanup);

  cleanups.push(attachPanZoom(canvas, gridModel, renderer, redraw, selection));

  const resyncTraits = [
    'buffers',
    'panels',
    'canvas_width',
    'canvas_height',
    'data_sent_bytes',
    'data_full_bytes',
    'data_sent_pixels',
    'data_full_pixels',
    'data_over_budget',
    'luts',
    'cmaps',
    'clims',
  ];
  gridModel.onBuffersReady(resync);
  for (const key of resyncTraits) {
    gridModel.onTrait(key, resync);
  }
  for (const key of ['ticks', 'cbar'] as const) {
    gridModel.onTrait(key, syncDrawOptions);
  }
  gridModel.onTrait('show_grid', syncShowGridSeed);

  const toolbarResizeObserver = new ResizeObserver(() => inspect.renderReadout());
  toolbarResizeObserver.observe(toolbar.bar);
  cleanups.push(() => toolbarResizeObserver.disconnect());

  const canvasResizeObserver = new ResizeObserver(() => redraw());
  canvasResizeObserver.observe(canvasWrap);
  cleanups.push(() => canvasResizeObserver.disconnect());

  return () => {
    cleanups.forEach((fn) => fn());
    labels.dispose();
    renderer.dispose();
    el.replaceChildren();
  };
}

export default { render };
