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
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import server
import vimlink
import window
from Xlib import X, error

ENDS_WITHIN = 3
SERVERNAME = 'MDEUSTEST'
WATCH_FOR = 1.5


class Display:
    """A stand in for the desktop, for the one call a layout makes of it."""

    def sync(self):
        """Wait for the requests above to have been made."""


class Dragging(Display):
    """A stand in for the desktop with a drag already waiting in it.

    The events a drag reads are all queued before it starts, which is the state
    a reading is really in a moment into a violent drag: the pointer has said
    where it is many times over while the panes were still being resized to
    answer the first of them.
    """

    def __init__(self, events, edge=0):
        self.edge = edge
        self.events = list(events)

    def next_event(self):
        """Take the event that has waited longest."""
        return self.events.pop(0)

    def pending_events(self):
        """Say how many are still waiting."""
        return len(self.events)

    def screen(self):
        """Answer for the root window, which is asked where the container is."""
        return SimpleNamespace(
            root=SimpleNamespace(
                translate_coords=lambda window, x, y: SimpleNamespace(x=self.edge)
            )
        )

    def ungrab_pointer(self, when):
        """Give the pointer back, as the end of a drag does."""


class Desktop(Display):
    """A stand in for the desktop with one window on it, listed and named.

    Enough of a desktop for the asking a reading makes of it as it ends: the
    list of windows it is managing, the atoms the ask is written in, and the
    connection being closed afterwards. The atoms are numbers, since the ask is
    a real X message and a real one is packed as it is made.
    """

    def __init__(self, page):
        self.atoms = []
        self.closed = False
        self.page = page

    def close(self):
        """Give the connection back, as a reading does once it has asked."""
        self.closed = True

    def create_resource_object(self, kind, xid):
        """Answer for the one window on this desktop."""
        return self.page

    def intern_atom(self, name):
        """Return a number for an atom, and remember which name it stands for."""
        if name not in self.atoms:
            self.atoms.append(name)
        return self.atoms.index(name) + 1

    def named(self, atom):
        """Return the name the number above was given for."""
        return self.atoms[atom - 1]

    def screen(self):
        """Answer for the root window, which is asked what the desktop is managing."""
        listed = SimpleNamespace(value=[self.page.id])
        return SimpleNamespace(
            root=SimpleNamespace(get_full_property=lambda atom, kind: listed)
        )


class Page:
    """A stand in for the page's window, which is asked to close and then goes.

    It answers the two questions a close asks of it, what it is called and
    whether it is still there, and it remembers the message rather than sending
    one. The window goes as the ask arrives, which is a browser closing a window
    it was asked to close.
    """

    def __init__(self, servername):
        self.asked = []
        self.id = 42
        self.servername = servername

    def __index__(self):
        """Answer as the window's own number, which is how a message names it."""
        return self.id

    def get_geometry(self):
        """Say the window is there until it has been asked to go, then refuse."""
        if self.asked:
            raise error.BadDrawable.__new__(error.BadDrawable)
        return SimpleNamespace(x=0, y=0, width=800, height=600)

    def get_wm_class(self):
        """Say what a browser calls a window it opened for one page."""
        return ('mdeus', f'127.0.0.1__8766_{self.servername}')

    def send_event(self, event):
        """Remember the message rather than making one."""
        self.asked.append(event)


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

    def grab_pointer(self, *asked):
        """Take the pointer, as the strip does for as long as a drag lasts."""


class Screened(Display):
    """A stand in for the desktop with a colour to paint a pane's ground with."""

    def screen(self):
        """Answer for the screen, which is asked what its white is."""
        return SimpleNamespace(white_pixel=0xFFFFFF)


class Taken:
    """A stand in for another program's window, on its way into the container.

    It answers what taking a window in asks of it, and remembers what it was
    asked in the order it was asked, since the order is half of what taking a
    window in has to get right.
    """

    def __init__(self):
        self.asked = []
        self.id = 7

    def change_attributes(self, **wanted):
        """Take the ground the pane is painted on until its program draws again."""
        self.asked.append('attributes')

    def change_save_set(self, mode):
        """Take the reading's word that this window is to outlive the reading."""
        self.asked.append(('save set', mode))

    def configure(self, **wanted):
        """Take a request for the size and place of the pane."""
        self.asked.append('configure')

    def get_geometry(self):
        """Say how deep the window draws, which is what its white is worked out from."""
        return SimpleNamespace(x=0, y=0, width=800, height=600, depth=24)

    def grab_button(self, *asked):
        """Take a click the session wants to see before the pane does."""
        self.asked.append('grab')

    def map(self):
        """Put the window up where it now is."""
        self.asked.append('map')

    def reparent(self, container, x, y):
        """Take the window into the container."""
        self.asked.append('reparent')


@contextmanager
def a_split_of(share):
    """Hold the seam at this share of the window for as long as the test runs.

    Where a drag leaves the seam is stored under the document it was dragged on,
    for the next reading of that document to open at, and a test is not a
    reading: it says where the seam started, keeps its own dragging out of the
    stored settings, and puts both back afterwards.
    """
    was, stored = window.browser_share, window.save_split
    window.browser_share = share
    window.save_split = lambda document, left: None
    try:
        yield
    finally:
        window.browser_share = was
        window.save_split = stored


def held(reading, vim, ending=None):
    """Run one session's wait on a thread of its own, and return the thread.

    The session is given no desktop and no windows, so all it does is watch the
    wish and vim. It is a daemon, since a test that leaves it stuck must fail
    rather than hang the run.

    The flag saying the whole reading is to end is the test's to hold where the
    test cares what the session left it at, and the session's own otherwise.
    """
    thread = threading.Thread(
        target=window.hold,
        args=(None, None, {}, None, vim, reading, ending or threading.Event()),
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


def test_a_pane_taken_in_is_handed_back_to_the_desktop_if_the_reading_dies():
    """A window taken into the container is put in the X server's save set.

    Both panes belong to other programs and neither window is the reading's to
    destroy. A window inside another program's window goes when that program
    does, so a reading killed outright, or one that falls over, would take the
    browser's window and the vim beside it with it, and whatever is unwritten in
    that vim with them. That is the one promise a session makes: nothing is
    taken away from under unsaved work.

    A window in the save set is handed back out to the desktop instead, where it
    stands as an ordinary window of its own, which is what the browser and vim
    both survive the reading by.
    """
    taken = Taken()
    window.put_in(Screened(), None, taken, (0, 0, 800, 600))
    assert ('save set', X.SetModeInsert) in taken.asked, taken.asked
    order = [what for what in taken.asked if what in ('reparent', 'map')]
    kept = taken.asked.index(('save set', X.SetModeInsert))
    assert order == ['reparent', 'map'], taken.asked
    assert kept > taken.asked.index('reparent'), taken.asked


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


def test_a_drag_lays_the_panes_out_where_the_pointer_ended_and_nowhere_else():
    """A drag answers where the pointer is now, not every place it has been.

    A pointer says where it is far oftener than a browser and a vim can be
    resized to answer it, so the moves pile up while the panes are still
    answering the first of them. A reading that takes them one at a time lays
    the panes out for every place the pointer passed through, each layout being
    two other programs asked to redraw a whole window, and the seam falls
    further behind the hand the harder it is dragged. The reader drags a little
    and waits for the reading to catch up.

    Only the last of them says anything about where the seam is wanted, so the
    rest are read and dropped, and the panes are laid out once.
    """
    container = Pane(0, 0, 1000, 600)
    panes = {'browser': Pane(0, 0, 500, 600), 'vim': Pane(500, 0, 500, 600)}
    divider = seam(500, 600)
    moves = [SimpleNamespace(type=X.MotionNotify, root_x=x) for x in range(501, 701)]
    d = Dragging(moves + [SimpleNamespace(type=X.ButtonRelease)])
    reading = SimpleNamespace(current='doc.md')
    with a_split_of(0.5):
        window.drag(d, container, panes, divider, SimpleNamespace(time=0), reading)
    assert panes['vim'].asked == [{'x': 700, 'y': 0, 'width': 300, 'height': 600}], (
        panes['vim'].asked
    )
    assert panes['browser'].asked == [{'x': 0, 'y': 0, 'width': 700, 'height': 600}], (
        panes['browser'].asked
    )


def test_a_drag_puts_the_panes_edge_to_edge_once_however_often_they_answer():
    """The panes saying how big they settled on are answered together, not each in turn.

    One layout tells four windows where to go and hears back from every one of
    them, and each of those answers arriving on its own would be another round
    of asking both panes their size and moving them to meet. That is the same
    work done four times over for one move of the seam.
    """
    container = Pane(0, 0, 1000, 600)
    panes = {'browser': Pane(0, 0, 500, 600), 'vim': Pane(500, 0, 495, 600)}
    divider = seam(500, 600)
    settled = [SimpleNamespace(type=X.ConfigureNotify) for _ in range(4)]
    d = Dragging(settled + [SimpleNamespace(type=X.ButtonRelease)])
    reading = SimpleNamespace(current='doc.md')
    with a_split_of(0.5):
        window.drag(d, container, panes, divider, SimpleNamespace(time=0), reading)
    assert panes['vim'].asked == [{'x': 505}], panes['vim'].asked
    assert panes['browser'].asked == [{'width': 505}], panes['browser'].asked


def test_a_second_press_asks_a_vim_that_refused_the_first():
    """A vim that refused one press is asked again by the next.

    vim refuses to go while anything in it is unwritten, and it has heard the
    asking when it refuses, which is what tells a session to stop asking. The
    reader then writes their work and presses the box again, meaning exactly
    what they meant the first time.

    A session that took the first press as the whole of the asking leaves them
    with a box that does nothing at all from then on, and a reading that will
    only close by quitting vim by hand.
    """
    reading, vim, stop = opening_session()
    asked = []
    was = vimlink.quit_vim

    def refuses(name):
        """Stand in for a vim that hears both asks and goes on the second."""
        asked.append(name)
        if len(asked) > 1:
            vim.terminate()
        return True

    vimlink.quit_vim = refuses
    try:
        reading.wanted = False
        session = held(reading, vim)
        time.sleep(WATCH_FOR)
        assert asked == [SERVERNAME], asked
        assert session.is_alive(), 'the session let go of a vim that refused'
        reading.ask(False)
        session.join(ENDS_WITHIN)
        assert asked == [SERVERNAME, SERVERNAME], asked
        assert not session.is_alive(), 'the second press was thrown away'
    finally:
        vimlink.quit_vim = was
        stop()


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


def test_a_reading_ended_in_the_terminal_takes_its_page_with_it():
    """Ctrl-c on a reading that is only the page closes the page's window too.

    The window is the browser's and not the reading's, so nothing about the
    command ending asks it to go, and a reading that does not ask leaves a
    window standing on the desktop with nothing behind it: the document as it
    was last drawn, no redraw and no Edit, and no way to tell it apart from a
    reading still running.

    The asking is the one a close button makes, since the window belongs to a
    browser that may have other windows open and ending the process behind it
    would take those with it.
    """
    page = Page(SERVERNAME)
    desktop = Desktop(page)
    was = window.x_display
    window.x_display = lambda: desktop
    try:
        window.stop_page(SERVERNAME)
    finally:
        window.x_display = was
    assert len(page.asked) == 1, page.asked
    message = page.asked[0]
    assert desktop.named(message.client_type) == 'WM_PROTOCOLS', message.client_type
    wanted = desktop.named(message.data[1][0])
    assert wanted == 'WM_DELETE_WINDOW', wanted
    assert desktop.closed, 'the reading left its connection to the desktop open'


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


def test_vim_leaving_on_a_write_and_quit_takes_the_reading_with_it():
    """A vim that said goodbye on its way out ends the reading, and one that did not does not.

    Both look the same from here: a process that has stopped. The reader means
    quite different things by them, though, and the reading has one page's
    window to close or to hand back on the strength of which it was. So vim says
    which before it goes, and the session reads that once vim has gone.

    A session that never looked would send every reader who typed a write and
    quit back to a page they had finished with, and one that read it the other
    way round would take the whole reading away from a reader who only wanted
    vim gone.
    """
    for said, wanted in ((False, False), (True, True)):
        reading, vim, stop = opening_session()
        ending = threading.Event()
        try:
            reading.ends = said
            session = held(reading, vim, ending)
            vim.terminate()
            session.join(ENDS_WITHIN)
            assert not session.is_alive(), 'the session outlived the vim holding it'
            assert ending.is_set() == wanted, (said, ending.is_set())
        finally:
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
