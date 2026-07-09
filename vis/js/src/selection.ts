/** Shared panel-selection state used by the toolbar dropdown and canvas clicks. */
export class PanelSelection {
  private ids = new Set<number>();
  private readonly allIds: number[];
  private listeners: Array<() => void> = [];

  constructor(allIds: number[]) {
    this.allIds = [...allIds];
  }

  /** Explicitly selected ids (empty when nothing is selected). */
  get explicit(): number[] {
    return [...this.ids];
  }

  /** Panels to act on: the explicit set, or all panels when none are selected. */
  get targeting(): number[] {
    return this.ids.size ? [...this.ids] : [...this.allIds];
  }

  isSelected(id: number): boolean {
    return this.ids.has(id);
  }

  set(ids: number[]): void {
    this.ids = new Set(ids);
    this.notify();
  }

  toggle(id: number): void {
    if (this.ids.has(id)) {
      this.ids.delete(id);
    } else {
      this.ids.add(id);
    }
    this.notify();
  }

  onChange(cb: () => void): void {
    this.listeners.push(cb);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }
}
