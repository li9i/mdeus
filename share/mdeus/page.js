/* The reading page: the theme dropdown, the Contents, Full width and Edit
   toggles beside it, the contents list, the sections a double click folds away,
   and the one connection that carries the rest. The server speaks down it
   whenever the file is written or vim comes or goes, and its dropping is what
   ends a reading with no terminal.

   The row those controls sit on stays at the top of the window while the
   document runs behind it, which the stylesheet does on its own. What this file
   owes it is its height, written to the root as --bar-height so that a heading
   jumped to lands below the row rather than behind it.

   The page keeps nothing of its own. It draws what GET /doc sends and writes
   every change back through POST /api/state, so one reading and the next
   agree wherever they were opened from.

   The Edit toggle is the exception to that: it is not a setting and is stored
   nowhere. It is a fact about the reading in front of you, so it follows what
   the server says rather than leading it, and every line the server sends
   writes it again.

   sync.js runs beside this file and owns the two marks a reading with vim
   carries. One named event passes between them, mdeus:editing, dispatched here
   whenever vim comes or goes. Nothing else is shared.

   The structure this builds is written out at the top of themes.css. */

'use strict';

/* Three headings is the point at which a contents list starts to earn its
   place. Below it the button is absent rather than disabled. */
const CONTENTS_MINIMUM = 3;
/* How long a copy button says it copied before it offers to again. */
const COPIED_MS = 1500;
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
/* Whether vim is up, as the server last said. Never what this page asked for:
   opening vim takes a moment and closing it is refused outright while anything
   in vim is unwritten, so the toggle has to follow rather than lead. */
let editing = false;
let headingIds = [];
let mtime = null;
/* The source lines the top level headings start at, which is to say where every
   section the page can fold begins. Taken from the outline the server sends. */
let sectionLines = new Set();
let theme = null;
/* Whether Full width is on. Two of the three themes are drawn any differently
   for it. Null until the server has said. */
let wide = null;

function anchor() {
  /* The first block still on screen, and how far down the window it sits. A
     theme change alters every measurement on the page, so the reading
     position has to be held by a block rather than by a pixel offset.

     The control row stands over the document, so a block behind it is not on
     screen and the foot of the row is where the reading starts. The row is
     measured rather than read out of --bar-height, since where its foot lands
     moves as the page is scrolled to the very top and the height alone does not
     say that. */
  const blocks = docNode.querySelectorAll('.block');
  const barFoot = controlsNode.getBoundingClientRect().bottom;
  for (const block of blocks) {
    if (block.hidden) {
      continue; // folded away, so it has no place on the page to hold
    }
    const top = block.getBoundingClientRect().top;
    if (top >= barFoot) {
      return { start: block.dataset.start, top };
    }
  }
  return null;
}

function applyEditing(now) {
  /* Say what the server says about vim: press the toggle to match, and tell
     sync.js when the answer has moved.

     The toggle is written on every line the server sends rather than only when
     the answer changes. A press the reading could not honour, a press a vim with
     unsaved work refused, and a vim that quit of its own accord are all put
     right by the next line down the connection. */
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

function applyWide() {
  /* One class on the root, on while the toggle is pressed, off while it is not.
     The stylesheet is what decides which themes are drawn any differently for
     it. */
  document.documentElement.classList.toggle('wide', wide);
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
  /* Native controls and nothing else. The theme is a choice between three, so
     it is a dropdown. Everything else on the row is one view state that is
     either on or off, so each is a button that says whether it is pressed
     rather than a box that reads as a form waiting to be submitted.

     The Edit toggle is built only where the reading could open vim at all,
     which the server says with every document: a printed copy is answered by
     nobody and carries no toggle, and neither does a reading served where
     there is no desktop session to open vim into.

     The contents button is not built here, since whether the document has
     headings enough for one is a question every redraw asks again. It sits
     between the dropdown and Full width, and drawContents is what puts it
     there. */
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
  let button = document.getElementById('contents');
  if (!enough) {
    if (button) {
      button.remove();
    }
    return;
  }
  if (!button) {
    button = toggleButton('contents', 'Contents', contentsOpen, onContents);
    /* Put in front of the toggle that is always there rather than appended, so
       that a button coming and going with the headings of a document lands in
       the same place on the row every time. */
    controlsNode.insertBefore(button, document.getElementById('wide'));
  }
  setPressed(button, contentsOpen);
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

  /* A reading is called after the document it is showing and nothing else. The
     name is written on every draw rather than once at the start, so that
     following a link to another document takes the tab along with it. */
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
  /* Said once, when the document is first on the screen. The reading waits for
     it before starting the vim it keeps out of sight, so that a browser drawing
     a page and a gvim starting are not after the same machine at the one moment
     somebody is watching. */
  fetch('/api/drawn', { method: 'POST' }).catch(() => {});
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
     with it, so the file whose modification time is being watched moves too and
     has to be read again before the server's next word mistakes it for an
     edit. */
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

async function hold() {
  /* Hold the reading open for as long as this page is here, and listen while it
     is held.

     A reading opened from the file manager has no terminal to interrupt, so the
     page is what ends it. The page does that by asking for one thing it is
     never given: the reply's headers come back and the body never does, so the
     connection stays up until the window closes and the browser drops it, which
     is the moment the reading ends.

     What does come down it is a line whenever the file is written or vim comes
     or goes. That is why nothing here is on a timer, and it is the whole point.
     A browser slows the timers of a window that is not in front of you, and
     stops them altogether while the machine sleeps, so a page that had to ask
     would lose its reading behind its own window while somebody had it
     minimised, or sit there showing a file as it was a minute ago. Nothing is
     asked of the clock, and a connection sleeps as happily as the machine it is
     on and wakes with the first thing said down it.

     Held again if the connection ends while the reading has not, which is what
     a browser dropping an idle socket of its own accord would look like. A
     server that has stopped answering refuses the next asking, and the page
     lets the reading go rather than asking for ever. */
  let response;
  try {
    response = await fetch('/hold');
  } catch (error) {
    return; // nothing is serving, so there is no reading left to hold
  }
  if (!response.ok) {
    return; // nobody is behind this page at all, which is what a printed copy is
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let rest = '';
  try {
    for (;;) {
      const arrived = await reader.read();
      if (arrived.done) {
        break; // the reply ended, which is the connection having gone
      }
      rest += decoder.decode(arrived.value, { stream: true });
      const lines = rest.split('\n');
      /* Whatever follows the last newline is a line still on its way, so it is
         left where it is until the rest of it arrives. */
      rest = lines.pop();
      for (const line of lines) {
        await told(JSON.parse(line));
      }
    }
  } catch (error) {
    // The connection went rather than the page, so it is taken again below.
  }
  hold();
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
     time it was last written, so what the server says next is measured against
     what is on the screen. */
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
  /* After the controls are built rather than with them, so that a page
     reloaded in the middle of a session presses its toggle and tells sync.js in
     the one movement, rather than opening pressed and telling nobody. */
  applyEditing(Boolean(doc.editing));
  drawDocument();
  drawContents();
  restore(mark);
}

function measureBar() {
  /* Say how tall the control row is, for the stylesheet to hold a heading that
     far clear of it when the contents list jumps to one.

     It is asked again whenever the row changes rather than once at the start,
     since the row wraps onto a second line on a narrow window and the contents
     button comes and goes with the document being read. */
  document.documentElement.style.setProperty(
    '--bar-height',
    `${controlsNode.offsetHeight}px`
  );
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

function onEdit() {
  /* Ask for vim, or ask for vim to go. Nothing here waits for an answer and
     nothing here decides: opening vim takes a moment, and closing it is
     refused outright while anything in vim is unwritten, so what became of the
     asking comes down the held connection like every other thing this page
     knows. The toggle is not pressed here either, for the same reason: what is
     asked for is the opposite of what the server last said, and the server is
     what moves it. */
  fetch('/api/edit', {
    body: JSON.stringify({ editing: !editing }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
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

function onWide(event) {
  /* Same as a theme change: a class swap, the reading position held across it,
     and the choice written back so the next reading opens the same way. */
  const mark = anchor();
  wide = !wide;
  applyWide();
  setPressed(event.currentTarget, wide);
  restore(mark);
  saveState();
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
    body: JSON.stringify({ contents: contentsOpen, theme, wide }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function setPressed(button, on) {
  /* Say whether a toggle is on. The word is written out rather than the
     attribute being added and removed, because a toggle that is off has to say
     so: an absent aria-pressed is a plain button that carries no state at all,
     and the stylesheet draws the face off the same word. */
  button.setAttribute('aria-pressed', on ? 'true' : 'false');
}

function slug(text, used) {
  /* GitHub's own naming for a heading anchor, so a link to a section reads
     the same here as it does there. */
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
  /* The reading is taken hold of before the document is asked for, so that a
     reloaded page is holding it again within the moment rather than once it has
     drawn, which on a long document is long enough for the reading to have ended
     underneath it. */
  hold();
  await load();
  /* The document the reading opened at is the first history entry, so going
     back to it names a path like every other entry does. */
  history.replaceState({ path: doc.name }, '');
  docNode.addEventListener('click', onClick);
  /* The row is measured as this starts watching it, so nothing has to say how
     tall it was to begin with. The border box is what is watched rather than
     the default: a theme change alters the padding round the row and leaves the
     controls inside it the size they were, and that is a change in height the
     content box alone does not report. */
  new ResizeObserver(measureBar).observe(controlsNode, { box: 'border-box' });
  window.addEventListener('popstate', onPop);
  drawn();
}

function toggleButton(id, text, pressed, handler) {
  /* One control of the row: a button whose label never moves and whose pressed
     state is what says it is on. The label stays put because a label that
     flips between Contents and Hide contents describes what a click will do,
     while the face describes what is already so, and a control that does both
     at once leaves the reader working out which of the two it is looking at. */
  const button = document.createElement('button');
  button.addEventListener('click', handler);
  button.id = id;
  button.textContent = text;
  button.type = 'button';
  setPressed(button, pressed);
  return button;
}

async function told(said) {
  /* Take one line of what the server says: when the document was last written,
     and whether vim is up. The document is fetched again only where that time
     has moved, so a line carrying nothing new about the file costs nothing.

     A line arriving before the page has drawn is let go. The first of them says
     what the document reply the page is already waiting for will say, and acting
     on it would fetch the same document twice. Whatever moves after that is
     said again. */
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
