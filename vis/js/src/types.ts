export type PanelKind = 'scalar' | 'rgb';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PanelMeta {
  id: number;
  title: string;
  kind: PanelKind;
  width: number;
  height: number;
  sourceWidth?: number;
  sourceHeight?: number;
  factor?: number;
  sentBytes?: number;
  fullBytes?: number;
  cmap: string;
  clim: [number | null, number | null];
  layout: Rect;
  cbar?: Rect | null;
}

export interface ViewState {
  scale: number;
  tx: number;
  ty: number;
}

export interface CursorState {
  panel?: number;
  x?: number;
  y?: number;
  values?: Array<{ title: string; value: string }>;
  text?: string;
}

/** Global display options (not selection-scoped). */
export interface DrawOptions {
  cbar: boolean;
  ticks: string;
}

/** Per-panel toggleable options (selection-scoped in the toolbar). */
export interface PanelDrawOptions {
  showGrid: boolean;
}

export const DEFAULT_PANEL_DRAW_OPTIONS: PanelDrawOptions = { showGrid: false };

export interface AnyModel {
  get<T = unknown>(key: string): T;
  set(key: string, value: unknown): void;
  on(event: string, callback: () => void): void;
}
