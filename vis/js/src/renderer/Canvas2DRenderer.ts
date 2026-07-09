import { syncHiDpiCanvas } from '../canvas';
import { LabelsOverlay } from '../labels';
import { recolorScalar } from '../colormap';
import type { DrawOptions, PanelDrawOptions, PanelMeta, Rect, ViewState } from '../types';
import { DEFAULT_PANEL_DRAW_OPTIONS } from '../types';
import type { Renderer } from './Renderer';

interface PanelState {
  meta: PanelMeta;
  source: Float32Array | Uint8Array;
  bitmap: HTMLCanvasElement | null;
  lut: Uint8Array;
  lo: number;
  hi: number;
  opts: PanelDrawOptions;
}

export class Canvas2DRenderer implements Renderer {
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private labels: LabelsOverlay | null = null;
  private panels: PanelState[] = [];
  private view: ViewState = { scale: 1, tx: 0, ty: 0 };
  private drawOptions: DrawOptions = { cbar: true, ticks: 'xy' };
  private refWidth = 320;
  private refHeight = 200;
  private displayScale = 1;
  private dpr = 1;
  private highlightIds = new Set<number>();

  setHighlight(ids: number[]): void {
    this.highlightIds = new Set(ids);
  }

  init(
    canvas: HTMLCanvasElement,
    panels: PanelMeta[],
    canvasSize: [number, number],
    labels?: LabelsOverlay,
  ): void {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.labels = labels ?? null;
    this.panels = panels.map((meta) => ({
      meta,
      source: new Float32Array(0),
      bitmap: null,
      lut: new Uint8Array(256 * 4),
      lo: meta.clim[0] ?? 0,
      hi: meta.clim[1] ?? 1,
      opts: { ...DEFAULT_PANEL_DRAW_OPTIONS },
    }));
    this.resizeCanvas(canvasSize[0], canvasSize[1]);
  }

  setBuffers(buffers: Array<Float32Array | Uint8Array>): void {
    buffers.forEach((buf, i) => {
      if (!this.panels[i]) return;
      this.panels[i].source = buf;
      this._refreshPanel(i);
    });
  }

  setColormap(panelId: number, lut: Uint8Array): void {
    const panelIdx = this._panelIndex(panelId);
    const p = this.panels[panelIdx];
    if (!p) return;
    p.lut = lut;
    this._refreshPanel(panelIdx);
  }

  setClim(panelId: number, lo: number, hi: number): void {
    const panelIdx = this._panelIndex(panelId);
    const p = this.panels[panelIdx];
    if (!p) return;
    p.lo = lo;
    p.hi = hi;
    this._refreshPanel(panelIdx);
  }

  setView(view: ViewState): void {
    this.view = view;
  }

  setDrawOptions(options: DrawOptions): void {
    this.drawOptions = options;
  }

  setPanelOptions(panelId: number, partial: Partial<PanelDrawOptions>): void {
    const p = this._panelById(panelId);
    if (!p) return;
    p.opts = { ...p.opts, ...partial };
  }

  getPanelOptions(panelId: number): PanelDrawOptions {
    const p = this._panelById(panelId);
    return p ? { ...p.opts } : { ...DEFAULT_PANEL_DRAW_OPTIONS };
  }

  syncDisplaySize(): void {
    const canvas = this.canvas;
    if (!canvas) return;
    const metrics = syncHiDpiCanvas(canvas, this.refWidth, this.refHeight);
    this.displayScale = metrics.displayScale;
    this.dpr = metrics.dpr;
  }

  draw(): void {
    const ctx = this.ctx;
    const canvas = this.canvas;
    if (!ctx || !canvas) return;
    this.syncDisplaySize();
    const scale = this.displayScale;
    const dpr = this.dpr;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, this.refWidth * scale, this.refHeight * scale);
    const origPerDisp = new Map<number, number>();
    const sourceWindows = new Map<number, { x: number; y: number; w: number; h: number }>();
    for (const p of this.panels) {
      const layout = this._scaledRect(p.meta.layout);
      const { x, y, w, h } = layout;
      if (p.bitmap) {
        const source = this._sourceWindow(p);
        sourceWindows.set(p.meta.id, source);
        const pxPerBufferX = (w * dpr) / source.w;
        const pxPerBufferY = (h * dpr) / source.h;
        ctx.imageSmoothingEnabled = pxPerBufferX <= 1 && pxPerBufferY <= 1;
        ctx.drawImage(p.bitmap, source.x, source.y, source.w, source.h, x, y, w, h);
        const factor = p.meta.factor ?? 1;
        const visibleOrigW = source.w * factor;
        origPerDisp.set(p.meta.id, visibleOrigW / (w * dpr));
      }
      if (p.opts.showGrid) {
        this._drawGrid(ctx, layout);
      }
      if (this.drawOptions.cbar && p.meta.kind === 'scalar' && p.meta.cbar) {
        this._drawColorbarStrip(ctx, p, this._scaledRect(p.meta.cbar));
      }
      if (this.highlightIds.has(p.meta.id)) {
        ctx.strokeStyle = '#4a9eff';
        ctx.lineWidth = 4;
      } else {
        ctx.strokeStyle = '#555';
        ctx.lineWidth = 1;
      }
      ctx.strokeRect(x, y, w, h);
    }
    ctx.restore();
    if (this.labels) {
      const clims = new Map<number, { lo: number; hi: number }>();
      const panelShowGrid = new Map<number, boolean>();
      for (const p of this.panels) {
        clims.set(p.meta.id, { lo: p.lo, hi: p.hi });
        panelShowGrid.set(p.meta.id, p.opts.showGrid);
      }
      this.labels.update(
        this.panels.map((p) => p.meta),
        scale,
        this.drawOptions,
        clims,
        panelShowGrid,
        origPerDisp,
        sourceWindows,
      );
    }
  }

  pixelValue(panelId: number, x: number, y: number): number | [number, number, number] | null {
    const p = this._panelById(panelId);
    if (!p) return null;
    const expected =
      p.meta.kind === 'rgb'
        ? p.meta.width * p.meta.height * 4
        : p.meta.width * p.meta.height;
    if (!p.source.length || p.source.length < expected) return null;
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    if (ix < 0 || iy < 0 || ix >= p.meta.width || iy >= p.meta.height) return null;
    const idx = iy * p.meta.width + ix;
    if (p.meta.kind === 'rgb') {
      const src = p.source as Uint8Array;
      const base = idx * 4;
      return [src[base], src[base + 1], src[base + 2]];
    }
    const val = (p.source as Float32Array)[idx];
    return Number.isFinite(val) ? val : null;
  }

  panelAt(canvasX: number, canvasY: number): { panelId: number; localX: number; localY: number } | null {
    for (const p of this.panels) {
      const { x, y, w, h } = this._scaledRect(p.meta.layout);
      if (canvasX >= x && canvasX < x + w && canvasY >= y && canvasY < y + h) {
        const source = this._sourceWindow(p);
        const lx = source.x + ((canvasX - x) / w) * source.w;
        const ly = source.y + ((canvasY - y) / h) * source.h;
        return { panelId: p.meta.id, localX: lx, localY: ly };
      }
    }
    return null;
  }

  imageCoords(panelId: number, localX: number, localY: number): { x: number; y: number } {
    const p = this._panelById(panelId);
    if (!p) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(p.meta.width - 1, Math.floor(localX))),
      y: Math.max(0, Math.min(p.meta.height - 1, Math.floor(localY))),
    };
  }

  dispose(): void {
    this.panels = [];
    this.canvas = null;
    this.ctx = null;
    this.labels = null;
  }

  resizeCanvas(width: number, height: number): void {
    this.refWidth = Math.max(1, width);
    this.refHeight = Math.max(1, height);
    const canvas = this.canvas;
    if (canvas) {
      canvas.style.aspectRatio = `${this.refWidth} / ${this.refHeight}`;
      // Reference width (driven by figsize) is the target on-screen width,
      // capped to the container via max-width so it shrinks on narrow screens.
      canvas.style.width = `${this.refWidth}px`;
    }
    this.syncDisplaySize();
  }

  private _scaledRect(rect: Rect): Rect {
    const scale = this.displayScale;
    return {
      x: rect.x * scale,
      y: rect.y * scale,
      w: rect.w * scale,
      h: rect.h * scale,
    };
  }

  private _drawColorbarStrip(ctx: CanvasRenderingContext2D, panel: PanelState, rect: Rect): void {
    const { x, y, w, h } = rect;
    const strip = document.createElement('canvas');
    strip.width = 1;
    strip.height = 256;
    const sctx = strip.getContext('2d')!;
    const row = sctx.createImageData(1, 256);
    for (let i = 0; i < 256; i++) {
      const idx = (255 - i) * 4;
      row.data[idx] = panel.lut[i * 4];
      row.data[idx + 1] = panel.lut[i * 4 + 1];
      row.data[idx + 2] = panel.lut[i * 4 + 2];
      row.data[idx + 3] = 255;
    }
    sctx.putImageData(row, 0, 0);
    ctx.drawImage(strip, 0, 0, 1, 256, x, y, w, h);
  }

  private _drawGrid(ctx: CanvasRenderingContext2D, layout: Rect): void {
    const { x, y, w, h } = layout;
    const nx = 5;
    const ny = 5;
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 1;
    for (let i = 1; i < nx; i++) {
      const gx = x + (w * i) / nx;
      ctx.beginPath();
      ctx.moveTo(gx, y);
      ctx.lineTo(gx, y + h);
      ctx.stroke();
    }
    for (let j = 1; j < ny; j++) {
      const gy = y + (h * j) / ny;
      ctx.beginPath();
      ctx.moveTo(x, gy);
      ctx.lineTo(x + w, gy);
      ctx.stroke();
    }
  }

  private _refreshPanel(panelIdx: number): void {
    const p = this.panels[panelIdx];
    if (!p || !p.source.length) return;
    const { width, height, kind } = p.meta;
    const expected = kind === 'rgb' ? width * height * 4 : width * height;
    if (p.source.length < expected) return;
    let rgba: ImageData;
    if (kind === 'rgb') {
      rgba = new ImageData(width, height);
      rgba.data.set((p.source as Uint8Array).subarray(0, width * height * 4));
    } else {
      rgba = recolorScalar(p.source as Float32Array, width, height, p.lut, p.lo, p.hi);
    }
    p.bitmap = this._toBitmap(rgba);
  }

  private _toBitmap(rgba: ImageData): HTMLCanvasElement {
    const cv = document.createElement('canvas');
    cv.width = rgba.width;
    cv.height = rgba.height;
    cv.getContext('2d')!.putImageData(rgba, 0, 0);
    return cv;
  }

  private _panelIndex(panelId: number): number {
    const idx = this.panels.findIndex((panel) => panel.meta.id === panelId);
    return idx >= 0 ? idx : panelId;
  }

  private _panelById(panelId: number): PanelState | undefined {
    return this.panels.find((panel) => panel.meta.id === panelId) ?? this.panels[panelId];
  }

  private _sourceWindow(panel: PanelState): { x: number; y: number; w: number; h: number } {
    const scale = Math.max(1, this.view.scale || 1);
    const sourceW = Math.max(1, panel.meta.width / scale);
    const sourceH = Math.max(1, panel.meta.height / scale);
    const maxX = Math.max(0, panel.meta.width - sourceW);
    const maxY = Math.max(0, panel.meta.height - sourceH);
    return {
      x: Math.max(0, Math.min(maxX, this.view.tx * panel.meta.width)),
      y: Math.max(0, Math.min(maxY, this.view.ty * panel.meta.height)),
      w: sourceW,
      h: sourceH,
    };
  }
}
