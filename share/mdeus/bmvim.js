/* The browser half of the sync between the page and vim. Only a reading with
   vim beside it loads this file.

   Clicking a block sends vim to the first source line that block was built
   from. In the other direction the page asks the server where the vim cursor
   is and marks the block whose lines contain it.

   The page moves as little as it can. The rule is put on the marked block
   wherever that block happens to be, and the page follows the cursor only on
   a far jump. Anything more eager drags the document about under someone who
   is reading or typing in the other window.

   It runs beside page.js, which draws the document and owns everything else
   on the page. Every name here is its own. */

'use strict';

const CURSOR_MS = 200;
/* How long the clicked ground stays before it is let go. The fade itself is
   in bmvim.css. */
const FLASH_MS = 1000;

const pane = document.querySelector('.doc');

/* How many clicks in vim the page has already followed. A click there is a
   jump the page goes to whatever the distance, and the throttled report of the
   same line follows a moment later, so what is watched is a count rather than
   a flag the report behind it would take back. Nothing has been followed until
   the first reply has been read, and that reply is not a click. */
let clicksAt = null;
let flashTimer = null;
/* The first source line of the block the rule is on. Held as a line rather
   than as an element because page.js rebuilds the document on every redraw,
   which throws away the element but not the line it came from. */
let ruleAt = null;

function begin() {
  /* Both directions of the sync, started together. The click is listened for
     on the pane rather than on each block, because page.js builds the blocks
     afresh on every redraw and a handler on one would go with it. */
  pane.addEventListener('click', onBlockClick);
  window.setInterval(pollCursor, CURSOR_MS);
}

function blockForLine(line) {
  /* The block whose source lines contain this one. Blocks are in source
     order, so the search stops at the first one starting past the line. A
     line in the blank space between two blocks belongs to the one above it,
     which is where vim leaves the cursor when it lands on a blank line. */
  let found = null;
  for (const block of pane.querySelectorAll('.block')) {
    if (Number(block.dataset.start) > line) {
      break;
    }
    found = block;
    if (Number(block.dataset.end) >= line) {
      break;
    }
  }
  return found;
}

function flash(block) {
  /* The ground on the block that was clicked. One block carries it at a
     time, and clicking again starts the second over. */
  const lit = pane.querySelector('.bmvim-click');
  if (lit) {
    lit.classList.remove('bmvim-click');
  }
  window.clearTimeout(flashTimer);
  block.classList.add('bmvim-click');
  flashTimer = window.setTimeout(() => block.classList.remove('bmvim-click'), FLASH_MS);
}

function markCursor(line, clicked) {
  /* Move the rule to the block holding the cursor, and let the page follow if
     the cursor has gone far enough to be worth following.

     A redraw arrives here as the same line in a fresh element, so the rule is
     put back without the page moving. Moving the cursor about inside one
     block arrives as a new line in the same block, which is the case that
     must never scroll: someone is typing.

     A cursor put where it is by a click in vim is the one case with no
     distance to weigh. Somebody has pointed at a block and the page goes to
     it, near or far and whether or not it was already in front of them. */
  const block = blockForLine(line);
  const ruled = pane.querySelector('.bmvim-cursor');
  if (ruled && ruled !== block) {
    ruled.classList.remove('bmvim-cursor');
  }
  if (!block) {
    ruleAt = null;
    return;
  }
  block.classList.add('bmvim-cursor');
  const begins = Number(block.dataset.start);
  if (clicked) {
    ruleAt = begins;
    show(block);
  } else if (begins !== ruleAt) {
    ruleAt = begins;
    reveal(block, ruled);
  }
}

function onBlockClick(event) {
  /* A link is a link and a copy button copies. Anything else in a block is a
     jump to the line that block starts at. The name keeps clear of the click
     handler the reader page installs on this same element, since the two
     scripts share a scope. */
  if (event.target.closest('a, .copy')) {
    return;
  }
  const block = event.target.closest('.block');
  if (!block) {
    return;
  }
  flash(block);
  fetch('/api/jump', {
    body: JSON.stringify({ line: Number(block.dataset.start) }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
}

function onScreen(box) {
  /* A block is on the screen when the whole of it is in the window. A block
     taller than the window can never be, so it counts as on the screen while
     it fills the window instead. Without that it would be reported off the
     screen even with the cursor in the middle of it. */
  const height = window.innerHeight;
  if (box.height >= height) {
    return box.top <= 0 && box.bottom >= height;
  }
  return box.top >= 0 && box.bottom <= height;
}

async function pollCursor() {
  /* vim reports its cursor by starting a process rather than by waiting on
     one, so nothing can push the line to the page. The server holds whatever
     vim last sent and the page comes and asks for it. */
  let where;
  try {
    const response = await fetch('/api/cursor');
    where = await response.json();
  } catch (error) {
    return; // the server has stopped answering and the reading is over
  }
  if (typeof where.line === 'number') {
    markCursor(where.line, clicksAt !== null && where.clicks !== clicksAt);
  }
  clicksAt = where.clicks;
}

function reveal(block, from) {
  /* Bring the block into view, but only where it is worth moving the page for.

     Two things have to be true first. The block must be off the screen, since
     one the reader can already see does not need bringing to them. And the
     cursor must have come more than a window height to reach it.

     That second test is what keeps the page still. vim moves its cursor when
     you scroll its window, once the cursor would be scrolled out of it, so
     the wheel and ctrl-d and ctrl-f all report a moving cursor and a page
     that followed every report would be dragged along by them. A search, a G
     or a :42 lands somewhere else entirely, and that is the move worth
     following. One window height of this page is the line between the two.

     `from` is the block the rule was on. Both boxes are measured at the same
     scroll position, so the difference between their tops is the distance
     through the document. There is no `from` on the first report of a
     reading, or on the first after a link has been followed, and the page
     goes to the cursor: the reader has not put the page anywhere yet. */
  const box = block.getBoundingClientRect();
  if (onScreen(box)) {
    return;
  }
  if (from && Math.abs(box.top - from.getBoundingClientRect().top) <= window.innerHeight) {
    return;
  }
  show(block);
}

function show(block) {
  /* Put the block a quarter of the way down the window, so the lines around
     the cursor are in view rather than the cursor sitting on the last row. */
  window.scrollBy(0, block.getBoundingClientRect().top - window.innerHeight / 4);
}

begin();
