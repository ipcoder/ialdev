import { buildToolbar } from './controls';
import { attachPanZoom } from './grid';
import { attachInspect } from './inspect';
import { GridModel } from './model';
import { Canvas2DRenderer } from './renderer/Canvas2DRenderer';
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
  });
  renderer.setView(model.view);
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

  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'iad-imgrid__canvas-wrap';
  const canvas = document.createElement('canvas');
  canvas.className = 'iad-imgrid__canvas';
  canvasWrap.appendChild(canvas);
  root.appendChild(canvasWrap);

  const readout = document.createElement('div');
  readout.className = 'iad-imgrid__readout';
  root.appendChild(readout);

  const renderer = new Canvas2DRenderer();
  const gridDims = model.get<[number, number]>('grid');
  renderer.init(canvas, gridModel.panels, gridDims);

  const redraw = () => renderer.draw();
  const resync = () => {
    syncRenderer(gridModel, renderer);
    redraw();
  };

  buildToolbar(root, gridModel, renderer, redraw);
  resync();

  const cleanups: Array<() => void> = [];
  cleanups.push(attachPanZoom(canvas, gridModel, renderer, redraw));
  cleanups.push(attachInspect(canvas, readout, gridModel, renderer));

  gridModel.onBuffersReady(resync);
  gridModel.onChange(() => {
    if (gridModel.buffers.some((b) => b.length > 0)) {
      resync();
    }
  });

  return () => {
    cleanups.forEach((fn) => fn());
    renderer.dispose();
    el.replaceChildren();
  };
}

export default { render };
