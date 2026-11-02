const assert = require('node:assert/strict');
const { MAX, IDEAS, MOODS, COLORS, DETAILS, clean, compose, suggest } = require('../promptkit.js');

// Joins the answers into one clear prompt.
assert.equal(compose({ idea: 'a smiling cloud' }), 'a smiling cloud');
assert.equal(compose({ idea: 'a smiling cloud', mood: 'cozy', color: 'pastel', details: 'wearing a tiny hat' }),
  'a smiling cloud, cozy and warm mood, soft pastel colors, wearing a tiny hat');
assert.equal(compose({ idea: 'a dragon', color: 'neon' }), 'a dragon, neon pink and electric blue colors', 'unanswered questions are skipped');
assert.equal(compose({ idea: 'a dragon', mood: 'nope', color: 'nope' }), 'a dragon', 'unknown choices are ignored');

// A mood or color the idea already says is not repeated; unrelated words are left alone.
assert.equal(compose({ idea: 'a cozy attic', mood: 'cozy', color: 'warm' }), 'a cozy attic, warm orange and pink colors');
assert.equal(compose({ idea: 'a neon street', color: 'neon', mood: 'epic' }), 'a neon street, epic and dramatic mood');
assert.equal(compose({ idea: 'a cool cat', color: 'cool' }), 'a cool cat, cool blue and teal colors', 'a word that only sounds similar is kept');
assert.equal(compose({ idea: 'a Rainbow unicorn', color: 'rainbow' }), 'a Rainbow unicorn');

// Nothing to write about yet.
for (const idea of ['', '   ', null, undefined, '...', '\n\t']) assert.equal(compose({ idea, mood: 'cozy' }), '', JSON.stringify(idea));
assert.equal(compose(), '');

// Tidying: control characters, spacing and trailing punctuation.
assert.equal(clean('  a   cat\u0000 \u0007on\na  roof!!! '), 'a cat on a roof');
assert.equal(compose({ idea: 'a cat.', details: 'a hat;' }), 'a cat, a hat');
assert.ok(!/[\u0000-\u001f]/.test(compose({ idea: 'bad\u0001 idea', details: 'x\u0002' })));

// The server accepts at most 200 characters, so optional parts drop first, then the idea is trimmed at a word.
const long = 'a very detailed picture of a ' + 'tiny friendly dragon sitting on a hill '.repeat(8);
const everything = { idea: 'a lighthouse standing proudly on a tall rocky cliff above a calm sea at dawn with gulls', mood: 'epic', color: 'moody', details: 'a soft glow and many tiny details everywhere' };
const squeezed = compose(everything);
assert.ok(squeezed.length <= MAX && squeezed.startsWith('a lighthouse'), squeezed);
assert.ok(compose({ idea: 'a lighthouse', mood: 'epic', color: 'moody', details: 'x'.repeat(190) }) === 'a lighthouse, epic and dramatic mood, dark moody colors with glowing accents', 'extras are dropped from the end first');
const trimmed = compose({ idea: long, mood: 'cozy' });
assert.ok(trimmed.length <= MAX && trimmed.length > 100 && !trimmed.endsWith(' ') && long.startsWith(trimmed), 'a too-long idea is cut at a word boundary');

// Curated lists are tidy and family-friendly, and every combination fits.
for (const [placement, list] of Object.entries(IDEAS)) {
  assert.ok(list.length >= 5, placement); assert.equal(new Set(list).size, list.length, 'no duplicate ideas');
  for (const idea of list) for (const m of MOODS) for (const c of COLORS) assert.ok(compose({ idea, mood: m.id, color: c.id, details: DETAILS[0] }).length <= MAX);
}
assert.equal(new Set([...MOODS, ...COLORS].map(x => x.id)).size, MOODS.length + COLORS.length - (MOODS.filter(m => COLORS.some(c => c.id === m.id)).length), 'ids are unique within each list');
for (const item of [...MOODS, ...COLORS]) assert.ok(item.id && item.label && item.phrase && !/undefined|null/.test(item.phrase));

// "Surprise me": always usable, depends on where the picture will go, and is predictable under a fixed random source.
for (const placement of ['object', 'backdrop', 'full', 'unknown', undefined]) {
  const s = suggest(placement, () => 0.5);
  assert.ok(s.idea && MOODS.some(m => m.id === s.mood) && COLORS.some(c => c.id === s.color));
}
assert.ok(IDEAS.full.includes(suggest('full', () => 0).idea)); assert.ok(IDEAS.backdrop.includes(suggest('backdrop', () => 0.99).idea));
assert.deepEqual(suggest('object', () => 0), { idea: IDEAS.object[0], mood: MOODS[0].id, color: COLORS[0].id });
assert.deepEqual(suggest('object', () => 0.999999), { idea: IDEAS.object.at(-1), mood: MOODS.at(-1).id, color: COLORS.at(-1).id }, 'the last item is reachable');
assert.ok(new Set(Array.from({ length: 40 }, (_, i) => suggest('object', () => i / 40).idea)).size > 4, 'it gives variety');

console.log('PASS: prompt helper composes, tidies, caps length, and suggests ideas.');
