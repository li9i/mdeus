/* The browser half of the sync between the page and vim. Only a reading with
   vim beside it loads this file.

   Double clicking a block sends vim to the first source line that block was
   built from, and double clicking in vim brings the page over the same way.
   One gesture, the same in both halves. Single click is left to whichever
   half it happened in, so selecting a paragraph, following a link and putting
   the vim cursor somewhere all cost nothing.

   In the other direction the page asks the server where the vim cursor is and
   marks the block whose lines contain it.

   The page stays where it is put. The rule is moved onto the marked block
   wherever that block happens to be, and one thing alone scrolls the page: a
   click in vim, which is how you ask for the page to be brought over. Cursors
   arriving any other way move the rule and nothing else, since vim moves its
   cursor as its window scrolls and a page that followed would be dragged
   about by the wheel and by ctrl-d and ctrl-f.

   It runs beside page.js, which draws the document and owns everything else
   on the page. Every name here is its own. */

'use strict';

const CURSOR_MS = 200;
/* How long the ground on the block stays before it is let go. The fade itself
   is in bmvim.css. */
const FLASH_MS = 1000;

const pane = document.querySelector('.doc');

/* How many clicks in vim the page has already followed. A click there is the
   one thing that brings the page along, and the throttled report of the same
   line follows a moment later, so what is watched is a count rather than a
   flag the report behind it would take back. Nothing has been followed until
   the first reply has been read, and that reply is not a click. */
let clicksAt = null;
let flashTimer = null;
/* The line the last reply named, so a reply saying the cursor has not moved
   costs nothing more than reading it. */
let lineAt = null;
/* The first source line of the block the rule is on. Held as a line rather
   than as an element because page.js rebuilds the document on every redraw,
   which throws away the element but not the line it came from. */
let ruleAt = null;

function begin() {
  /* Both directions of the sync, started together. The double click is
     listened for on the pane rather than on each block, because page.js builds
     the blocks afresh on every redraw and a handler on one would go with it. */
  pane.addEventListener('dblclick', onBlockDouble);
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
  /* The ground on the block that was pointed at. One block carries it at a
     time, and pointing at another starts the second over. */
  const lit = pane.querySelector('.bmvim-click');
  if (lit) {
    lit.classList.remove('bmvim-click');
  }
  window.clearTimeout(flashTimer);
  block.classList.add('bmvim-click');
  flashTimer = window.setTimeout(() => block.classList.remove('bmvim-click'), FLASH_MS);
}

function markCursor(line, clicked) {
  /* Move the rule to the block holding the cursor.

     A cursor put where it is by a double click in vim is the one that brings
     the page with it. Somebody has pointed at a block, and the page goes to it
     however near or far it is and whether or not it was already in front of
     them. Every other cursor moves the rule and nothing else, so a document
     being scrolled through or typed in stays where its reader left it.

     A redraw arrives here as the same line in a fresh element, so the rule is
     put back without the page moving.

     The two halves fold on their own, so the block the cursor is in may be
     one the page has folded away. The heading of the folded section stands in
     for it, since that is all the page is showing of it. */
  const block = shownFor(blockForLine(line));
  const ruled = pane.querySelector('.bmvim-cursor');
  if (ruled && ruled !== block) {
    ruled.classList.remove('bmvim-cursor');
  }
  if (!block) {
    ruleAt = null;
    return;
  }
  block.classList.add('bmvim-cursor');
  ruleAt = Number(block.dataset.start);
  if (clicked) {
    show(block);
  }
}

function onBlockDouble(event) {
  /* Two clicks on a block send vim to the line that block starts at. Both ends
     of the block go with the message, since the page is the only half that
     knows them and vim lights the whole of what was pointed at rather than its
     first line.

     A link is followed by the first of the two clicks and a copy button copies
     on it, so neither of those ever reaches this. A block with a link in it is
     pointed at by double clicking the words around the link.

     The two clicks take a word as a selection on the way through, and a
     document that highlights a word wherever you point at it reads as though
     something were being chosen. */
  const block = event.target.closest('.block');
  if (!block) {
    return;
  }
  window.getSelection().removeAllRanges();
  flash(block);
  fetch('/api/jump', {
    body: JSON.stringify({
      last: Number(block.dataset.end),
      line: Number(block.dataset.start),
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  }).catch(() => {});
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
    /* A cursor sitting still is what a reading looks like most of the time, and
       the same line arrives five times a second while it does. Nothing is done
       for one of those, unless the page has been redrawn underneath it and the
       rule went with the old document. */
    const clicked = clicksAt !== null && where.clicks !== clicksAt;
    if (clicked || where.line !== lineAt || !ruleStands()) {
      markCursor(where.line, clicked);
    }
    lineAt = where.line;
  }
  clicksAt = where.clicks;
}

function ruleStands() {
  /* Whether the rule is still on the block the last report put it on. A redraw
     builds the document again from scratch and the rule goes with the elements
     it was on, so this is what tells a report of an unchanged line that there
     is work to do after all. */
  const ruled = pane.querySelector('.bmvim-cursor');
  return ruled === null ? ruleAt === null : Number(ruled.dataset.start) === ruleAt;
}

function show(block) {
  /* Put the block a quarter of the way down the window, so the lines around
     the cursor are in view rather than the cursor sitting on the last row. */
  window.scrollBy(0, block.getBoundingClientRect().top - window.innerHeight / 4);
}

function shownFor(block) {
  /* The block to mark in place of one the page has folded away. A folded
     section shows nothing but its heading, and the heading is the block
     before every one that went with it. */
  for (let shown = block; shown; shown = shown.previousElementSibling) {
    if (shown.classList.contains('block') && !shown.hidden) {
      return shown;
    }
  }
  return block;
}

begin();
