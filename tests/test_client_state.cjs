// Regression tests for streamer/viewer state handling in app.js, run in a fake page (no browser needed).
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');

function env({ getUserMedia, withoutPromptKit } = {}) {
  const elements = {}, requests = [], ctxCalls = { clear: 0 };
  const ctxStub = { clearRect() { ctxCalls.clear++; }, getImageData() { return { data: new Uint8ClampedArray([0, 0, 0, 255]) }; }, drawImage() {}, putImageData() {} };
  class Element {
    constructor(id = '') {
      this.id = id; this.dataset = {}; this.style = { setProperty() {} }; this.textContent = ''; this.value = ''; this.listeners = {}; this.children = [];
      this.hidden = false; this.disabled = false; this.checked = false; this.className = ''; this.attrs = {}; this.width = 600; this.height = 400;
      const set = this.classList = { values: new Set(), add: x => set.values.add(x), remove: x => set.values.delete(x), contains: x => set.values.has(x),
        toggle: (x, on) => { (on === undefined ? !set.values.has(x) : on) ? set.values.add(x) : set.values.delete(x); } };
    }
    addEventListener(type, fn) { this.listeners[type] = fn; }
    append(...nodes) { for (const node of nodes) { this.children.push(node); if (node && node.id) elements[node.id] = node; } }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    set innerHTML(value) { this.children = []; }
    setAttribute(k, v) { this.attrs[k] = v; } removeAttribute(k) { delete this.attrs[k]; } getContext() { return ctxStub; } focus() {} select() {}
    dispatchEvent(event) { const fn = this.listeners[event.type]; if (fn) fn(event); return true; }
    setPointerCapture() {} hasPointerCapture() { return true; } play() { return Promise.resolve(); } toDataURL() { return 'data:image/png;base64,AAAA'; }
    getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; }
  }
  const get = id => elements[id] || (elements[id] = new Element(id));
  const document = { title: 'Little Worlds — Studio', body: new Element('body'), getElementById: get, createElement: () => new Element(), querySelectorAll: () => [], addEventListener(type, fn) { (document.handlers[type] = document.handlers[type] || []).push(fn); }, handlers: {} };
  const context = { document, window: {}, navigator: { mediaDevices: getUserMedia ? { getUserMedia } : undefined }, performance: { now: () => 0 },
    cancelAnimationFrame() {}, requestAnimationFrame() { return 0 }, location: { origin: 'http://localhost:8765', search: '' }, URL, URLSearchParams, Image: class {},
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} }, setInterval() {}, setTimeout() { return 1; }, clearTimeout() {},
    Event: class { constructor(type) { this.type = type; } }, fetch: (url, options) => new Promise(resolve => requests.push({ url, options, resolve })), console: { error: (...a) => console.error('APP ERROR', ...a), log() {} } };
  vm.createContext(context); if (!withoutPromptKit) { vm.runInContext(fs.readFileSync('promptkit.js', 'utf8'), context); context.LittleWorldsPrompts = context.window.LittleWorldsPrompts; } vm.runInContext(fs.readFileSync('app.js', 'utf8'), context);
  const run = code => vm.runInContext(code, context);
  const tick = () => new Promise(r => setImmediate(r));
  const reply = async (index, data, ok = true) => { requests[index].resolve({ ok, json: async () => data }); await tick(); await tick(); };
  const walk = node => [node, ...node.children.flatMap(walk)];
  return { get, run, tick, reply, requests, walk, ctxCalls };
}

const obj = (id, extra = {}) => ({ id, creator: 'V', description: 'cat', behavior: 'still', x: 20, y: 30, image: 'data:image/png;base64,AA', scale: 1, placement: 'object', ...extra });
const streamerState = (approved, pending, chat = {}) => ({ approved, pending, paused: false, theme: 'neon', twitch: {}, chat_creation: { enabled: false, status: 'off', attempts: 0, limit: 10, ...chat }, viewer_url: '' });

(async () => {
  // 1. Previewing a waiting submission must not resize an already-live object that happened to be selected.
  {
    const { get, run, reply, requests, walk } = env();
    run("enter('streamer','ABC234','secret')");
    await reply(0, streamerState([obj(1)], [obj(2)], { attempts: 3, limit: 40 }));
    assert.match(get('chatCreationStatus').textContent, /3 of 40 generation attempts used/, 'the real AI limit is shown, not a fixed 10');
    assert.equal(run('sizeTarget().id'), 2, 'with nothing else chosen, the slider follows the waiting item that is being previewed');
    get('objects').children[0].listeners.pointerdown({ stopPropagation() {}, pointerId: 1 });
    assert.equal(run('sizeTarget().id'), 1, 'clicking a live object targets it');
    const preview = walk(get('queue')).find(n => /^Preview/.test(n.textContent));
    assert.ok(preview, 'a Preview button exists');
    preview.listeners.click();
    assert.equal(run('sizeTarget().id'), 2, 'Preview moves the slider to the waiting submission');
    assert.equal(run('selected'), null, 'the live object is no longer selected');
    get('objSize').value = '150'; get('objSize').listeners.input();
    assert.deepEqual(JSON.parse(run('JSON.stringify([approved[0].scale, pending[0].scale])')), [1, 1.5], 'only the previewed item changes size');
    get('objSize').listeners.change();
    const saved = requests[requests.length - 1];
    assert.match(saved.url, /\/placement\/2$/); assert.deepEqual(JSON.parse(saved.options.body), { scale: 1.5 });
    await reply(requests.length - 1, { ok: true });
    get('objects').children[0].listeners.pointerdown({ stopPropagation() {}, pointerId: 1 });
    assert.equal(run('sizeTarget().id'), 1, 'clicking the live object again retargets it');
  }

  // 2. Leaving clears a viewer's private drawing, words and AI preview, and ignores a reply that arrives afterwards.
  {
    const { get, run, reply, requests, tick, ctxCalls } = env();
    run("viewerToken='t'; aiArt=true; enter('viewer','ABC234')");
    await reply(0, { approved: [], paused: false, theme: 'neon' });
    get('creator').value = 'Alice'; get('description').value = 'my secret idea';
    run("previewArt='data:image/webp;base64,AAAA'; previewDesc='my secret idea'; previewMode='polish'; kind='backdrop'");
    get('leave').listeners.click();
    assert.equal(get('creator').value, ''); assert.equal(get('description').value, '');
    assert.equal(run('previewArt'), ''); assert.equal(get('previewImg').hidden, true); assert.equal(run('kind'), 'object');
    assert.ok(ctxCalls.clear >= 1, 'the drawing canvas is wiped');
    // A preview still in flight when the viewer leaves must not appear for the next person.
    run("viewerToken='t2'; aiArt=true; enter('viewer','ABC234')");
    await reply(requests.length - 1, { approved: [], paused: false, theme: 'neon' });
    get('creator').value = 'Bob'; get('description').value = 'a cloud';
    get('previewArt').listeners.click(); await tick();
    const inflight = requests.length - 1; assert.match(requests[inflight].url, /\/preview$/);
    get('leave').listeners.click();
    await reply(inflight, { art: 'data:image/webp;base64,SECRET', previews_left: 3 });
    assert.equal(run('previewArt'), '', 'a late AI preview from the departed session is discarded');
    assert.equal(get('previewImg').hidden, true);
  }

  // 3. A camera permission request that is still pending when the streamer leaves must not start the camera.
  {
    let grant, stopped = 0;
    const stream = { getTracks: () => [{ stop() { stopped++; } }], getVideoTracks: () => [{ addEventListener() {} }] };
    const { get, run, reply, tick } = env({ getUserMedia: () => new Promise(resolve => { grant = resolve; }) });
    run("enter('streamer','ABC234','secret')");
    await reply(0, streamerState([], []));
    get('webcamToggle').listeners.click(); await tick();
    assert.equal(get('webcamToggle').disabled, true, 'waiting for permission');
    get('leave').listeners.click();
    grant(stream); await tick(); await tick();
    assert.equal(stopped, 1, 'the late camera stream is stopped immediately');
    assert.equal(run('webcamStream'), null, 'no camera is kept for the departed session');
    assert.equal(get('webcamToggle').disabled, false);
    assert.notEqual(get('webcamToggle').textContent, 'Turn off webcam preview');
  }

  // 4. The library: tiles appear for approved items, pictures load once, and the buttons send the right requests.
  {
    const { get, run, reply, requests, walk, tick } = env();
    run("enter('streamer','ABC234','secret')");
    const entry = (id, extra = {}) => ({ id, description: 'cloud ' + id, creator: 'Mira', placement: 'object', ai: true, ...extra });
    await reply(0, { ...streamerState([], []), library: [entry(5), entry(6)] });
    assert.equal(get('libGrid').children.length, 2, 'one tile per saved item');
    assert.equal(get('libEmpty').hidden, true);
    const wanted = requests.slice(1).map(r => r.url).sort();
    assert.deepEqual(wanted, ['/api/rooms/ABC234/library/5', '/api/rooms/ABC234/library/6'], 'each picture is fetched once');
    for (const index of [1, 2]) await reply(index, { image: 'data:image/webp;base64,IMG' + index });
    assert.ok(walk(get('libGrid')).some(n => n.src && n.src.startsWith('data:image/webp')), 'thumbnails show once loaded');
    const before = requests.length;
    run('update(true)'); await tick(); await reply(before, { ...streamerState([], []), library: [entry(5), entry(6)] });
    assert.equal(requests.length, before + 1, 'cached pictures are not fetched again');
    const buttons = walk(get('libGrid')).filter(n => /Background|Piece|✕/.test(n.textContent));
    const newest = buttons.slice(0, 3);   // newest item (6) is listed first
    newest[0].listeners.click(); await tick();
    let sent = requests[requests.length - 1]; assert.match(sent.url, /\/library\/6\/use$/); assert.deepEqual(JSON.parse(sent.options.body), { as: 'full' });
    await reply(requests.length - 1, { ok: true });
    newest[1].listeners.click(); await tick();
    sent = requests[requests.length - 1]; assert.deepEqual(JSON.parse(sent.options.body), { as: 'piece' });
    await reply(requests.length - 1, { ok: true });
    newest[2].listeners.click(); await tick();
    sent = requests[requests.length - 1]; assert.match(sent.url, /\/library\/6\/delete$/);
    await reply(requests.length - 1, { ok: true });
    await reply(requests.length - 1, { ...streamerState([], []), library: [] });
    get('leave').listeners.click();
    assert.equal(run('library.length'), 0, 'leaving forgets the library');
    assert.equal(run('libImages.size'), 0, 'and its cached pictures');
  }

  // 5. The prompt helper: guided answers write the prompt, and "Use this prompt" fills the box the viewer opened it from.
  {
    const { get, run, reply, requests, walk } = env();
    run("viewerToken='t'; aiArt=true; enter('viewer','ABC234')");
    await reply(0, { approved: [], paused: false, theme: 'neon' });
    const chip = (box, text) => walk(get(box)).find(n => n.textContent === text);
    get('description').value = 'a smiling cloud';
    get('promptHelp').listeners.click();
    assert.equal(get('helperOverlay').hidden, false, 'the helper opens');
    assert.equal(get('helperIdea').value, 'a smiling cloud', 'it starts from what the viewer already typed');
    assert.equal(get('helperResult').value, 'a smiling cloud');
    chip('helperMoods', 'Cozy').listeners.click();
    chip('helperColors', 'Pastel').listeners.click();
    get('helperDetails').value = 'wearing a tiny hat'; get('helperDetails').listeners.input();
    assert.equal(get('helperResult').value, 'a smiling cloud, cozy and warm mood, soft pastel colors, wearing a tiny hat');
    assert.equal(chip('helperMoods', 'Cozy').attrs['aria-pressed'], 'true'); assert.equal(chip('helperMoods', 'Epic').attrs['aria-pressed'], 'false');
    chip('helperMoods', 'Cozy').listeners.click();
    assert.equal(get('helperResult').value, 'a smiling cloud, soft pastel colors, wearing a tiny hat', 'clicking a chosen chip again unchooses it');
    get('helperResult').value = 'a smiling cloud, my own words'; get('helperResult').listeners.input();
    assert.equal(get('helperUse').disabled, false);
    let typed = 0; get('description').listeners.input = () => { typed++; };
    get('helperUse').listeners.click();
    assert.equal(get('description').value, 'a smiling cloud, my own words', 'the edited prompt is used');
    assert.equal(typed, 1, 'the page is told the box changed so previews stay in step');
    assert.equal(get('helperOverlay').hidden, true); assert.equal(get('helperIdea').value, '', 'the helper is emptied after use');
    // Surprise me, the right ideas for the chosen placement, and an empty helper cannot be used.
    run("kind='full'"); get('promptHelp').listeners.click();
    assert.ok(walk(get('helperIdeas')).every(n => !n.textContent || run('LittleWorldsPrompts.IDEAS.full').includes(n.textContent)), 'background ideas for a full background');
    get('helperSurprise').listeners.click();
    assert.ok(get('helperIdea').value && get('helperResult').value.includes(get('helperIdea').value));
    get('helperIdea').value = ''; get('helperIdea').listeners.input();
    assert.equal(get('helperResult').value, ''); assert.equal(get('helperUse').disabled, true, 'nothing to use yet');
    // Escape and leaving close and wipe it.
    run("document.handlers.keydown.forEach(fn=>fn({key:'Escape'}))"); assert.equal(get('helperOverlay').hidden, true);
    get('promptHelp').listeners.click(); get('helperIdea').value = 'private idea'; get('helperIdea').listeners.input();
    get('leave').listeners.click();
    assert.equal(get('helperOverlay').hidden, true); assert.equal(get('helperIdea').value, ''); assert.equal(get('helperResult').value, '', 'leaving wipes the helper');
    // The streamer's background box opens it as a full-background helper.
    run("enter('streamer','ABC234','secret')"); await reply(requests.length - 1, streamerState([], []));
    get('bgPrompt').value = 'a cozy attic'; get('bgPromptHelp').listeners.click();
    assert.equal(run('helper.placement'), 'full'); assert.equal(run('helper.target'), 'bgPrompt'); assert.equal(get('helperIdea').value, 'a cozy attic');
    get('helperUse').listeners.click(); assert.equal(get('bgPrompt').value, 'a cozy attic');
  }

  // 6. If promptkit.js is missing (an older server), the app still loads and the helper buttons are simply hidden.
  {
    const { get, run, reply } = env({ withoutPromptKit: true });
    assert.equal(get('promptHelp').hidden, true); assert.equal(get('bgPromptHelp').hidden, true);
    run("viewerToken='t'; enter('viewer','ABC234')"); await reply(0, { approved: [], paused: false, theme: 'neon' });
    get('leave').listeners.click();   // leaving still works without the helper
  }

  console.log('PASS: slider targets the previewed item, real AI limit is shown, leaving clears private work, pending camera is cancelled, library tiles and actions, prompt helper.');
})().catch(e => { console.error(e); process.exitCode = 1; });
