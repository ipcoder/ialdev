import type { AnyModel, CursorState, DrawOptions, PanelMeta, ViewState } from './types';

function toArrayBuffer(value: unknown): ArrayBuffer | null {
  if (value instanceof ArrayBuffer) return value;
  if (ArrayBuffer.isView(value)) {
    return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength);
  }
  return null;
}

function decodePanelBuffer(
  buf: unknown,
  panel: PanelMeta,
): Float32Array | Uint8Array {
  if (buf instanceof Float32Array) {
    return buf;
  }
  if (buf instanceof Uint8Array) {
    return buf;
  }
  const ab = toArrayBuffer(buf);
  if (!ab) {
    if (buf && typeof buf === 'object' && 'data' in buf) {
      const data = (buf as { data: ArrayLike<number> }).data;
      if (panel.kind === 'rgb') {
        return new Uint8Array(Array.from(data as ArrayLike<number>));
      }
      return new Float32Array(Array.from(data as ArrayLike<number>));
    }
    return panel.kind === 'rgb' ? new Uint8Array(0) : new Float32Array(0);
  }
  if (panel.kind === 'rgb') {
    return new Uint8Array(ab, 0, panel.width * panel.height * 4);
  }
  return new Float32Array(ab, 0, panel.width * panel.height);
}

function decodeLut(value: unknown): Uint8Array | null {
  if (value instanceof Uint8Array) return value;
  const ab = toArrayBuffer(value);
  if (ab) return new Uint8Array(ab, 0, 256 * 4);
  if (Array.isArray(value)) {
    if (value.length === 256 && Array.isArray(value[0])) {
      return new Uint8Array(value.flat() as number[]);
    }
    if (value.length === 256 * 4) {
      return new Uint8Array(value as number[]);
    }
  }
  if (value && typeof value === 'object' && 'data' in value) {
    return new Uint8Array((value as { data: number[] }).data);
  }
  return null;
}

export class GridModel {
  constructor(private model: AnyModel) {}

  get panels(): PanelMeta[] {
    return this.model.get<PanelMeta[]>('panels') ?? [];
  }

  get buffers(): Array<Float32Array | Uint8Array> {
    const raw = this.model.get<unknown[]>('buffers') ?? [];
    return this.panels.map((panel, i) => decodePanelBuffer(raw[i], panel));
  }

  get luts(): Record<string, Uint8Array> {
    const raw = this.model.get<Record<string, unknown>>('luts') ?? {};
    const out: Record<string, Uint8Array> = {};
    for (const [name, val] of Object.entries(raw)) {
      const lut = decodeLut(val);
      if (lut) out[name] = lut;
    }
    return out;
  }

  get cmaps(): string[] {
    return this.model.get<string[]>('cmaps') ?? [];
  }

  get cbar(): boolean {
    return this.model.get<boolean>('cbar') ?? true;
  }

  get ticks(): string {
    return this.model.get<string>('ticks') ?? 'xy';
  }

  get showGrid(): boolean {
    return this.model.get<boolean>('show_grid') ?? false;
  }

  setShowGrid(value: boolean): void {
    this.model.set('show_grid', value);
  }

  get drawOptions(): DrawOptions {
    return {
      cbar: this.cbar,
      ticks: this.ticks,
    };
  }

  get adjClim(): boolean {
    return this.model.get<boolean>('adj_clim') ?? false;
  }

  get canvasWidth(): number {
    return this.model.get<number>('canvas_width') ?? 320;
  }

  get canvasHeight(): number {
    return this.model.get<number>('canvas_height') ?? 200;
  }

  get dataSentBytes(): number {
    return this.model.get<number>('data_sent_bytes') ?? 0;
  }

  get dataFullBytes(): number {
    return this.model.get<number>('data_full_bytes') ?? 0;
  }

  get dataSentPixels(): number {
    return this.model.get<number>('data_sent_pixels') ?? 0;
  }

  get dataFullPixels(): number {
    return this.model.get<number>('data_full_pixels') ?? 0;
  }

  get dataOverBudget(): boolean {
    return this.model.get<boolean>('data_over_budget') ?? false;
  }

  get inspectEnabled(): boolean {
    return this.model.get<boolean>('inspect_enabled') ?? true;
  }

  get windowTitle(): string {
    return this.model.get<string>('window_title') ?? '';
  }

  get view(): ViewState {
    return this.model.get<ViewState>('view') ?? { scale: 1, tx: 0, ty: 0 };
  }

  setView(view: ViewState): void {
    this.model.set('view', view);
  }

  setCursor(cursor: CursorState): void {
    this.model.set('cursor', cursor);
  }

  onChange(cb: () => void): void {
    this.model.on('change', cb);
  }

  onTrait(key: string, cb: () => void): void {
    this.model.on(`change:${key}`, cb);
  }

  onBuffersReady(cb: () => void): void {
    const trySync = () => {
      const ready = this.buffers.every((b, i) => {
        const panel = this.panels[i];
        if (!panel) return false;
        const expected = panel.kind === 'rgb' ? panel.width * panel.height * 4 : panel.width * panel.height;
        return b.length >= expected;
      });
      if (ready) cb();
    };
    this.model.on('change:buffers', trySync);
    trySync();
  }
}
