'use strict';
// Helpers for the streamer's "show only me" webcam preview. The segmentation model gives a mask with one
// number per pixel for how likely it is to be the person; these turn that into transparency.
(function (root) {
  const clamp01 = v => Math.min(1, Math.max(0, v));
  function smoothstep(lo, hi, v) { const t = clamp01((v - lo) / (hi - lo)); return t * t * (3 - 2 * t); }

  function regionMean(mask, w, h, x0, y0, x1, y1) {
    let sum = 0, count = 0;
    for (let y = Math.max(0, Math.floor(y0)); y < Math.min(h, Math.ceil(y1)); y += 2)
      for (let x = Math.max(0, Math.floor(x0)); x < Math.min(w, Math.ceil(x1)); x += 2) { sum += mask[y * w + x]; count++; }
    return count ? sum / count : 0;
  }

  // People usually sit in the middle of the frame and the room is at the sides. If the middle looks like "background"
  // and the sides look like "person", the mask points the wrong way. Returns true / false, or null when unsure.
  function looksInverted(mask, w, h) {
    const middle = regionMean(mask, w, h, w * 0.3, h * 0.25, w * 0.7, h);
    const sides = (regionMean(mask, w, h, 0, 0, w * 0.15, h) + regionMean(mask, w, h, w * 0.85, 0, w, h)) / 2;
    if (Math.abs(middle - sides) < 0.15) return null;
    return middle < sides;
  }

  // Writes the alpha channel of an RGBA pixel array from a w*h mask. Soft edges avoid a harsh cut-out line.
  function applyMask(pixels, mask, invert) {
    for (let i = 0; i < mask.length; i++) {
      const value = invert ? 1 - mask[i] : mask[i];
      pixels[i * 4 + 3] = Math.round(255 * smoothstep(0.3, 0.7, value));
    }
  }

  const api = { smoothstep, regionMean, looksInverted, applyMask };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LittleWorldsCutout = api;
})(typeof window !== 'undefined' ? window : globalThis);
