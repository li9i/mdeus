'use strict';

const AIMS = '.aim, .block';
const CURSOR_MS = 200;
const DEFAULT_SHARE = 0.25;
const FLASH_MS = 1000;

const controls = document.querySelector('.controls');
const pane = document.querySelector('.doc');

let clicksAt = null;
let cursorTimer = null;
let flashTimer = null;
let lineAt = null;
let ruleAt = null;
let shareAt = DEFAULT_SHARE;

function aimIn(block, line) {
  let finest = null;
  for (const aim of block.querySelectorAll('.aim')) {
    if (Number(aim.dataset.start) > line || Number(aim.dataset.end) < line) {
      continue;
    }
    if (!finest || span(aim) < span(finest)) {
      finest = aim;
    }
  }
  return finest;
}

function begin() {
  pane.addEventListener('dblclick', onDouble);
  document.addEventListener('mdeus:editing', onEditing);
}

function blockForLine(line) {
  let holding = null;
  let above = null;
  for (const block of pane.querySelectorAll('.block')) {
    const start = Number(block.dataset.start);
    if (start > line) {
      continue;
    }
    if (!holding && Number(block.dataset.end) >= line) {
      holding = block;
    }
    if (!above || start > Number(above.dataset.start)) {
      above = block;
    }
  }
  return holding || above;
}

function flash(mark) {
  const lit = pane.querySelector('.mdeus-click');
  if (lit) {
    lit.classList.remove('mdeus-click');
  }
  window.clearTimeout(flashTimer);
  mark.classList.add('mdeus-click');
  flashTimer = window.setTimeout(() => mark.classList.remove('mdeus-click'), FLASH_MS);
}

function forget() {
  pane.querySelectorAll('.mdeus-click, .mdeus-cursor').forEach((mark) => {
    mark.classList.remove('mdeus-click', 'mdeus-cursor');
  });
  window.clearTimeout(flashTimer);
  clicksAt = null;
  lineAt = null;
  ruleAt = null;
}

function markCursor(line, clicked) {
  const block = shownFor(blockForLine(line));
  const mark = (block && aimIn(block, line)) || block;
  const ruled = pane.querySelector('.mdeus-cursor');
  if (ruled && ruled !== mark) {
    ruled.classList.remove('mdeus-cursor');
  }
  if (!mark) {
    ruleAt = null;
    return;
  }
  mark.classList.add('mdeus-cursor');
  ruleAt = Number(mark.dataset.start);
  if (clicked) {
    flash(mark);
    show(mark);
  }
}

function onDouble(event) {
  const aim = event.target.closest(AIMS);
  if (!aim || cursorTimer === null) {
    return;
  }
  window.getSelection().removeAllRanges();
  flash(aim);
  fetch('/api/jump', {
    body: JSON.stringify({
      last: Number(aim.dataset.end),
      line: Number(aim.dataset.start),
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function onEditing(event) {
  if (event.detail.editing) {
    if (cursorTimer === null) {
      cursorTimer = window.setInterval(pollCursor, CURSOR_MS);
    }
    return;
  }
  if (cursorTimer !== null) {
    window.clearInterval(cursorTimer);
    cursorTimer = null;
    forget();
  }
}

async function pollCursor() {
  let where;
  try {
    const response = await fetch('/api/cursor');
    where = await response.json();
  } catch (error) {
    return;
  }
  if (typeof where.share === 'number') {
    shareAt = where.share;
  }
  if (typeof where.line === 'number') {
    const clicked = clicksAt !== null && where.clicks !== clicksAt;
    if (clicked || where.line !== lineAt || !ruleStands()) {
      markCursor(where.line, clicked);
    }
    lineAt = where.line;
  }
  clicksAt = where.clicks;
}

function ruleStands() {
  const ruled = pane.querySelector('.mdeus-cursor');
  return ruled === null ? ruleAt === null : Number(ruled.dataset.start) === ruleAt;
}

function show(mark) {
  const head = controls.getBoundingClientRect().bottom;
  const room = window.innerHeight - head;
  window.scrollBy(0, mark.getBoundingClientRect().top - head - room * shareAt);
}

function shownFor(block) {
  for (let shown = block; shown; shown = shown.previousElementSibling) {
    if (shown.classList.contains('block') && !shown.hidden) {
      return shown;
    }
  }
  return block;
}

function span(mark) {
  return Number(mark.dataset.end) - Number(mark.dataset.start);
}

begin();
