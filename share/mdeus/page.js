'use strict';

const CONTENTS_MINIMUM = 3;
const COPIED_MS = 1500;
const PLACE_KEY = 'mdeus:place';
const SHORTCUTS = { c: 'contents', e: 'edit', f: 'wide' };
const THEMES = [
  ['browser', 'Browser default'],
  ['report', 'Mono headings'],
  ['github', 'GitHub'],
];
const TREE = 'file:///tree/';

const controlsNode = document.querySelector('.controls');
const docNode = document.querySelector('.doc');
const foldedAt = new Set();

let contentsOpen = false;
let doc = null;
let editing = false;
let headingIds = [];
let mtime = null;
let sectionLines = new Set();
let theme = null;
let wide = null;

function anchor() {
  const blocks = docNode.querySelectorAll('.block');
  const barFoot = controlsNode.getBoundingClientRect().bottom;
  for (const block of blocks) {
    if (block.hidden) {
      continue;
    }
    const top = block.getBoundingClientRect().top;
    if (top >= barFoot) {
      return { start: block.dataset.start, top };
    }
  }
  return null;
}

function applyEditing(now) {
  const button = document.getElementById('edit');
  if (button) {
    setPressed(button, now);
  }
  if (now === editing) {
    return;
  }
  editing = now;
  document.dispatchEvent(
    new CustomEvent('mdeus:editing', { detail: { editing } })
  );
}

function applyFolds() {
  docNode.querySelectorAll('.block').forEach((block) => {
    if (isSection(block)) {
      foldSection(block, foldedAt.has(Number(block.dataset.start)));
    }
  });
}

function applyTheme() {
  const root = document.documentElement;
  THEMES.forEach(([key]) => root.classList.toggle(key, key === theme));
}

function applyWide() {
  document.documentElement.classList.toggle('wide', wide);
}

function blockHtml(block) {
  return (
    `<div class="block" data-start="${block.line_start}" data-end="${block.line_end}">` +
    `<div class="prose">${block.html}</div>` +
    '</div>'
  );
}

function buildControls() {
  const label = document.createElement('label');
  label.htmlFor = 'theme';
  label.textContent = 'Theme';
  const select = document.createElement('select');
  select.id = 'theme';
  THEMES.forEach(([key, name]) => {
    const option = document.createElement('option');
    option.textContent = name;
    option.value = key;
    select.append(option);
  });
  select.value = theme;
  select.addEventListener('change', onTheme);
  controlsNode.append(label, select, toggleButton('wide', 'Full width', wide, onWide));
  if (doc.editable) {
    controlsNode.append(toggleButton('edit', 'Edit', editing, onEdit));
  }
}

function contentsHtml() {
  const out = [];
  const levels = [];
  doc.outline.forEach((entry, index) => {
    if (!levels.length || entry.level > levels[levels.length - 1]) {
      out.push('<ul>');
      levels.push(entry.level);
    } else {
      out.push('</li>');
      while (levels.length > 1 && entry.level < levels[levels.length - 1]) {
        out.push('</ul></li>');
        levels.pop();
      }
      levels[levels.length - 1] = entry.level;
    }
    out.push(`<li><a href="#${headingIds[index]}">${esc(entry.text)}</a>`);
  });
  while (levels.length) {
    out.push('</li></ul>');
    levels.pop();
  }
  return (
    '<nav class="toc"><p class="toc-title">Contents</p>' + out.join('') + '</nav>'
  );
}

function copyFence(pre, button) {
  const text = pre.textContent;
  const sayCopied = () => {
    button.classList.add('copied');
    button.textContent = 'Copied';
    window.setTimeout(() => {
      button.classList.remove('copied');
      button.textContent = 'Copy';
    }, COPIED_MS);
  };
  const bySelection = () => {
    const holder = document.createElement('textarea');
    holder.value = text;
    holder.style.opacity = '0';
    holder.style.position = 'fixed';
    document.body.append(holder);
    holder.select();
    document.execCommand('copy');
    holder.remove();
    sayCopied();
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(sayCopied, bySelection);
  } else {
    bySelection();
  }
}

function documentPath(href) {
  if (!href || href.startsWith('#') || href.startsWith('/') || /^[a-z][a-z0-9+.-]*:/i.test(href)) {
    return null;
  }
  const root = new URL(TREE);
  const target = new URL(href, new URL(doc.name, TREE));
  if (!target.href.startsWith(TREE) || !target.pathname.endsWith('.md')) {
    return null;
  }
  return decodeURIComponent(target.pathname.slice(root.pathname.length));
}

function drawContents() {
  const enough = headingIds.length >= CONTENTS_MINIMUM;
  const existing = document.querySelector('.toc');
  if (existing) {
    existing.remove();
  }
  if (contentsOpen && enough) {
    docNode.insertAdjacentHTML('beforebegin', contentsHtml());
  }
  let button = document.getElementById('contents');
  if (!enough) {
    if (button) {
      button.remove();
    }
    return;
  }
  if (!button) {
    button = toggleButton('contents', 'Contents', contentsOpen, onContents);
    controlsNode.insertBefore(button, document.getElementById('wide'));
  }
  setPressed(button, contentsOpen);
}

function drawCopyButtons() {
  docNode.querySelectorAll('pre').forEach((pre) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block';
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.append(pre);
    const button = document.createElement('button');
    button.className = 'copy';
    button.textContent = 'Copy';
    button.type = 'button';
    button.addEventListener('click', () => copyFence(pre, button));
    wrapper.append(button);
  });
}

function drawDocument() {
  document.title = doc.name;
  if (doc.gone) {
    docNode.innerHTML = `<p class="gone">${esc(doc.name || 'The file')} is gone.</p>`;
    headingIds = [];
    sectionLines = new Set();
    return;
  }
  sectionLines = new Set(
    doc.outline.filter((entry) => entry.level === 1).map((entry) => entry.line)
  );
  const parts = doc.blocks.map(blockHtml);
  const meta = `<p class="meta">${esc(doc.name)}</p>`;
  if (doc.blocks.length && doc.blocks[0].type === 'heading') {
    parts.splice(1, 0, meta);
  } else {
    parts.unshift(meta);
  }
  docNode.innerHTML = parts.join('');
  const headings = docNode.querySelectorAll('h1, h2, h3, h4, h5, h6');
  const used = [];
  headingIds = doc.outline.map((entry, index) => {
    const id = slug(entry.text, used);
    if (headings[index]) {
      headings[index].id = id;
    }
    return id;
  });
  drawCopyButtons();
  applyFolds();
}

function drawn() {
  fetch('/api/drawn', { method: 'POST' }).catch(() => {});
}

function esc(text) {
  const replacements = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
  return String(text).replace(/[&<>"]/g, (character) => replacements[character]);
}

function foldSection(heading, folded) {
  heading.classList.toggle('folded', folded);
  for (let next = heading.nextElementSibling; next; next = next.nextElementSibling) {
    if (!next.classList.contains('block')) {
      continue;
    }
    if (isSection(next)) {
      return;
    }
    next.hidden = folded;
  }
}

async function follow(relative, push) {
  const response = await fetch(`/doc?path=${encodeURIComponent(relative)}`);
  if (!response.ok) {
    return;
  }
  doc = await response.json();
  foldedAt.clear();
  mtime = doc.mtime;
  if (push) {
    history.pushState({ path: doc.name }, '');
  }
  drawDocument();
  drawContents();
  window.scrollTo(0, 0);
}

async function hold() {
  let response;
  try {
    response = await fetch('/hold');
  } catch (error) {
    return;
  }
  if (!response.ok) {
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let rest = '';
  try {
    for (;;) {
      const arrived = await reader.read();
      if (arrived.done) {
        break;
      }
      rest += decoder.decode(arrived.value, { stream: true });
      const lines = rest.split('\n');
      rest = lines.pop();
      for (const line of lines) {
        await told(JSON.parse(line));
      }
    }
  } catch (error) {
  }
  hold();
}

function isSection(block) {
  return sectionLines.has(Number(block.dataset.start));
}

function keepPlace() {
  const mark = doc && !doc.gone ? anchor() : null;
  if (!mark) {
    sessionStorage.removeItem(PLACE_KEY);
    return;
  }
  sessionStorage.setItem(
    PLACE_KEY,
    JSON.stringify({ name: doc.name, start: mark.start, top: mark.top })
  );
}

function keptPlace() {
  const kept = sessionStorage.getItem(PLACE_KEY);
  sessionStorage.removeItem(PLACE_KEY);
  if (!kept) {
    return null;
  }
  const place = JSON.parse(kept);
  return place.name === doc.name ? place : null;
}

async function load() {
  const mark = anchor();
  const response = await fetch('/doc');
  doc = await response.json();
  mtime = doc.mtime;
  if (theme === null) {
    theme = doc.state.theme;
    contentsOpen = doc.state.contents;
    wide = doc.state.wide;
    applyTheme();
    applyWide();
    buildControls();
  }
  applyEditing(Boolean(doc.editing));
  drawDocument();
  drawContents();
  restore(mark);
}

function measureBar() {
  document.documentElement.style.setProperty(
    '--bar-height',
    `${controlsNode.offsetHeight}px`
  );
}

function onClick(event) {
  const link = event.target.closest('a');
  if (!link) {
    return;
  }
  const relative = documentPath(link.getAttribute('href'));
  if (relative === null) {
    return;
  }
  event.preventDefault();
  follow(relative, true);
}

function onContents() {
  contentsOpen = !contentsOpen;
  drawContents();
  saveState();
}

function onEdit() {
  fetch('/api/edit', {
    body: JSON.stringify({ editing: !editing }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function onKey(event) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
    return;
  }
  if (event.target.closest && event.target.closest('input, select, textarea, [contenteditable]')) {
    return;
  }
  const button = document.getElementById(SHORTCUTS[event.key] || '');
  if (!button) {
    return;
  }
  event.preventDefault();
  button.click();
}

function onPop(event) {
  if (event.state && event.state.path !== doc.name) {
    follow(event.state.path, false);
  }
}

function onTheme(event) {
  const mark = anchor();
  theme = event.target.value;
  applyTheme();
  restore(mark);
  saveState();
}

function onWide(event) {
  const mark = anchor();
  wide = !wide;
  applyWide();
  setPressed(event.currentTarget, wide);
  restore(mark);
  saveState();
}

function restore(mark) {
  if (!mark) {
    return;
  }
  const block = docNode.querySelector(`.block[data-start="${mark.start}"]`);
  if (block) {
    window.scrollBy(0, block.getBoundingClientRect().top - mark.top);
  }
}

function saveState() {
  fetch('/api/state', {
    body: JSON.stringify({ contents: contentsOpen, theme, wide }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function setPressed(button, on) {
  button.setAttribute('aria-pressed', on ? 'true' : 'false');
}

function slug(text, used) {
  const base =
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'section';
  let name = base;
  for (let n = 2; used.includes(name); n += 1) {
    name = `${base}-${n}`;
  }
  used.push(name);
  return name;
}

async function start() {
  history.scrollRestoration = 'manual';
  hold();
  await load();
  restore(keptPlace());
  window.addEventListener('pagehide', keepPlace);
  history.replaceState({ path: doc.name }, '');
  docNode.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);
  new ResizeObserver(measureBar).observe(controlsNode, { box: 'border-box' });
  window.addEventListener('popstate', onPop);
  drawn();
}

function toggleButton(id, text, pressed, handler) {
  const button = document.createElement('button');
  const letter = text.slice(0, 1);
  button.addEventListener('click', handler);
  button.id = id;
  button.innerHTML = `<u>${letter}</u>${text.slice(1)}`;
  button.title = `${text} (${letter.toLowerCase()})`;
  button.type = 'button';
  setPressed(button, pressed);
  return button;
}

async function told(said) {
  if (doc === null) {
    return;
  }
  applyEditing(Boolean(said.editing));
  if (said.mtime === mtime) {
    return;
  }
  mtime = said.mtime;
  await load();
}

start();
