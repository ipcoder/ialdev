import type { GridModel } from './model';
import { resetView } from './grid';
import type { Renderer } from './renderer/Renderer';
import type { PanelSelection } from './selection';

export interface ToolbarHandle {
  cleanup: () => void;
  info: HTMLElement;
  dataReadout: HTMLElement;
  bar: HTMLElement;
  sync: () => void;
}

function panelLabel(model: GridModel, id: number): string {
  const panel = model.panels.find((p) => p.id === id);
  return panel?.title || `Panel ${id}`;
}

function firstTargetPanel(model: GridModel, selection: PanelSelection) {
  const id = selection.targeting[0];
  return model.panels.find((p) => p.id === id);
}

function applyToTargets(selection: PanelSelection, fn: (id: number) => void): void {
  selection.targeting.forEach(fn);
}

/** Single-line panel selector that expands a checkbox menu on click. */
function buildPanelDropdown(
  model: GridModel,
  selection: PanelSelection,
): { el: HTMLElement; cleanup: () => void } {
  const wrap = document.createElement('div');
  wrap.className = 'iad-imgrid__dropdown';

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'iad-imgrid__dropdown__button';
  button.title =
    'Select panels to apply cmap/clim to (or Ctrl+Alt+click panels)';

  const menu = document.createElement('div');
  menu.className = 'iad-imgrid__dropdown__menu';
  menu.hidden = true;

  const checks = new Map<number, HTMLInputElement>();
  model.panels.forEach((p) => {
    const item = document.createElement('label');
    item.className = 'iad-imgrid__dropdown__item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = String(p.id);
    cb.addEventListener('change', () => {
      const ids = model.panels
        .filter((pp) => checks.get(pp.id)?.checked)
        .map((pp) => pp.id);
      selection.set(ids);
    });
    checks.set(p.id, cb);
    item.append(cb, document.createTextNode(' ' + (p.title || `Panel ${p.id}`)));
    menu.appendChild(item);
  });

  const sync = () => {
    const sel = selection.explicit;
    model.panels.forEach((p) => {
      const cb = checks.get(p.id);
      if (cb) cb.checked = selection.isSelected(p.id);
    });
    button.textContent =
      sel.length === 0
        ? 'All panels'
        : sel.length === 1
          ? panelLabel(model, sel[0])
          : `${sel.length} panels`;
  };
  selection.onChange(sync);
  sync();

  button.addEventListener('click', (ev) => {
    ev.stopPropagation();
    menu.hidden = !menu.hidden;
  });
  menu.addEventListener('click', (ev) => {
    ev.stopPropagation();
  });
  const onDocClick = (ev: MouseEvent) => {
    if (!wrap.contains(ev.target as Node)) menu.hidden = true;
  };
  document.addEventListener('click', onDocClick);

  wrap.append(button, menu);
  return { el: wrap, cleanup: () => document.removeEventListener('click', onDocClick) };
}

function formatMpx(pixels: number): string {
  const mpx = pixels / 1_000_000;
  if (mpx >= 10) return mpx.toFixed(1);
  if (mpx >= 1) return mpx.toFixed(2);
  return mpx.toFixed(3);
}

function formatDataReadout(model: GridModel): string {
  const sentBytes = model.dataSentBytes;
  const sentPixels = model.dataSentPixels;
  const fullPixels = model.dataFullPixels;
  if (sentBytes <= 0) return '';
  const mb = sentBytes / 1_000_000;
  const mbStr = mb >= 10 ? mb.toFixed(1) : mb.toFixed(2);
  if (fullPixels > 0) {
    return `${mbStr} MB (${formatMpx(sentPixels)}/${formatMpx(fullPixels)} Mpx)`;
  }
  return `${mbStr} MB`;
}

function syncDataReadout(model: GridModel, el: HTMLElement): void {
  el.textContent = formatDataReadout(model);
  const over = model.dataOverBudget;
  el.classList.toggle('iad-imgrid__data-readout--over-budget', over);
  if (over) {
    el.title =
      'Sent pixel budget exceeded; explicit max_zoom/downsample takes precedence over max_pixels';
  } else {
    el.removeAttribute('title');
  }
}

export function buildToolbar(
  root: HTMLElement,
  model: GridModel,
  renderer: Renderer,
  onRedraw: () => void,
  selection: PanelSelection,
): ToolbarHandle {
  const bar = document.createElement('div');
  bar.className = 'iad-imgrid__toolbar';

  const dataReadout = document.createElement('div');
  dataReadout.className = 'iad-imgrid__data-readout';
  syncDataReadout(model, dataReadout);
  bar.appendChild(dataReadout);

  const info = document.createElement('div');
  info.className = 'iad-imgrid__info';
  bar.appendChild(info);

  const controls = document.createElement('div');
  controls.className = 'iad-imgrid__controls';
  controls.hidden = true;

  const panelCmaps = new Map<number, string>();
  model.panels.forEach((p) => panelCmaps.set(p.id, p.cmap));

  const targetLabel = document.createElement('label');
  targetLabel.className = 'iad-imgrid__panel-select';
  targetLabel.textContent = 'panel ';
  const dropdown = buildPanelDropdown(model, selection);
  targetLabel.appendChild(dropdown.el);
  controls.appendChild(targetLabel);

  const cmapNames = Object.keys(model.luts);
  let cmapSelect: HTMLSelectElement | null = null;
  if (cmapNames.length) {
    const label = document.createElement('label');
    label.textContent = 'cmap ';
    cmapSelect = document.createElement('select');
    cmapSelect.title = 'Colormap for selected panels';
    cmapNames.forEach((name) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      cmapSelect!.appendChild(opt);
    });
    cmapSelect.value = model.cmaps[0] ?? cmapNames[0];
    cmapSelect.addEventListener('change', () => {
      const lut = model.luts[cmapSelect!.value];
      if (!lut) return;
      applyToTargets(selection, (id) => {
        panelCmaps.set(id, cmapSelect!.value);
        renderer.setColormap(id, lut);
      });
      onRedraw();
    });
    label.appendChild(cmapSelect);
    controls.appendChild(label);
  }

  const climLabel = document.createElement('label');
  climLabel.textContent = 'clim ';
  const climMin = document.createElement('input');
  climMin.type = 'number';
  climMin.step = 'any';
  climMin.title = 'Color-scale min';
  const climMax = document.createElement('input');
  climMax.type = 'number';
  climMax.step = 'any';
  climMax.title = 'Color-scale max';
  const refreshClimInputs = () => {
    const panel = firstTargetPanel(model, selection);
    if (!panel) return;
    climMin.value = String(panel.clim[0] ?? 0);
    climMax.value = String(panel.clim[1] ?? 1);
  };
  refreshClimInputs();
  const applyClim = () => {
    const lo = parseFloat(climMin.value);
    const hi = parseFloat(climMax.value);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
    applyToTargets(selection, (id) => renderer.setClim(id, lo, hi));
    onRedraw();
  };
  climMin.addEventListener('change', applyClim);
  climMax.addEventListener('change', applyClim);
  climLabel.append(climMin, document.createTextNode(' – '), climMax);
  if (model.adjClim) {
    controls.appendChild(climLabel);
  }

  const gridBtn = document.createElement('button');
  gridBtn.type = 'button';
  gridBtn.textContent = '\u25A6';
  gridBtn.title = 'Toggle grid lines';

  const syncGridBtn = () => {
    const targets = selection.targeting;
    const allOn =
      targets.length > 0 &&
      targets.every((id) => renderer.getPanelOptions(id).showGrid);
    gridBtn.setAttribute('aria-pressed', String(allOn));
  };

  gridBtn.addEventListener('click', () => {
    const targets = selection.targeting;
    const allOn = targets.every((id) => renderer.getPanelOptions(id).showGrid);
    const next = !allOn;
    applyToTargets(selection, (id) =>
      renderer.setPanelOptions(id, { showGrid: next }),
    );
    syncGridBtn();
    onRedraw();
  });
  controls.appendChild(gridBtn);

  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = '\u2302';
  resetBtn.title = 'Reset zoom/pan to fit';
  resetBtn.addEventListener('click', () => resetView(model, renderer, onRedraw));
  controls.appendChild(resetBtn);

  bar.appendChild(controls);

  const collapseBtn = document.createElement('button');
  collapseBtn.type = 'button';
  collapseBtn.className = 'iad-imgrid__collapse-toggle';
  collapseBtn.textContent = '\u25BA';
  collapseBtn.title = 'Show controls';
  collapseBtn.setAttribute('aria-expanded', 'false');

  const syncCollapseBtn = () => {
    const expanded = !controls.hidden;
    collapseBtn.textContent = expanded ? '\u25C4' : '\u25BA';
    collapseBtn.title = expanded ? 'Hide controls' : 'Show controls';
    collapseBtn.setAttribute('aria-expanded', String(expanded));
  };

  collapseBtn.addEventListener('click', () => {
    controls.hidden = !controls.hidden;
    syncCollapseBtn();
  });
  bar.appendChild(collapseBtn);

  const sync = () => {
    syncDataReadout(model, dataReadout);
    refreshClimInputs();
    const panel = firstTargetPanel(model, selection);
    if (cmapSelect && panel) {
      const name = panelCmaps.get(panel.id) ?? panel.cmap;
      if (name && cmapSelect.querySelector(`option[value="${name}"]`)) {
        cmapSelect.value = name;
      }
    }
    syncGridBtn();
  };

  selection.onChange(sync);
  syncGridBtn();

  root.appendChild(bar);

  return {
    cleanup: dropdown.cleanup,
    info,
    dataReadout,
    bar,
    sync,
  };
}
