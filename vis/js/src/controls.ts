import type { GridModel } from './model';
import { resetView } from './grid';
import type { Renderer } from './renderer/Renderer';

export function buildToolbar(
  root: HTMLElement,
  model: GridModel,
  renderer: Renderer,
  onRedraw: () => void,
): void {
  const bar = document.createElement('div');
  bar.className = 'iad-imgrid__toolbar';

  const cmapNames = Object.keys(model.luts);
  if (cmapNames.length) {
    const label = document.createElement('label');
    label.textContent = 'cmap ';
    const select = document.createElement('select');
    cmapNames.forEach((name) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
    select.value = model.cmaps[0] ?? cmapNames[0];
    select.addEventListener('change', () => {
      const lut = model.luts[select.value];
      if (!lut) return;
      model.panels.forEach((p) => renderer.setColormap(p.id, lut));
      onRedraw();
    });
    label.appendChild(select);
    bar.appendChild(label);
  }

  const climLabel = document.createElement('label');
  climLabel.textContent = 'clim ';
  const climMin = document.createElement('input');
  climMin.type = 'number';
  climMin.step = 'any';
  const climMax = document.createElement('input');
  climMax.type = 'number';
  climMax.step = 'any';
  const p0 = model.panels[0];
  if (p0) {
    climMin.value = String(p0.clim[0] ?? 0);
    climMax.value = String(p0.clim[1] ?? 1);
  }
  const applyClim = () => {
    const lo = parseFloat(climMin.value);
    const hi = parseFloat(climMax.value);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
    model.panels.forEach((p) => renderer.setClim(p.id, lo, hi));
    onRedraw();
  };
  climMin.addEventListener('change', applyClim);
  climMax.addEventListener('change', applyClim);
  climLabel.append(climMin, document.createTextNode(' – '), climMax);
  bar.appendChild(climLabel);

  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = 'Reset view';
  resetBtn.addEventListener('click', () => resetView(model, renderer, onRedraw));
  bar.appendChild(resetBtn);

  root.appendChild(bar);
}
