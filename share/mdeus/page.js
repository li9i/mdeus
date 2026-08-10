/* The reading page: the theme dropdown, the contents list, the sections a
   double click folds away, the redraw when the file changes, and the heartbeat
   that ends a reading with no terminal.

   The page keeps nothing of its own. It draws what GET /doc sends and writes
   every change back through POST /api/state, so one reading and the next
   agree wherever they were opened from.

   The structure this builds is written out at the top of themes.css. */

'use strict';

/* Three headings is the point at which a contents list starts to earn its
   place. Below it the button is absent rather than disabled. */
const CONTENTS_MINIMUM = 3;
/* How long a copy button says it copied before it offers to again. */
const COPIED_MS = 1500;
const HEARTBEAT_MS = 3000;
const MTIME_MS = 500;
const THEMES = [
  ['browser', 'Browser default'],
  ['report', 'Mono headings'],
  ['github', 'GitHub'],
];
/* A stand in for the directory the reading started in, used only to work out
   whether a link resolves inside it. Nothing is ever fetched from it. */
const TREE = 'file:///tree/';

const controlsNode = document.querySelector('.controls');
const docNode = document.querySelector('.doc');
/* The sections a double click has folded away, by the source line the heading
   of each one starts at. Lines rather than elements, because the document is
   built again from scratch on every redraw and the elements go with it. */
const foldedAt = new Set();

let contentsOpen = false;
let doc = null;
let headingIds = [];
let mtime = null;
/* The source lines the top level headings start at, which is to say where every
   section the page can fold begins. Taken from the outline the server sends. */
let sectionLines = new Set();
let theme = null;

function anchor() {
  /* The first block still on screen, and how far down the window it sits. A
     theme change alters every measurement on the page, so the reading
     position has to be held by a block rather than by a pixel offset. */
  const blocks = docNode.querySelectorAll('.block');
  for (const block of blocks) {
    if (block.hidden) {
      continue; // folded away, so it has no place on the page to hold
    }
    const top = block.getBoundingClientRect().top;
    if (top >= 0) {
      return { start: block.dataset.start, top };
    }
  }
  return null;
}

function applyFolds() {
  /* Put the folds back after a redraw. Every section is drawn open, so the
     ones that were folded are folded again here. */
  docNode.querySelectorAll('.block').forEach((block) => {
    if (isSection(block)) {
      foldSection(block, foldedAt.has(Number(block.dataset.start)));
    }
  });
}

function applyTheme() {
  /* Only the theme key is swapped. The root carries other classes that are not
     this page's to write, the reader marker the stylesheet sizes github off
     being one, so the keys are turned on and off one at a time rather than the
     whole class name being written over. */
  const root = document.documentElement;
  THEMES.forEach(([key]) => root.classList.toggle(key, key === theme));
}

function blockHtml(block) {
  /* One block of the document, carrying the source lines it was built from. */
  return (
    `<div class="block" data-start="${block.line_start}" data-end="${block.line_end}">` +
    `<div class="prose">${block.html}</div>` +
    '</div>'
  );
}

function buildControls() {
  /* Two native controls and nothing else. */
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
  controlsNode.append(label, select);
}

function contentsHtml() {
  /* A nested list following the heading levels. A document may skip a level,
     so the open lists are tracked rather than counted. */
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
  /* Put a fence on the clipboard, exactly as it was rendered.

     navigator.clipboard is missing or refused in some file:// readings, which
     is where a printed copy is opened, so the old selection trick stands
     behind it. */
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

async function currentMtime() {
  /* The modification time the server last saw. Null once the file is gone. */
  const response = await fetch('/mtime');
  const payload = await response.json();
  return payload.mtime;
}

function documentPath(href) {
  /* The path of another markdown document inside the tree the reading started
     in, relative to that tree. Null for anything the browser should handle
     itself: an anchor within the page, an absolute path, an http link, a link
     to something that is not markdown, and a relative path climbing out of
     the tree. A link is read against the document holding it, which is not
     always the one the reading started at. */
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
  /* The list and the button that opens it, drawn together. Following a link
     changes the document and with it the number of headings, so both are put up
     or taken away again on every draw rather than built once at the start.

     The list sits above the document and pushes it down. It never floats. */
  const enough = headingIds.length >= CONTENTS_MINIMUM;
  const existing = document.querySelector('.toc');
  if (existing) {
    existing.remove();
  }
  if (contentsOpen && enough) {
    docNode.insertAdjacentHTML('beforebegin', contentsHtml());
  }
  let button = controlsNode.querySelector('button');
  if (!enough) {
    if (button) {
      button.remove();
    }
    return;
  }
  if (!button) {
    button = document.createElement('button');
    button.addEventListener('click', onContents);
    button.id = 'contents';
    button.type = 'button';
    controlsNode.append(button);
  }
  button.textContent = contentsOpen ? 'Hide contents' : 'Contents';
}

function drawCopyButtons() {
  /* A copy button in the corner of every fence. The document is rebuilt on
     every redraw, so these are put up again with it rather than once at the
     start. The wrapper is what the button is positioned against. */
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
  /* The heading ids are assigned here, from the outline the server sends.
     Changing the theme does not come through this function, so no theme ever
     renames them. */
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

function esc(text) {
  /* Heading names and file names are put on the page as markup, and both come
     out of the file being read. Anything in them that reads as a tag has to
     stop reading as one first. */
  const replacements = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
  return String(text).replace(/[&<>"]/g, (character) => replacements[character]);
}

function foldSection(heading, folded) {
  /* Put a section away or bring it back. Everything under the heading goes as
     far as the next top level heading, and the heading itself stays and is
     marked, so that a folded section still says where it is and can be opened
     again. The file name above the document is not part of any section and is
     left where it is. */
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
  /* Move the reading to another document inside the tree. The server moves
     with it, so the file whose modification time is being watched moves too
     and has to be read again before the next poll mistakes it for an edit. */
  const response = await fetch(`/doc?path=${encodeURIComponent(relative)}`);
  if (!response.ok) {
    return; // outside the tree, and the reading carries on where it is
  }
  doc = await response.json();
  /* Another document, whose sections are its own. What was folded away in the
     one before it means nothing here, and the lines it was held by would fold
     whatever happens to start at them. */
  foldedAt.clear();
  mtime = doc.mtime;
  if (push) {
    history.pushState({ path: doc.name }, '');
  }
  drawDocument();
  drawContents();
  window.scrollTo(0, 0);
}

function heartbeat() {
  /* A reading opened from the file manager has no terminal to interrupt, so
     the server stops once this stops arriving. */
  fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
}

function isSection(block) {
  /* Say whether a block is a section of its own, which is to say a top level
     heading. Nothing under that level folds. The outline the server sends
     already says which lines those begin at, so the rendered markup is not
     asked the same question a second time. */
  return sectionLines.has(Number(block.dataset.start));
}

async function load() {
  /* Draw what the server has. Called again whenever the file changes, so it
     holds the reading position across a redraw. The document arrives with the
     time it was last written, so the poll that follows compares against what
     is on the screen rather than asking a second question. */
  const mark = anchor();
  const response = await fetch('/doc');
  doc = await response.json();
  mtime = doc.mtime;
  if (theme === null) {
    theme = doc.state.theme;
    contentsOpen = doc.state.contents;
    applyTheme();
    buildControls();
  }
  drawDocument();
  drawContents();
  restore(mark);
}

function onClick(event) {
  /* A link to another document is followed in place, so the reading stays one
     page and the back button returns the way it would anywhere else. */
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
  /* The choice belongs to the server rather than to this page, so it is
     written back as it is made and the next reading opens the same way. */
  contentsOpen = !contentsOpen;
  drawContents();
  saveState();
}

function onPop(event) {
  /* A jump to an anchor makes a history entry of its own. Going back over one
     must leave the reading where it is, or the browser's own jump back would
     be undone by a redraw. */
  if (event.state && event.state.path !== doc.name) {
    follow(event.state.path, false);
  }
}

function onTheme(event) {
  /* A theme change is a class swap and nothing more. The document, its
     heading ids and the reading position all stay as they are. */
  const mark = anchor();
  theme = event.target.value;
  applyTheme();
  restore(mark);
  saveState();
}

async function poll() {
  /* Nothing tells the page the file was written, so it asks. The modification
     time is the small question, and the document is fetched again only once
     the answer has moved. */
  let seen;
  try {
    seen = await currentMtime();
  } catch (error) {
    return; // the server has stopped answering and the reading is over
  }
  if (seen !== mtime) {
    mtime = seen;
    await load();
  }
}

function restore(mark) {
  /* Put the block that was at the top of the window back where it was. */
  if (!mark) {
    return;
  }
  const block = docNode.querySelector(`.block[data-start="${mark.start}"]`);
  if (block) {
    window.scrollBy(0, block.getBoundingClientRect().top - mark.top);
  }
}

function saveState() {
  /* The store is the server's. Nothing is kept in the browser. */
  fetch('/api/state', {
    body: JSON.stringify({ contents: contentsOpen, theme }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function slug(text, used) {
  /* The same naming the spec review tool uses, so a link to a section reads
     the same whichever tool rendered the document. */
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
  await load();
  /* The document the reading opened at is the first history entry, so going
     back to it names a path like every other entry does. */
  history.replaceState({ path: doc.name }, '');
  docNode.addEventListener('click', onClick);
  window.addEventListener('popstate', onPop);
  heartbeat();
  window.setInterval(heartbeat, HEARTBEAT_MS);
  window.setInterval(poll, MTIME_MS);
}

start();
