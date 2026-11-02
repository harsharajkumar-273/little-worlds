'use strict';
// Only the approved scene is read; pending submissions never reach this page.
const outputObjects = document.getElementById('objects');
const backdropLayer = document.getElementById('backdrops'), fullLayer = document.getElementById('fullbg');
const banner = document.getElementById('revealBanner');
const outputScene = document.getElementById('outputScene');
const room = new URLSearchParams(location.search).get('room') || '';
const THEMES = ['neon', 'space', 'sunset', 'forest', 'ocean', 'studio', 'green', 'clear'];
const nodes = new Map();
let initialized = false, revealQueue = [], activeReveal = null, revealTimer = null;
function cancelReveal() {
  if (revealTimer !== null) clearTimeout(revealTimer);
  revealTimer = null;
  if (activeReveal !== null) nodes.get(activeReveal)?.firstElementChild.classList.remove('reveal-pop');
  activeReveal = null; banner.hidden = true; banner.textContent = '';
}
function showNext() {
  if (activeReveal !== null || !revealQueue.length) return;
  const item = revealQueue.shift();
  const node = nodes.get(item.id);
  if (!node) { showNext(); return; }
  activeReveal = item.id;
  node.firstElementChild.classList.add('reveal-pop');
  banner.textContent = `✦  Created by ${item.creator}`;
  banner.hidden = false;
  revealTimer = setTimeout(() => { cancelReveal(); showNext(); }, 3000);
}
function render(items) {
  const present = new Set(items.map(item => item.id));
  revealQueue = revealQueue.filter(item => present.has(item.id));
  if (activeReveal !== null && !present.has(activeReveal)) cancelReveal();
  for (const [id, node] of nodes) {
    if (!present.has(id)) { node.remove(); nodes.delete(id); }
  }
  for (const item of items) {
    let node = nodes.get(item.id);
    if (!node) {
      node = document.createElement('div'); node.className = item.placement === 'full' ? 'object full' : item.placement === 'backdrop' ? 'object backdrop' : 'object';
      const reveal = document.createElement('div'); reveal.className = 'reveal-wrap';
      const effect = document.createElement('div'); effect.className = `effect ${item.behavior}`;
      const image = document.createElement('img'); image.src = item.image; image.alt = '';
      effect.append(image); reveal.append(effect); node.append(reveal); (item.placement === 'full' ? fullLayer : item.placement === 'backdrop' ? backdropLayer : outputObjects).append(node);
      nodes.set(item.id, node);
      if (initialized) revealQueue.push({id:item.id, creator:item.creator});
    }
    node.style.left = `${item.x}%`; node.style.top = `${item.y}%`; node.style.setProperty('--s', item.scale || 1);
  }
  initialized = true; showNext();
}
async function poll() {
  try {
    if (!/^[A-Z2-9]{6}$/.test(room)) throw new Error('Invalid room');
    const response = await fetch(`/api/rooms/${encodeURIComponent(room)}`, {cache:'no-store', signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error('Room unavailable');
    const data = await response.json();
    if (!Array.isArray(data.approved)) throw new Error('Invalid scene');
    const theme = THEMES.includes(data.theme) ? data.theme : 'neon';
    outputScene.dataset.theme = theme;
    if (document.documentElement) document.documentElement.dataset.theme = theme;
    render(data.approved);
  } catch (_) {
    // On disconnect, clear objects and do not replay old approvals on reconnect.
    cancelReveal(); revealQueue = []; nodes.clear(); outputObjects.replaceChildren(); backdropLayer.replaceChildren(); fullLayer.replaceChildren(); initialized = false;
  } finally { setTimeout(poll, 1000); }
}
poll();
