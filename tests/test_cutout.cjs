const assert = require('node:assert/strict');
const { smoothstep, looksInverted, applyMask } = require('../cutout.js');

// A 20x10 frame with a "person" in the middle columns.
const W = 20, H = 10;
const person = new Float32Array(W * H);
for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) person[y * W + x] = x >= 6 && x < 14 ? 0.95 : 0.05;
const flipped = person.map(v => 1 - v);

assert.equal(smoothstep(0.3, 0.7, 0.1), 0);
assert.equal(smoothstep(0.3, 0.7, 0.9), 1);
assert.ok(Math.abs(smoothstep(0.3, 0.7, 0.5) - 0.5) < 1e-9);

assert.equal(looksInverted(person, W, H), false, 'person-high mask is not inverted');
assert.equal(looksInverted(flipped, W, H), true, 'background-high mask is inverted');
assert.equal(looksInverted(new Float32Array(W * H).fill(0.5), W, H), null, 'a flat mask is ambiguous');
assert.equal(looksInverted(new Float32Array(W * H).fill(0), W, H), null, 'an empty frame is ambiguous');

const pixels = new Uint8ClampedArray(W * H * 4).fill(200);
applyMask(pixels, person, false);
assert.equal(pixels[(5 * W + 10) * 4 + 3], 255, 'person pixels are opaque');
assert.equal(pixels[(5 * W + 1) * 4 + 3], 0, 'room pixels are transparent');
assert.equal(pixels[(5 * W + 10) * 4], 200, 'colours are untouched');

const second = new Uint8ClampedArray(W * H * 4).fill(200);
applyMask(second, flipped, true);
assert.deepEqual([...second], [...pixels], 'an inverted mask gives the same result once corrected');

console.log('PASS: cut-out mask maths, polarity detection and soft edges.');
