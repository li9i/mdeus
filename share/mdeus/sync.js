'use strict';

const AIMS = '.aim, .block';
const CURSOR_MS = 200;
const DEFAULT_SHARE = 0.25;
const FLASH_MS = 1000;
const KEYWORD = '[\\p{L}\\p{N}_]';
const WORD = 'mdeus-word';

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

function* copiesOf(word, mark) {
  yield* rangesOf(new RegExp(
    `(?<!${KEYWORD})${RegExp.escape(word)}(?!${KEYWORD})`, 'gu'), mark);
}

function flash(mark, word) {
  const lit = pane.querySelector('.mdeus-click');
  if (lit) {
    lit.classList.remove('mdeus-click');
  }
  window.clearTimeout(flashTimer);
  CSS.highlights.delete(WORD);
  mark.classList.add('mdeus-click');
  if (word) {
    CSS.highlights.set(WORD, new Highlight(word));
  }
  flashTimer = window.setTimeout(() => {
    mark.classList.remove('mdeus-click');
    CSS.highlights.delete(WORD);
  }, FLASH_MS);
}

function forget() {
  pane.querySelectorAll('.mdeus-click, .mdeus-cursor').forEach((mark) => {
    mark.classList.remove('mdeus-click', 'mdeus-cursor');
  });
  window.clearTimeout(flashTimer);
  CSS.highlights.delete(WORD);
  clicksAt = null;
  lineAt = null;
  ruleAt = null;
}

function markCursor(line, clicked, word, earlier) {
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
    const nth = earlier.filter((at) => at >= ruleAt).length;
    flash(mark, copiesOf(word, mark).drop(nth).next().value);
    show(mark);
  }
}

function onDouble(event) {
  const aim = event.target.closest(AIMS);
  if (!aim || cursorTimer === null) {
    return;
  }
  const selection = window.getSelection();
  const word = wordAt(selection.getRangeAt(0).cloneRange(), aim);
  selection.removeAllRanges();
  let nth = 0;
  for (const copy of copiesOf(word.toString(), aim)) {
    if (copy.compareBoundaryPoints(Range.START_TO_START, word) >= 0) {
      break;
    }
    nth += 1;
  }
  flash(aim, word);
  fetch('/api/jump', {
    body: JSON.stringify({
      last: Number(aim.dataset.end),
      line: Number(aim.dataset.start),
      nth,
      word: word.toString(),
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
      markCursor(where.line, clicked, where.word, where.earlier);
    }
    lineAt = where.line;
  }
  clicksAt = where.clicks;
}

function* rangesOf(pattern, mark) {
  const walker = document.createTreeWalker(mark, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    for (const found of walker.currentNode.data.matchAll(pattern)) {
      const range = document.createRange();
      range.setStart(walker.currentNode, found.index);
      range.setEnd(walker.currentNode, found.index + found[0].length);
      yield range;
    }
  }
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

function wordAt(clicked, aim) {
  if (new RegExp(KEYWORD, 'u').test(clicked.toString())) {
    return clicked;
  }
  const after = rangesOf(new RegExp(`${KEYWORD}+`, 'gu'), aim).find(
    (run) => run.compareBoundaryPoints(Range.START_TO_START, clicked) >= 0);
  return after || clicked;
}

begin();
