import { displayPoint } from './canvas';
import type { GridModel } from './model';
import type { Renderer } from './renderer/Renderer';
import type { PanelSelection } from './selection';
import type { ViewState } from './types';

function canvasPoint(canvas: HTMLCanvasElement, ev: MouseEvent | WheelEvent): { x: number; y: number } {
  return displayPoint(canvas, ev);
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

function clampView(view: ViewState): ViewState {
  const scale = clamp(view.scale, 1, 64);
  const maxOffset = 1 - 1 / scale;
  return {
    scale,
    tx: clamp(view.tx, 0, maxOffset),
    ty: clamp(view.ty, 0, maxOffset),
  };
}

function setSyncedView(
  model: GridModel,
  renderer: Renderer,
  view: ViewState,
  onViewChange: () => void,
): void {
  const next = clampView(view);
  model.setView(next);
  renderer.setView(next);
  onViewChange();
}

export function attachPanZoom(
  canvas: HTMLCanvasElement,
  model: GridModel,
  renderer: Renderer,
  onViewChange: () => void,
  selection: PanelSelection,
): () => void {
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let activePanelId: number | null = null;

  const onWheel = (ev: WheelEvent) => {
    ev.preventDefault();
    const view = { ...model.view };
    const point = canvasPoint(canvas, ev);
    const hit = renderer.panelAt(point.x, point.y);
    if (!hit) return;
    const panel = model.panels.find((p) => p.id === hit.panelId);
    if (!panel) return;
    const factor = ev.deltaY > 0 ? 0.85 : 1.18;
    const newScale = clamp(view.scale * factor, 1, 64);
    const normX = hit.localX / panel.width;
    const normY = hit.localY / panel.height;
    const anchorX = (normX - view.tx) * view.scale;
    const anchorY = (normY - view.ty) * view.scale;
    setSyncedView(
      model,
      renderer,
      {
        scale: newScale,
        tx: normX - anchorX / newScale,
        ty: normY - anchorY / newScale,
      },
      onViewChange,
    );
  };

  const onDown = (ev: MouseEvent) => {
    if (ev.button !== 0) return;
    const point = canvasPoint(canvas, ev);
    const hit = renderer.panelAt(point.x, point.y);
    if (!hit) return;
    if (ev.ctrlKey && ev.altKey) {
      ev.preventDefault();
      selection.toggle(hit.panelId);
      return;
    }
    dragging = true;
    activePanelId = hit.panelId;
    lastX = point.x;
    lastY = point.y;
  };

  const onMove = (ev: MouseEvent) => {
    if (!dragging) return;
    if (activePanelId === null) return;
    const point = canvasPoint(canvas, ev);
    const prev = renderer.panelAt(lastX, lastY);
    const next = renderer.panelAt(point.x, point.y);
    const panel = model.panels.find((p) => p.id === activePanelId);
    if (prev?.panelId === activePanelId && next?.panelId === activePanelId && panel) {
      setSyncedView(
        model,
        renderer,
        {
          ...model.view,
          tx: model.view.tx + (prev.localX - next.localX) / panel.width,
          ty: model.view.ty + (prev.localY - next.localY) / panel.height,
        },
        onViewChange,
      );
    }
    lastX = point.x;
    lastY = point.y;
  };

  const onUp = () => {
    dragging = false;
    activePanelId = null;
  };

  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('mousedown', onDown);
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);

  return () => {
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('mousedown', onDown);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };
}

export function resetView(model: GridModel, renderer: Renderer, onViewChange: () => void): void {
  const view: ViewState = { scale: 1, tx: 0, ty: 0 };
  model.setView(view);
  renderer.setView(view);
  onViewChange();
}
