'use strict';
// Prompt helper: turns a few simple answers into a clear picture prompt, for people who don't know how to prompt.
// Plain data and string work only: it makes no AI call, so it is free and instant. The finished prompt is moderated
// by the server like anything typed by hand.
(function (root) {
  const MAX = 200;

  const IDEAS = {
    object: ['a smiling cloud wearing sunglasses', 'a tiny dragon sleeping on a pile of coins', 'a happy cat astronaut floating', 'a friendly robot holding a flower',
      'a glowing jellyfish lantern', 'a cozy mushroom house with a round door', 'a sleepy moon wearing a nightcap', 'a treasure chest overflowing with stars'],
    backdrop: ['a row of cozy townhouses with lit windows', 'a giant glowing mushroom', 'a mossy stone bridge', 'a cluster of floating lanterns',
      'a pine tree covered in string lights', 'a tall lighthouse on a cliff'],
    full: ['a cozy attic gaming room with string lights', 'a rainy neon street at night', 'a sunset beach with palm trees', 'a magical forest full of fireflies',
      'a space station window looking out at a colorful nebula', 'a snowy mountain cabin at dusk'],
  };
  const MOODS = [
    { id: 'cozy', label: 'Cozy', phrase: 'cozy and warm mood', said: /\bcozy\b/i }, { id: 'funny', label: 'Funny', phrase: 'playful and funny mood', said: /\bfunn(y|ier)\b|\bplayful\b/i },
    { id: 'spooky', label: 'Spooky-cute', phrase: 'a little spooky but friendly mood', said: /\bspook/i }, { id: 'epic', label: 'Epic', phrase: 'epic and dramatic mood', said: /\bepic\b/i },
    { id: 'dreamy', label: 'Dreamy', phrase: 'dreamy and calm mood', said: /\bdream/i }, { id: 'energetic', label: 'Energetic', phrase: 'bright and energetic mood', said: /\benergetic\b/i },
  ];
  const COLORS = [
    { id: 'warm', label: 'Warm sunset', phrase: 'warm orange and pink colors' }, { id: 'cool', label: 'Cool ocean', phrase: 'cool blue and teal colors' },
    { id: 'neon', label: 'Neon', phrase: 'neon pink and electric blue colors', said: /\bneon\b/i }, { id: 'pastel', label: 'Pastel', phrase: 'soft pastel colors', said: /\bpastel\b/i },
    { id: 'moody', label: 'Dark and moody', phrase: 'dark moody colors with glowing accents' }, { id: 'rainbow', label: 'Rainbow', phrase: 'bright rainbow colors', said: /\brainbow\b/i },
  ];
  const DETAILS = ['tiny sparkles', 'a soft glow', 'wearing a little hat', 'rain and reflections', 'lots of tiny details'];

  // Remove control characters, squash spaces, and drop trailing punctuation so pieces join cleanly with commas.
  function clean(text) {
    return String(text == null ? '' : text).replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().replace(/[.,;:!?\s]+$/, '');
  }
  const find = (list, id) => list.find(x => x.id === id);

  // Builds the prompt. If it is too long, optional parts are dropped from the end first, and the idea is cut last.
  function compose({ idea, mood, color, details } = {}) {
    const main = clean(idea);
    if (!main) return '';
    // Skip a mood or color the idea already says ("a cozy attic" + Cozy would repeat itself).
    const phrase = item => item && !(item.said && item.said.test(main)) ? item.phrase : '';
    const optional = [phrase(find(MOODS, mood)), phrase(find(COLORS, color)), clean(details)].filter(Boolean);
    for (let keep = optional.length; keep >= 0; keep--) {
      const text = [main, ...optional.slice(0, keep)].join(', ');
      if (text.length <= MAX) return text;
    }
    const cut = main.slice(0, MAX - 1), space = cut.lastIndexOf(' ');
    return clean(space > 40 ? cut.slice(0, space) : cut);
  }

  // A random starting point for people who have no idea yet. `rng` is injectable so tests are predictable.
  function suggest(placement, rng = Math.random) {
    const pick = list => list[Math.min(list.length - 1, Math.floor(rng() * list.length))];
    const pool = IDEAS[placement] || IDEAS.object;
    return { idea: pick(pool), mood: pick(MOODS).id, color: pick(COLORS).id };
  }

  const api = { MAX, IDEAS, MOODS, COLORS, DETAILS, clean, compose, suggest };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LittleWorldsPrompts = api;
})(typeof window !== 'undefined' ? window : globalThis);
