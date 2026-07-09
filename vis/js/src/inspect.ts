import { displayPoint } from './canvas';
import type { GridModel } from './model';
import type { Renderer } from './renderer/Renderer';
import type { PanelMeta } from './types';

const SCALAR_VALUE_WIDTH = 10;
const RGB_VALUE_WIDTH = 15;

export const READOUT_PLACEHOLDER = '\u2014';

function panelSourceMaxCoord(panels: PanelMeta[]): { xDigits: number; yDigits: number } {
  let maxX = 0;
  let maxY = 0;
  for (const p of panels) {
    maxX = Math.max(maxX, (p.sourceWidth ?? p.width) - 1);
    maxY = Math.max(maxY, (p.sourceHeight ?? p.height) - 1);
  }
  return {
    xDigits: Math.max(1, String(maxX).length),
    yDigits: Math.max(1, String(maxY).length),
  };
}

function formatCoord(n: number, digits: number): string {
  return String(Math.floor(n)).padStart(digits, ' ');
}

function valueWidthForPanel(panel: PanelMeta): number {
  return panel.kind === 'rgb' ? RGB_VALUE_WIDTH : SCALAR_VALUE_WIDTH;
}

function formatScalarFixed(val: number, width: number): string {
  if (!Number.isFinite(val)) return 'nan'.padStart(width, ' ');
  let s = val.toFixed(4);
  if (s.length > width) {
    s = val.toExponential(3);
  }
  return s.padStart(width, ' ');
}

function formatRgbFixed(rgb: [number, number, number]): string {
  return `(${String(rgb[0]).padStart(3, ' ')}, ${String(rgb[1]).padStart(3, ' ')}, ${String(rgb[2]).padStart(3, ' ')})`;
}

export function formatPixelValue(
  val: number | [number, number, number] | null | undefined,
  panel?: PanelMeta,
): string {
  if (panel) {
    return formatPixelValueFixed(val, panel);
  }
  if (val == null) return READOUT_PLACEHOLDER;
  if (Array.isArray(val)) return formatRgbFixed(val);
  if (typeof val === 'number') {
    return Number.isFinite(val) ? val.toFixed(4) : 'nan';
  }
  return String(val);
}

function formatPixelValueFixed(
  val: number | [number, number, number] | null | undefined,
  panel: PanelMeta,
): string {
  const width = valueWidthForPanel(panel);
  if (val == null) return READOUT_PLACEHOLDER.padStart(width, ' ');
  if (Array.isArray(val)) return formatRgbFixed(val);
  return formatScalarFixed(val, width);
}

function formatCoords(
  x: number,
  y: number,
  panels: PanelMeta[],
): string {
  const { xDigits, yDigits } = panelSourceMaxCoord(panels);
  return `(${formatCoord(x, xDigits)}, ${formatCoord(y, yDigits)})`;
}

export function formatFullReadout(
  x: number,
  y: number,
  panels: PanelMeta[],
  renderer: Renderer,
): string {
  const parts = panels.map((panel) =>
    formatPixelValueFixed(renderer.pixelValue(panel.id, x, y), panel),
  );
  return `${formatCoords(x, y, panels)}: [${parts.join(', ')}]`;
}

export function formatCompactReadout(
  x: number,
  y: number,
  panelId: number,
  panels: PanelMeta[],
  renderer: Renderer,
): string {
  const panel = panels.find((p) => p.id === panelId);
  if (!panel) {
    return formatCoords(x, y, panels);
  }
  const val = renderer.pixelValue(panelId, x, y);
  return `${formatCoords(x, y, panels)}: ${formatPixelValueFixed(val, panel)}`;
}

function renderFullReadout(
  el: HTMLElement,
  x: number,
  y: number,
  hoverPanelId: number,
  panels: PanelMeta[],
  renderer: Renderer,
): void {
  el.replaceChildren(document.createTextNode(`${formatCoords(x, y, panels)}: [`));
  panels.forEach((panel, idx) => {
    if (idx > 0) {
      el.appendChild(document.createTextNode(', '));
    }
    const span = document.createElement('span');
    span.className = 'iad-imgrid__info-value';
    span.textContent = formatPixelValueFixed(renderer.pixelValue(panel.id, x, y), panel);
    if (panel.id === hoverPanelId) {
      span.classList.add('iad-imgrid__info-value--hovered');
    }
    el.appendChild(span);
  });
  el.appendChild(document.createTextNode(']'));
}

export interface InspectHandle {
  cleanup: () => void;
  renderReadout: () => void;
}

export function attachInspect(
  canvas: HTMLCanvasElement,
  readoutEl: HTMLElement,
  model: GridModel,
  renderer: Renderer,
  fits: () => boolean,
): InspectHandle {
  let lastHit: { panelId: number; x: number; y: number } | null = null;

  const renderReadout = (): void => {
    if (!lastHit) {
      readoutEl.textContent = READOUT_PLACEHOLDER;
      return;
    }
    const { panelId, x, y } = lastHit;
    if (!fits()) {
      readoutEl.textContent = formatCompactReadout(x, y, panelId, model.panels, renderer);
      return;
    }
    renderFullReadout(readoutEl, x, y, panelId, model.panels, renderer);
  };

  readoutEl.textContent = READOUT_PLACEHOLDER;

  const onMove = (ev: MouseEvent) => {
    if (!model.inspectEnabled) return;
    const { x: cx, y: cy } = displayPoint(canvas, ev);
    const hit = renderer.panelAt(cx, cy);
    if (!hit) {
      lastHit = null;
      readoutEl.textContent = READOUT_PLACEHOLDER;
      model.setCursor({});
      return;
    }
    const coords = renderer.imageCoords(hit.panelId, hit.localX, hit.localY);
    if (!coords) return;
    const { x, y } = coords;
    lastHit = { panelId: hit.panelId, x, y };
    renderReadout();
    const values = model.panels.map((panel) => {
      const val = renderer.pixelValue(panel.id, x, y);
      return { title: panel.title, value: formatPixelValueFixed(val, panel) };
    });
    model.setCursor({
      panel: hit.panelId,
      x,
      y,
      values,
      text: readoutEl.textContent ?? '',
    });
  };

  canvas.addEventListener('mousemove', onMove);
  return {
    cleanup: () => canvas.removeEventListener('mousemove', onMove),
    renderReadout,
  };
}
