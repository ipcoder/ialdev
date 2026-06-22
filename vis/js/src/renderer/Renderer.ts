import type { PanelMeta, ViewState } from '../types';

export interface Renderer {
  init(canvas: HTMLCanvasElement, panels: PanelMeta[]): void;
  setColormap(panelId: number, lut: Uint8Array): void;
  setClim(panelId: number, lo: number, hi: number): void;
  setView(view: ViewState): void;
  draw(): void;
  pixelValue(panelId: number, x: number, y: number): number | [number, number, number] | null;
  dispose(): void;
  panelAt(canvasX: number, canvasY: number): { panelId: number; localX: number; localY: number } | null;
  imageCoords(panelId: number, localX: number, localY: number): { x: number; y: number } | null;
}
