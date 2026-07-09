import type { DrawOptions, PanelMeta, Rect } from './types';

const TITLE_BASELINE = 3;

function scaledRect(rect: Rect, scale: number): Rect {
  return { x: rect.x * scale, y: rect.y * scale, w: rect.w * scale, h: rect.h * scale };
}

/** Format a set of tick values with the least precision needed to keep them distinct. */
function formatTickValues(values: number[]): string[] {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return values.map(() => '—');
  const maxAbs = Math.max(...finite.map(Math.abs));
  if (maxAbs !== 0 && (maxAbs >= 1000 || maxAbs < 0.01)) {
    return values.map((v) => (Number.isFinite(v) ? v.toExponential(2) : '—'));
  }
  const targetUnique = new Set(values).size;
  let strs = values.map((v) => (Number.isFinite(v) ? v.toFixed(0) : '—'));
  for (let decimals = 0; decimals <= 8; decimals++) {
    strs = values.map((v) => (Number.isFinite(v) ? v.toFixed(decimals) : '—'));
    if (new Set(strs).size >= targetUnique) break;
  }
  return strs;
}

function formatResRatio(origPerDisp: number): string {
  const fmt = (x: number): string => {
    const rounded = Math.round(x);
    if (Math.abs(x - rounded) < 0.01) return String(rounded);
    return x.toFixed(2);
  };
  if (origPerDisp >= 1) return `(1:${fmt(origPerDisp)})`;
  return `(${fmt(1 / origPerDisp)}:1)`;
}

function placeLabel(
  root: HTMLElement,
  key: string,
  text: string,
  left: number,
  top: number,
  className: string,
  align: 'left' | 'center' | 'right' = 'left',
): void {
  let el = root.querySelector<HTMLElement>(`[data-key="${key}"]`);
  if (!el) {
    el = document.createElement('span');
    el.dataset.key = key;
    el.className = className;
    root.appendChild(el);
  }
  el.textContent = text;
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  el.style.textAlign = align;
}

export class LabelsOverlay {
  private root: HTMLElement;
  private seenKeys = new Set<string>();

  constructor(parent: HTMLElement) {
    this.root = document.createElement('div');
    this.root.className = 'iad-imgrid__labels';
    parent.appendChild(this.root);
  }

  update(
    panels: PanelMeta[],
    displayScale: number,
    drawOptions: DrawOptions,
    climOverrides: Map<number, { lo: number; hi: number }>,
    panelShowGrid: Map<number, boolean> = new Map(),
    origPerDisp: Map<number, number> = new Map(),
    sourceWindows: Map<number, { x: number; y: number; w: number; h: number }> = new Map(),
  ): void {
    this.seenKeys.clear();
    const scale = displayScale;
    const titleBaseline = TITLE_BASELINE * scale;
    for (const panel of panels) {
      const layout = scaledRect(panel.layout, scale);
      const { x, y, w } = layout;
      this.mark(
        `title-${panel.id}`,
        panel.title,
        x,
        y - titleBaseline,
        'iad-imgrid__panel-title',
        'left',
      );
      const ratio = origPerDisp.get(panel.id);
      if (ratio !== undefined && Number.isFinite(ratio) && ratio > 0) {
        this.mark(
          `res-${panel.id}`,
          formatResRatio(ratio),
          x + w,
          y - titleBaseline,
          'iad-imgrid__tick iad-imgrid__res-badge',
          'right',
        );
      }
      const showGrid = panelShowGrid.get(panel.id) ?? false;
      if (showGrid || drawOptions.ticks) {
        this.drawAxisTicks(panel, layout, drawOptions.ticks, sourceWindows.get(panel.id));
      }
      if (drawOptions.cbar && panel.kind === 'scalar' && panel.cbar) {
        const cbar = scaledRect(panel.cbar, scale);
        const clim = climOverrides.get(panel.id);
        const lo = clim?.lo ?? panel.clim[0] ?? 0;
        const hi = clim?.hi ?? panel.clim[1] ?? 1;
        this.drawColorbarTicks(panel.id, cbar, lo, hi);
      }
    }
    this.root.querySelectorAll<HTMLElement>('[data-key]').forEach((el) => {
      if (!this.seenKeys.has(el.dataset.key ?? '')) {
        el.remove();
      }
    });
  }

  dispose(): void {
    this.root.remove();
  }

  private mark(
    key: string,
    text: string,
    left: number,
    top: number,
    className: string,
    align: 'left' | 'center' | 'right',
  ): void {
    this.seenKeys.add(key);
    placeLabel(this.root, key, text, left, top, className, align);
  }

  private drawAxisTicks(
    panel: PanelMeta,
    layout: Rect,
    ticks: string,
    sourceWindow?: { x: number; y: number; w: number; h: number },
  ): void {
    const { x, y, w, h } = layout;
    const nx = 5;
    const ny = 5;
    const factor = panel.factor ?? 1;
    // Buffer-space window currently visible in the panel (reflects pan/zoom).
    const winX = sourceWindow?.x ?? 0;
    const winY = sourceWindow?.y ?? 0;
    const winW = sourceWindow?.w ?? panel.width;
    const winH = sourceWindow?.h ?? panel.height;
    if (ticks.includes('x')) {
      for (let i = 0; i <= nx; i++) {
        const bufX = winX + (winW * i) / nx;
        const px = Math.round(bufX * factor);
        this.mark(
          `xtick-${panel.id}-${i}`,
          String(px),
          x + (w * i) / nx,
          y + h + 2,
          'iad-imgrid__tick iad-imgrid__tick--x',
          'center',
        );
      }
    }
    if (ticks.includes('y')) {
      for (let j = 0; j <= ny; j++) {
        const bufY = winY + (winH * j) / ny;
        const py = Math.round(bufY * factor);
        this.mark(
          `ytick-${panel.id}-${j}`,
          String(py),
          x - 4,
          y + (h * j) / ny,
          'iad-imgrid__tick iad-imgrid__tick--y',
          'right',
        );
      }
    }
  }

  private drawColorbarTicks(
    panelId: number,
    rect: Rect,
    lo: number,
    hi: number,
  ): void {
    const { x, y, w, h } = rect;
    const ticks = 4;
    const values: number[] = [];
    for (let i = 0; i <= ticks; i++) {
      const t = i / ticks;
      values.push(lo + (hi - lo) * (1 - t));
    }
    const labels = formatTickValues(values);
    for (let i = 0; i <= ticks; i++) {
      const ty = y + (i / ticks) * h;
      this.mark(
        `cbar-${panelId}-${i}`,
        labels[i],
        x + w + 4,
        ty,
        'iad-imgrid__tick iad-imgrid__tick--cbar',
        'left',
      );
    }
  }
}
