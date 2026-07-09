export function displayPoint(canvas: HTMLCanvasElement, ev: MouseEvent | WheelEvent): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ev.clientX - rect.left,
    y: ev.clientY - rect.top,
  };
}

export interface DisplayMetrics {
  displayScale: number;
  dpr: number;
  displayWidth: number;
  displayHeight: number;
}

export function syncHiDpiCanvas(
  canvas: HTMLCanvasElement,
  refWidth: number,
  refHeight: number,
): DisplayMetrics {
  const rect = canvas.getBoundingClientRect();
  let displayWidth = rect.width;
  if (displayWidth < 1) {
    displayWidth = canvas.parentElement?.getBoundingClientRect().width ?? refWidth;
  }
  displayWidth = Math.max(1, displayWidth);
  const displayHeight = displayWidth * (refHeight / refWidth);
  const dpr = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(displayWidth * dpr);
  const pixelHeight = Math.round(displayHeight * dpr);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  if (!canvas.style.aspectRatio) {
    canvas.style.aspectRatio = `${refWidth} / ${refHeight}`;
  }
  return {
    displayScale: displayWidth / refWidth,
    dpr,
    displayWidth,
    displayHeight,
  };
}
