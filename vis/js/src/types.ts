export type PanelKind = 'scalar' | 'rgb';

export interface PanelMeta {
  id: number;
  title: string;
  kind: PanelKind;
  width: number;
  height: number;
  cmap: string;
  clim: [number | null, number | null];
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

export interface AnyModel {
  get<T = unknown>(key: string): T;
  set(key: string, value: unknown): void;
  on(event: string, callback: () => void): void;
}
