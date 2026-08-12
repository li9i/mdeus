"""
Behaviour tests for window.py. Run with: python3 test_window.py

No window is made and no vim is opened. What is tested here is the part of a
session that needs neither: how it lays its two panes out, and how it hears the
page asking for vim to go.

The panes are stand ins that say how big they are and remember what they were
asked for, since what the layout must never do is ask for something an X server
would refuse. The session itself is run without a desktop behind it, which is
the way it runs where python3-xlib is missing, and it is given a stand in for
vim, a process of its own that ends when the test lets it, and a stand in over
the call that asks vim to quit.
"""

import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import server
import vimlink
import window
from Xlib import error

ENDS_WITHIN = 3
SERVERNAME = 'MDEUSTEST'
WATCH_FOR = 1.5


class Display:
    """A stand in for the desktop, for the one call a layout makes of it."""

    def sync(self):
        """Wait for the requests above to have been made."""


class Pane:
    """A stand in for a window, which says how big it is and remembers what it was asked.

    It answers geometry in the pixels a real window would, and it is never
    asked for anything else by the layout, which is all that is tested here. A
    pane whose program has closed it refuses to answer at all, the way the X
    server refuses a question about a window that has gone.
    """

    def __init__(self, x, y, width, height, gone=False):
        self.asked = []
        self.gone = gone
        self.here = SimpleNamespace(x=x, y=y, width=width, height=height)

    def configure(self, **wanted):
        """Remember a request rather than making one."""
        self.asked.append(wanted)

    def get_geometry(self):
        """Say where this window is and how big it is, or refuse where it has gone."""
        if self.gone:
            raise error.BadDrawable.__new__(error.BadDrawable)
        return self.here


def held(reading, vim):
    """Run one session's wait on a thread of its own, and return the thread.

    The session is given no desktop and no windows, so all it does is watch the
    wish and vim. It is a daemon, since a test that leaves it stuck must fail
    rather than hang the run.
    """
    thread = threading.Thread(
        target=window.hold,
        args=(None, None, {}, None, vim, reading, threading.Event()),
        daemon=True,
    )
    thread.start()
    return thread


def opening_session():
    """Return a reading with vim up, a stand in for vim, and a way to put both away.

    The reading is one whose session has just started: vim is up and the page
    has been told so. What the wish says is the test's to set.
    """
    tree = tempfile.mkdtemp(prefix='mdeus-test-window-')
    document = Path(tree) / 'doc.md'
    document.write_text('# A document\n', encoding='utf-8')
    reading = server.Reading(document, SERVERNAME, editable=True)
    reading.editing = True
    vim = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])

    def stop():
        vim.kill()
        vim.wait()
        shutil.rmtree(tree, ignore_errors=True)

    return reading, vim, stop


def seam(at, height):
    """Return stand ins for the two windows the seam is shown and dragged by.

    The line down the join and the strip laid over it, in the places a layout
    would have left them, since a layout that touches either of them is a layout
    that has decided to move the seam.
    """
    return {'grab': Pane(at - 3, 0, 6, height), 'line': Pane(at - 1, 0, 1, height)}


def test_a_vim_pane_as_wide_as_the_window_leaves_the_panes_where_they_are():
    """A vim wider than the window it sits in is not answered with an impossible width.

    The two panes are put edge to edge by giving the browser whatever vim
    rounded off its own width, and vim answers a size of its own after the fact,
    so for a moment while a session is opening vim is the size of a pane in a
    window that has not been given its own size yet. What is left of the window
    beside vim is then nothing, or less than nothing, and a window cannot be
    that wide.

    A reading that asks anyway does not draw it wrong, it ends: the request
    cannot even be put together, so the whole reading comes down with a
    traceback and the page is left standing on the desktop with nothing behind
    it. Pressing the toggle twice quickly is enough to reach it. Nothing is laid
    out on such a turn, and the window settling on its own size lays it out
    again a moment later.
    """
    container = Pane(0, 0, 800, 600)
    panes = {'browser': Pane(0, 0, 352, 600), 'vim': Pane(352, 0, 900, 600)}
    divider = seam(352, 600)
    window.meet(Display(), container, panes, divider)
    for name, pane in dict(panes, **divider).items():
        assert pane.asked == [], (name, pane.asked)


def test_a_pane_that_has_gone_does_not_take_the_reading_with_it():
    """A layout asked for a window that has closed since is dropped, not fatal.

    Both panes belong to other programs, and the layout is asked for by an
    event that was already waiting when one of them went. Quitting vim does
    exactly that: vim's window goes, and the last thing it did on its way out
    was ask the reading to lay the panes out again.

    A question the X server refuses is refused where it was asked, so nothing
    catches it on the reading's behalf. Left alone it ends the whole reading,
    and the page is left standing on the desktop with nothing behind it: no
    vim, no toggle that does anything, and no way back but opening the document
    again.
    """
    container = Pane(0, 0, 1280, 800)
    for closed in ('browser', 'vim'):
        panes = {'browser': Pane(0, 0, 563, 800), 'vim': Pane(563, 0, 717, 800)}
        panes[closed].gone = True
        divider = seam(563, 800)
        window.meet(Display(), container, panes, divider)
        for name, pane in dict(panes, **divider).items():
            assert pane.asked == [], (closed, name, pane.asked)


def test_a_stop_asked_for_while_the_session_opens_is_still_honoured():
    """A press that lands before the session is holding still takes vim away.

    A session takes a moment to open, and the page is told vim is up as soon as
    vim is started rather than once the window is drawn, so a reader pressing
    the toggle again straight away asks for vim to go while the session is still
    opening. That asking has to survive the moment it lands in.

    A session that reads the wish as it stands and then waits for it to move
    misses this one, since it moved before the session ever looked. What that
    costs is not one press but every press after it: the page asks for the
    opposite of what the reading says it is doing, the reading goes on saying it
    is editing, so every press asks for the same thing again and nothing moves.
    The reader is left with a vim the toggle cannot close.
    """
    reading, vim, stop = opening_session()
    asked = []
    was = vimlink.quit_vim
    vimlink.quit_vim = lambda name: (asked.append(name), vim.terminate())
    try:
        reading.wanted = False
        session = held(reading, vim)
        session.join(ENDS_WITHIN)
        assert asked == [SERVERNAME], asked
        assert not session.is_alive(), 'the session went on holding a vim nobody wants'
    finally:
        vimlink.quit_vim = was
        stop()


def test_a_vim_that_heard_nothing_is_asked_again():
    """An ask that never reached vim is made again, so a press is not lost.

    A vim waiting to be answered hears nothing until it has been, and what puts a
    question up is the document being written by another program: vim asks whether
    to load it and takes the next key as the answer. A press meant to end the
    reading lands in the middle of that and goes nowhere.

    A session that asks once has thrown that press away, and what the reader is
    left with is a reading that will not close however often they press, with no
    reason given for it.
    """
    reading, vim, stop = opening_session()
    asked = []
    was = vimlink.quit_vim

    def deaf(name):
        """Stand in for a vim that hears nothing until it has been asked twice."""
        asked.append(name)
        if len(asked) < 2:
            return False
        vim.terminate()
        return True

    vimlink.quit_vim = deaf
    try:
        reading.wanted = False
        session = held(reading, vim)
        session.join(ENDS_WITHIN)
        assert asked == [SERVERNAME, SERVERNAME], asked
        assert not session.is_alive(), 'the session held a vim that heard nothing'
    finally:
        vimlink.quit_vim = was
        stop()


def test_vim_is_asked_to_go_once_however_long_it_refuses():
    """A vim with unsaved work is asked once and then left alone.

    vim refuses to quit while anything in it is unwritten, and the session goes
    on holding until it agrees. A vim that refuses has still heard the asking,
    which is what tells the session to leave it alone: asking again on every turn
    would be four asks a second for as long as the reader takes to save, each of
    them a vim client command started and waited on.
    """
    reading, vim, stop = opening_session()
    asked = []
    was = vimlink.quit_vim

    def heard(name):
        """Stand in for a vim that hears the asking and refuses to go."""
        asked.append(name)
        return True

    vimlink.quit_vim = heard
    try:
        reading.wanted = False
        session = held(reading, vim)
        time.sleep(WATCH_FOR)
        assert asked == [SERVERNAME], asked
        assert session.is_alive(), 'the session let go of a vim that never agreed to go'
        vim.terminate()
        session.join(ENDS_WITHIN)
        assert not session.is_alive(), 'the session outlived the vim holding it'
        assert asked == [SERVERNAME], asked
    finally:
        vimlink.quit_vim = was
        stop()


if __name__ == '__main__':
    tests = sorted(k for k in dict(globals()) if k.startswith('test_'))
    failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f'pass  {name}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL  {name}\n        {e}')
    for _ in range(50):
        if threading.active_count() == 1:
            break
        time.sleep(0.02)
    if threading.active_count() != 1:
        failed += 1
        print(f'FAIL  {threading.active_count() - 1} threads were left running')
    print(f'\n{len(tests)} tests, {failed} failed')
    sys.exit(1 if failed else 0)
