import type { GridModel } from './model';
import type { Renderer } from './renderer/Renderer';
import type { PanelMeta } from './types';

export function formatReadout(
  x: number,
  y: number,
  panels: PanelMeta[],
  renderer: Renderer,
): string {
  const lines = [`(${y}, ${x})`];
  for (const panel of panels) {
    const val = renderer.pixelValue(panel.id, x, y);
    if (val === null) {
      lines.push(`${panel.title}: —`);
    } else if (Array.isArray(val)) {
      lines.push(`${panel.title}: (${val.join(', ')})`);
    } else if (typeof val === 'number') {
      lines.push(`${panel.title}: ${val.toFixed(4)}`);
    }
  }
  return lines.join('\n');
}

export function attachInspect(
  canvas: HTMLCanvasElement,
  readoutEl: HTMLElement,
  model: GridModel,
  renderer: Renderer,
): () => void {
  const onMove = (ev: MouseEvent) => {
    if (!model.inspectEnabled) return;
    const rect = canvas.getBoundingClientRect();
    const cx = ((ev.clientX - rect.left) / rect.width) * canvas.width;
    const cy = ((ev.clientY - rect.top) / rect.height) * canvas.height;
    const hit = renderer.panelAt(cx, cy);
    if (!hit) {
      readoutEl.textContent = '';
      model.setCursor({});
      return;
    }
    const { x, y } = renderer.imageCoords(hit.panelId, hit.localX, hit.localY);
    const text = formatReadout(x, y, model.panels, renderer);
    readoutEl.textContent = text;
    const values = model.panels.map((panel) => {
      const val = renderer.pixelValue(panel.id, x, y);
      let s = '—';
      if (Array.isArray(val)) s = `(${val.join(', ')})`;
      else if (typeof val === 'number') s = val.toFixed(4);
      return { title: panel.title, value: s };
    });
    model.setCursor({ panel: hit.panelId, x, y, values, text });
  };
  canvas.addEventListener('mousemove', onMove);
  return () => canvas.removeEventListener('mousemove', onMove);
}
