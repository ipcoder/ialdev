import { recolorScalar } from '../colormap';
import type { PanelMeta, ViewState } from '../types';
import type { Renderer } from './Renderer';

interface PanelState {
  meta: PanelMeta;
  source: Float32Array | Uint8Array;
  rgba: ImageData | null;
  lut: Uint8Array;
  lo: number;
  hi: number;
  layout: { x: number; y: number; w: number; h: number };
}

export class Canvas2DRenderer implements Renderer {
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private panels: PanelState[] = [];
  private view: ViewState = { scale: 1, tx: 0, ty: 0 };
  private pad = 4;
  private titleH = 18;

  init(canvas: HTMLCanvasElement, panels: PanelMeta[], grid?: [number, number]): void {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.panels = panels.map((meta, i) => ({
      meta,
      source: new Float32Array(0),
      rgba: null,
      lut: new Uint8Array(256 * 4),
      lo: meta.clim[0] ?? 0,
      hi: meta.clim[1] ?? 1,
      layout: { x: 0, y: 0, w: 0, h: 0 },
    }));
    this._layoutPanels(panels, grid);
  }

  setBuffers(buffers: Array<Float32Array | Uint8Array>): void {
    buffers.forEach((buf, i) => {
      if (!this.panels[i]) return;
      this.panels[i].source = buf;
      this._refreshPanel(i);
    });
  }

  setColormap(panelId: number, lut: Uint8Array): void {
    const idx = this.panels.findIndex((panel) => panel.meta.id === panelId);
    const panelIdx = idx >= 0 ? idx : panelId;
    const p = this.panels[panelIdx];
    if (!p) return;
    p.lut = lut;
    this._refreshPanel(panelIdx);
  }

  setClim(panelId: number, lo: number, hi: number): void {
    const idx = this.panels.findIndex((panel) => panel.meta.id === panelId);
    const panelIdx = idx >= 0 ? idx : panelId;
    const p = this.panels[panelIdx];
    if (!p) return;
    p.lo = lo;
    p.hi = hi;
    this._refreshPanel(panelIdx);
  }

  setView(view: ViewState): void {
    this.view = view;
  }

  draw(): void {
    const ctx = this.ctx;
    const canvas = this.canvas;
    if (!ctx || !canvas) return;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const p of this.panels) {
      const { x, y, w, h } = p.layout;
      ctx.fillStyle = '#111';
      ctx.fillRect(x - 2, y - this.titleH - 2, w + 4, h + this.titleH + 4);
      ctx.fillStyle = '#eee';
      ctx.font = '12px system-ui,sans-serif';
      ctx.fillText(p.meta.title, x, y - 6);
      if (p.rgba) {
        const tmp = document.createElement('canvas');
        tmp.width = p.meta.width;
        tmp.height = p.meta.height;
        tmp.getContext('2d')!.putImageData(p.rgba, 0, 0);
        const source = this._sourceWindow(p);
        ctx.drawImage(tmp, source.x, source.y, source.w, source.h, x, y, w, h);
      }
      ctx.strokeStyle = '#555';
      ctx.strokeRect(x, y, w, h);
    }
    ctx.restore();
  }

  pixelValue(panelId: number, x: number, y: number): number | [number, number, number] | null {
    const p = this._panelById(panelId);
    if (!p) return null;
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    if (ix < 0 || iy < 0 || ix >= p.meta.width || iy >= p.meta.height) return null;
    const idx = iy * p.meta.width + ix;
    if (p.meta.kind === 'rgb') {
      const src = p.source as Uint8Array;
      const base = idx * 4;
      return [src[base], src[base + 1], src[base + 2]];
    }
    return (p.source as Float32Array)[idx];
  }

  panelAt(canvasX: number, canvasY: number): { panelId: number; localX: number; localY: number } | null {
    for (const p of this.panels) {
      const { x: px, y: py, w, h } = p.layout;
      if (canvasX >= px && canvasX < px + w && canvasY >= py && canvasY < py + h) {
        const source = this._sourceWindow(p);
        const lx = source.x + ((canvasX - px) / w) * source.w;
        const ly = source.y + ((canvasY - py) / h) * source.h;
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
  }

  resizeCanvas(width: number, height: number): void {
    if (!this.canvas) return;
    this.canvas.width = width;
    this.canvas.height = height;
  }

  private _layoutPanels(panels: PanelMeta[], grid?: [number, number]): void {
    const rows = grid?.[0] ?? this._gridDims(panels.length).rows;
    const cols = grid?.[1] ?? this._gridDims(panels.length).cols;
    const maxW = Math.max(...panels.map((p) => p.width));
    const maxH = Math.max(...panels.map((p) => p.height));
    const cellW = maxW + this.pad * 2;
    const cellH = maxH + this.titleH + this.pad * 2;
    panels.forEach((meta, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      const x = col * cellW + this.pad;
      const y = row * cellH + this.titleH + this.pad;
      const w = meta.width;
      const h = meta.height;
      this.panels[i].layout = { x, y, w, h };
    });
    const totalW = cols * cellW;
    const totalH = rows * cellH;
    this.resizeCanvas(Math.max(320, totalW), Math.max(200, totalH));
  }

  private _gridDims(n: number): { rows: number; cols: number } {
    const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
    const rows = Math.max(1, Math.ceil(n / cols));
    return { rows, cols };
  }

  private _refreshPanel(panelIdx: number): void {
    const p = this.panels[panelIdx];
    if (!p || !p.source.length) return;
    const expected =
      p.meta.kind === 'rgb'
        ? p.meta.width * p.meta.height * 4
        : p.meta.width * p.meta.height;
    if (p.source.length < expected) return;
    if (p.meta.kind === 'rgb') {
      const src = p.source as Uint8Array;
      const rgba = new ImageData(p.meta.width, p.meta.height);
      rgba.data.set(src.subarray(0, p.meta.width * p.meta.height * 4));
      p.rgba = rgba;
      return;
    }
    p.rgba = recolorScalar(
      p.source as Float32Array,
      p.meta.width,
      p.meta.height,
      p.lut,
      p.lo,
      p.hi,
    );
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
