/** Map scalar value through LUT and clim into RGBA bytes. */
export function scalarToRgba(
  value: number,
  lut: Uint8Array,
  lo: number,
  hi: number,
  out: Uint8ClampedArray,
  offset: number,
): void {
  if (!Number.isFinite(value)) {
    out[offset] = 0;
    out[offset + 1] = 0;
    out[offset + 2] = 0;
    out[offset + 3] = 0;
    return;
  }
  const span = hi - lo || 1;
  let t = (value - lo) / span;
  if (t < 0) t = 0;
  if (t > 1) t = 1;
  const idx = Math.min(255, Math.floor(t * 255)) * 4;
  out[offset] = lut[idx];
  out[offset + 1] = lut[idx + 1];
  out[offset + 2] = lut[idx + 2];
  out[offset + 3] = 255;
}

export function recolorScalar(
  source: Float32Array,
  width: number,
  height: number,
  lut: Uint8Array,
  lo: number,
  hi: number,
): ImageData {
  const imageData = new ImageData(width, height);
  const out = imageData.data;
  for (let i = 0; i < source.length; i++) {
    scalarToRgba(source[i], lut, lo, hi, out, i * 4);
  }
  return imageData;
}
