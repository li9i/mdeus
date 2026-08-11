"""
One editing session: the window both halves of a reading are drawn in.

A reading that is editing is two programs, a browser and gvim, and the desktop
would ordinarily give each of them a window of its own. This makes one window
and puts both inside it, so that the reading is one entry on the panel, is
moved as one, resized as one and closed as one.

An editing session begins in the middle of a reading rather than at the start
of one. The page is usually already open in a window of its own when the Edit
box is ticked, so that window is taken in where it stands, and a session opened
with --edit is the same work in the other order: the container is made first
and the page asked for after it, so nothing of the reading is seen half drawn.
Either way the session ends by putting the container away again, and the page's
window is either handed back to the desktop or asked to close, according to
whether the reading is going back to viewing or ending altogether.

Taking a window off the window manager has an order to it. Reparenting a window
the manager is still managing loses a race: the manager sees its client leave
the frame it drew, runs the same tidying up it runs for a window that has gone,
and that tidying up hands the client back to the root window. So each window is
withdrawn first, in the way the ICCCM asks for, and reparented only once the
manager has let go of it. Handing one back is the same journey the other way,
and there the map is what asks the manager to take charge again.

Nothing manages the two windows once they are inside, and the work a window
manager would have done falls here. The panes are laid out again whenever the
container is resized, the seam between them is dragged with the pointer, and
the keyboard is handed from one pane to the other on a click, which is how the
desktop is set to hand it between windows. The title is the same sort of work:
the desktop can see none of the panes, so the reading takes the page's own
title for its own, and following a link in the browser renames the window on
the panel with it.

Without python3-xlib there is no container to be made, so vim opens as an
ordinary window of its own beside the page. It says so and carries on.
"""

import os
import select
import subprocess
import sys
import threading
import time
import webbrowser

import vimlink
from browser import app_command, browser_path
from server import NAME, TITLE
from state import MAX_SPLIT, MIN_SPLIT, load_split, save_split

try:
    from PIL import Image
except ImportError:  # python3-pil is not installed
    Image = None

try:
    from Xlib import X, Xatom, Xutil, display, error, protocol
except ImportError:  # python3-xlib is not installed
    X = Xatom = Xutil = display = error = protocol = None

# How long to wait for the browser to take its window away once it has been
# asked to, in seconds.
BROWSER_STOP = 5
# How wide a strip of the reading you can take hold of the seam by. It lies
# over the join rather than between the panes, so the two go on meeting exactly
# and the reading looks no different for being draggable.
DIVIDER = 6
# The glyph in the cursor font that says a thing can be dragged sideways, and
# the glyph after it, which is its mask.
DIVIDER_CURSOR = 108
# The image the reading wears on the panel and on its title bar, in the two
# sizes it ships in. It is the same image the desktop entry names, and it sits
# beside this file inside the package, so a stowed package and a checkout of it
# both find it.
ICONS = tuple(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'icons', 'hicolor', f'{size}x{size}', 'apps', 'mdeus.png',
    )
    for size in (24, 128)
)
IN_A_TAB = (
    f'{NAME}: the page is in a tab rather than a window of its own, so vim opens\n'
    f'{" " * len(NAME)}  beside it wherever the desktop puts it'
)
# How long to go on waiting for the window manager to take charge of a window
# handed back to it, in seconds.
MANAGE_WAIT = 5
# What a request to move and resize a window carries: that all four of the
# position and the size are given, and that an ordinary application is asking.
# The gravity goes in the low byte and is the caller's, since it is what says
# whether the numbers are the window's own or its frame's.
MOVERESIZE = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | (1 << 12)
# How often the two programs are looked in on, in seconds.
POLL = 0.25
# What vim is sourced from for as long as a session lasts. It sits beside this
# file inside the package, so a stowed package and a checkout of it both find it.
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cursor.vim')
SETTLE_TRIES = 20
SETTLE_WAIT = 0.05
UNPLACED = f'{NAME}: vim is in a window of its own, wherever the desktop put it'
# How long to go on waiting for a program to put its window up, in seconds.
WINDOW_WAIT = 15
# How long to go on waiting for the window manager to let go of a window.
WITHDRAW_WAIT = 5

# The share of the window the browser pane takes. A session opens at whatever
# the last drag of the divider left, and every layout is measured from this, so
# it is kept here rather than handed down through the events that read it. It is
# read again as each session begins, since a session may start an hour into a
# reading and another reading may have moved the seam in the meantime.
browser_share = load_split()


def active_window(d):
    """Return the window the desktop has in front, or None where it does not say."""
    active = d.screen().root.get_full_property(
        d.intern_atom('_NET_ACTIVE_WINDOW'), Xatom.WINDOW
    )
    return active.value[0] if active and len(active.value) else None


def adopt(d, container, window, box):
    """Take a window off the window manager and put it in the container.

    The click that would ordinarily give a window the keyboard is asked for
    here as well, since the two panes are one window as far as the desktop is
    concerned and nothing else is left to hand the keyboard between them.

    White is put under the pane on the way in, for the moment between the
    window arriving and the program drawing in it again. A window that has been
    unmapped and mapped somewhere else holds nothing, and until its program
    catches up what shows is whatever the X server was left with, which is
    black. A browser takes seconds to draw its first page, and those are seconds
    of a black rectangle where the reading is. The container is white for the
    same reason, so a pane arriving over it looks like no arrival at all.
    """
    withdraw(d, window)
    x, y, width, height = box
    window.change_attributes(background_pixel=white(d, window))
    window.reparent(container, x, y)
    window.configure(x=x, y=y, width=width, height=height)
    window.map()
    for button in (1, 2, 3):
        for modifiers in locked():
            # Synchronous, so that the click can be looked at and then let
            # through to the pane it was meant for. The wheel is left alone,
            # since a pane scrolled through is a pane already under the pointer.
            window.grab_button(
                button, modifiers, False, X.ButtonPressMask,
                X.GrabModeSync, X.GrabModeAsync, X.NONE, X.NONE,
            )
    d.sync()


def browser_command(browser, url, box, origin):
    """Return the command that asks for the page in the window it is to fill.

    The asking itself is app_command()'s, and what is added here is where the
    window is going to end up. A running browser pays no attention to that and
    puts the window where it likes, since the window is its own; it counts only
    where the reading has to start a browser because none was running, and there
    it saves the window a visible jump on its way into the container.
    """
    command = app_command(browser, url)
    if box is not None:
        x, y, width, height = box
        command.append(f'--window-position={origin[0] + x},{origin[1] + y}')
        command.append(f'--window-size={width},{height}')
    return command


def client_list(d):
    """Return the windows the desktop says it is managing."""
    listed = d.screen().root.get_full_property(
        d.intern_atom('_NET_CLIENT_LIST'), Xatom.WINDOW
    )
    return list(listed.value) if listed else []


def close_page(d, window):
    """Ask the browser to take the page's window away, and wait until it has.

    The window is the browser's and not the reading's, since the reading borrowed
    a browser rather than starting one, so it is asked in the way the close
    button on a window asks. Ending the process behind it would take every other
    window in that browser with it, and destroying the window outright would
    take it away from under a browser still holding it.
    """
    window.send_event(protocol.event.ClientMessage(
        window=window, client_type=d.intern_atom('WM_PROTOCOLS'),
        data=(32, [d.intern_atom('WM_DELETE_WINDOW'), X.CurrentTime, 0, 0, 0]),
    ))
    d.sync()
    deadline = time.monotonic() + BROWSER_STOP
    while time.monotonic() < deadline:
        try:
            window.get_geometry()
        except Exception:
            return
        time.sleep(SETTLE_WAIT)


def divider_at(divider, seam, height):
    """Lay the strip you drag over the seam between the two panes.

    It is put on top every time, since a pane mapped into the container after
    it would otherwise sit over it and take the clicks meant for it.
    """
    divider.configure(
        x=seam - DIVIDER // 2, y=0, width=DIVIDER, height=height,
        stack_mode=X.Above,
    )


def drag(d, container, panes, divider, press):
    """Move the seam with the pointer until the button goes up.

    The pointer is grabbed for as long as the drag lasts, because the strip is
    dragged out from under the pointer on the very first move and would stop
    hearing about it otherwise.

    The panes are laid out again on every move rather than at the end, since a
    seam that arrives where the pointer left it says nothing about where it
    will land: vim settles on whole character columns, so the reading snaps to
    the nearest one and dragging is how you see which. Where it was left is
    stored, so the next reading opens at the same split.
    """
    global browser_share
    divider.grab_pointer(
        False, X.PointerMotionMask | X.ButtonReleaseMask,
        X.GrabModeAsync, X.GrabModeAsync, X.NONE, X.NONE, press.time,
    )
    # The window cannot be resized or moved while the pointer is held, so both
    # are read once rather than on every move. Every move carries where the
    # pointer is on the screen, and the left edge is what turns that into where
    # it is across the reading.
    width = container.get_geometry().width
    edge = d.screen().root.translate_coords(container, 0, 0).x
    try:
        while True:
            event = d.next_event()
            if event.type == X.ButtonRelease:
                break
            if event.type == X.ConfigureNotify:
                # vim answering with the width it settled on. The browser is
                # given the remainder now rather than after the drag, so the
                # seam stays under the pointer as it moves.
                meet(d, container, panes, divider)
            elif event.type == X.MotionNotify:
                here = (event.root_x - edge) / width
                wanted = min(MAX_SPLIT, max(MIN_SPLIT, here))
                # Only where the seam would actually move. A pointer crossing a
                # pixel that rounds to the column it is already on asks for a
                # layout that changes nothing and costs both panes a redraw.
                if round(wanted * width) != round(browser_share * width):
                    browser_share = wanted
                    layout(d, container, panes, divider)
    finally:
        d.ungrab_pointer(X.CurrentTime)
        d.sync()
    save_split(browser_share)


def edit(reading, url, ending, opening=False, app_window=True):
    """Hold one editing session up, and say whether the reading is to end with it.

    The session makes the container, puts the page and gvim inside it, holds
    the reading up for as long as vim is there, and puts the container away
    again afterwards. It returns True where what ended it was somebody asking
    for the whole reading to end, and False where the reading is going back to
    viewing with the page alone.

    Two ways in and one way through. Pressing the Edit toggle arrives here with the
    page's window already on the desktop, and it is taken in where it stands.
    Asking for --edit arrives here with no page yet, and the container is made
    first and the page asked for after it, so that neither half is seen
    standing on the desktop on its way in. Both funnel into the same loop,
    which takes each window in as it appears in the desktop's list and finds
    one that is already there on its first turn.

    The split is read here rather than at import, because a session may begin
    an hour into a reading and another reading may have moved the seam since.

    Where the page's window was standing before the session took it is noted on
    the way in, so that it can be put back exactly there on the way out. The
    container fills the work area, so a page read in a small window grows as it
    goes in, and it should shrink again as it comes out.
    """
    global browser_share
    browser_share = load_split()
    # Whatever brought us here, editing is what is wanted from this moment, so
    # that the box being unticked later reads as the change it is.
    reading.wanted = True
    if not app_window:
        print(IN_A_TAB, flush=True)
    d = x_display() if app_window else None
    container = make_container(d, reading.current.name) if d is not None else None
    if app_window and container is None:
        print(UNPLACED, flush=True)

    if container is None:
        boxes, divider, origin = (None, None), None, (0, 0)
    else:
        here = container.get_geometry()
        boxes = pane_boxes(here.width, here.height)
        divider = make_divider(d, container)
        where = d.screen().root.translate_coords(container, 0, 0)
        origin = (where.x, where.y)

    # Where the page's window stands now, read before anything is done to it. A
    # session opened with --edit has no page yet, so there is nowhere for one to
    # go back to and the container's own place stands in.
    was_at = None
    if container is not None and app_window and not opening:
        standing = page_window(d, client_list(d), reading.servername)
        if standing is not None:
            was_at = where_of(d, standing)

    if opening:
        open_page(url, reading.servername, app_window, boxes[0], origin)
    vim = subprocess.Popen(
        vim_command(reading.servername, reading.current, boxes[1], origin),
        env=dict(
            os.environ,
            MDVIEW_LINK=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vimlink.py'),
            MDVIEW_URL=url,
        ),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Said as soon as vim is started rather than once its window is in, so that
    # the routes are open for the cursor vim reports the moment it has read the
    # document, and the box on the page ticks without waiting for the layout.
    reading.editing = True

    panes = {}
    try:
        if container is not None:
            # vim is the reading's own and is known by its process. The page's
            # window is somebody else's and is known by the name the reading
            # served it under.
            wanted = [('vim', lambda listed: window_of(d, listed, vim.pid), boxes[1])]
            if app_window:
                wanted.append(
                    ('browser',
                     lambda listed: page_window(d, listed, reading.servername),
                     boxes[0])
                )
            panes = take_in(d, container, wanted)
            # vim asks for a size of its own as it starts, and whether that
            # lands before the pane was placed or after it is a matter of a few
            # hundredths of a second. So the session waits for vim to have
            # finished asking and then lays both panes out again, and a session
            # opens at the split the last one was left at rather than at
            # whatever vim happened to settle on.
            if 'vim' in panes:
                settle(panes['vim'])
                layout(d, container, panes, divider)
            # The panes were mapped after the strip and are sitting over it, so
            # the seam is laid again now that there is something to lay it on.
            meet(d, container, panes, divider)
            if 'browser' in panes:
                # Asked for the page's own title from here on, since the title
                # the reading carries is the page's and follows a link with it.
                panes['browser'].change_attributes(event_mask=X.PropertyChangeMask)
                follow_title(d, container, panes['browser'])
            focus(d, panes.get('vim'))
        hold(d, container, panes, divider, vim, reading, ending)
    finally:
        # Said before the container is put away, so that nothing on the page
        # goes on asking after a vim that is already gone. The wish goes with
        # it, since a vim that quit of its own accord leaves a session nobody
        # asked to end, and a wish left standing would open another at once.
        reading.editing = False
        reading.wanted = False
        release(d, container, panes, ending.is_set(), was_at)
        if d is not None:
            # One connection per session rather than one per reading, since a
            # reading may edit as many times as somebody ticks the box, and a
            # connection left open every time is a connection leaked every time.
            d.close()
    return ending.is_set()


def focus(d, window):
    """Point the keyboard at one of the panes."""
    if window is None:
        return
    window.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.sync()


def focus_pane(d, panes, focused):
    """Point the keyboard at the pane last clicked in, or at vim where that has gone."""
    focus(d, panes.get(focused) or panes.get('vim'))


def follow_title(d, container, page):
    """Put what the page calls itself on the reading's title bar and panel entry.

    The page's own title carries the document being read and follows a link to
    another document, so the reading is named from the page rather than from the
    document it started at.

    What the pane calls itself before the page has arrived is the address it is
    loading, which names no document, so only a title the page wrote is taken.
    """
    title = window_name(d, page)
    if title and title.startswith(TITLE):
        set_title(d, container, title)


def hand_back(d, container, page, box):
    """Give the page's window back to the desktop, at the size and place it had.

    The window is the browser's and was only borrowed, so when vim goes it is
    handed back rather than closed. This is the journey adopt() made, in
    reverse: the grabs taken on it are let go, the session stops listening to
    it, and it is unmapped, reparented to the root and mapped there. The map is
    what asks the window manager to take charge of it again, and it comes back
    framed and titled like any other window.

    Letting the grabs go matters more than it looks. They were taken
    synchronously, so that a click could be looked at and then let through, and
    a window left grabbed by a session that is no longer watching for clicks is
    a window nothing can be clicked in.

    Where it goes is where it stood before the session took it. The container
    fills the work area, so a page read in a small window grew as it went in,
    and leaving it at that size would mean the reader had to put it back by hand
    every time. A page that never had a place of its own, which is a session
    opened with --edit, is given the container's.

    Putting it back is asked for twice, because a request made before the
    window manager has taken charge is a request to nobody. The first is the
    configure below, which is what the manager reads as it frames the window,
    and the second is place(), once the manager has answered, which corrects
    whatever it decided to do instead.
    """
    for button in (1, 2, 3):
        for modifiers in locked():
            page.ungrab_button(button, modifiers)
    page.change_attributes(event_mask=0)
    page.unmap()
    page.reparent(d.screen().root, box[0], box[1])
    page.configure(x=box[0], y=box[1], width=box[2], height=box[3])
    page.map()
    d.sync()
    deadline = time.monotonic() + MANAGE_WAIT
    while time.monotonic() < deadline and page.id not in client_list(d):
        time.sleep(SETTLE_WAIT)
    place(d, page, box)


def hold(d, container, panes, divider, vim, reading, ending):
    """Hold the session up until vim goes.

    It ends when vim quits, or when vim is killed outright, which comes to the
    same thing here. Four things ask vim to quit, and vim refuses while
    anything in it is unwritten, so a session is never taken away from under
    unsaved work: the Edit toggle being pressed again, the browser window being
    the container's close button, and an interrupt in the terminal the command
    was typed into. The last three mean the whole reading is to end, and say so
    by setting the flag they share with whoever called this. The first means
    only that vim is to go.

    The page's window belongs to a browser the reading borrowed, so its closing
    is heard as the window being destroyed rather than as a process ending.
    Where there is no container there is nothing watching it, and such a
    session ends when vim quits and not before.

    The keyboard reaches a pane by two roads, because the desktop only lends
    the click on the first of them. A window that has just been clicked into
    from elsewhere is one the desktop takes the click for, and it says only
    that the container was clicked, so where the pointer is says which pane was
    meant. Once the reading has the keyboard the desktop stops taking the
    clicks, and from then on they arrive here and name their own pane.
    """
    focused = 'vim'
    # The one property of the page's the session follows, asked for once rather
    # than on every event a browser writes about itself.
    named = d.intern_atom('_NET_WM_NAME') if d is not None else None
    # What the page last asked for, so that unticking the box is heard as the
    # change it is and vim is asked once rather than four times a second for as
    # long as it goes on refusing.
    was = reading.wanted
    while vim.poll() is None:
        if reading.wanted != was:
            was = reading.wanted
            if was is False:
                vimlink.quit_vim(reading.servername)
        if container is None:
            time.sleep(POLL)
            continue
        keep_focus(d, container, panes, focused)
        select.select([d], [], [], POLL)
        while d.pending_events():
            event = d.next_event()
            if event.type == X.ButtonPress:
                # A press on the strip over the seam is a drag and nothing
                # else. It reaches the strip rather than the pane under it, so
                # no click is owed to anybody and none is let through.
                if event.window.id == divider.id:
                    drag(d, container, panes, divider, event)
                    continue
                for name, window in panes.items():
                    if window.id == event.window.id:
                        focused = name
                        focus(d, window)
                # Let the click through to the pane it was meant for, now that
                # the keyboard has been pointed at that pane.
                d.allow_events(X.ReplayPointer, event.time)
            elif event.type == X.ConfigureNotify:
                if event.window.id == container.id:
                    layout(d, container, panes, divider)
                else:
                    meet(d, container, panes, divider)
            elif event.type == X.DestroyNotify:
                # The page's window closed, by its own close button or with the
                # browser it belongs to. There is no page to go back to, so the
                # whole reading ends with it.
                page = panes.get('browser')
                if page is not None and event.window.id == page.id:
                    panes.pop('browser')
                    ending.set()
                    vimlink.quit_vim(reading.servername)
            elif event.type == X.FocusIn and event.window.id == container.id:
                if event.mode == X.NotifyNormal:
                    focused = under_pointer(container, panes) or focused
                    focus_pane(d, panes, focused)
            elif event.type == X.PropertyNotify and event.atom == named:
                # The page has renamed itself, which is how a link followed in
                # the browser reaches the title bar and the panel.
                page = panes.get('browser')
                if page is not None and event.window.id == page.id:
                    follow_title(d, container, page)
            elif event.type == X.ClientMessage:
                if event.data[1][0] == d.intern_atom('WM_DELETE_WINDOW'):
                    ending.set()
                    vimlink.quit_vim(reading.servername)


def ignore_gone(problem, request):
    """Say nothing when a window a request named has gone in the meantime.

    Everything here is asked of windows belonging to two other programs, either
    of which may close at any moment, and half of what is asked is asked as a
    reading is ending. The X server answers late, so the answer arrives here
    rather than where the request was made and cannot be caught there. Anything
    that is not a window having gone is still worth hearing about.
    """
    if not isinstance(problem, (error.BadWindow, error.BadDrawable, error.BadMatch)):
        sys.stderr.write(f'{NAME}: {problem}\n')


def keep_focus(d, container, panes, focused):
    """Take the keyboard back when it has been left on a window that has gone.

    Either program may put a window of its own up for a moment, and the desktop
    gives that window the keyboard and then has nowhere to hand it back to when
    the window goes, since the panes are not the desktop's to know about. A
    window the desktop is managing is another application, and one the desktop
    itself holds is the desktop's business, so both are left alone.

    Only ever while the reading is the window the desktop has in front, and
    never while another application holds the keyboard. Neither test is enough
    on its own. The desktop puts a window in front and hands it the keyboard as
    two steps, so a reading looking only at which window is in front can look
    between them and take back a keyboard it has already given up. And an
    application commonly keeps the keyboard on a window inside its own, which
    the desktop's list of windows does not name, so a reading looking only at
    that list reads a window it should not touch as one that has gone.
    """
    if active_window(d) != container.id:
        return
    where = d.get_input_focus().focus
    here = where if isinstance(where, int) else where.id
    if here in (X.NONE, X.PointerRoot, d.screen().root.id):
        return
    if any(window.id == here for window in panes.values()):
        return
    if top_level(d, here) in client_list(d):
        return
    focus_pane(d, panes, focused)


def layout(d, container, panes, divider):
    """Give each pane its share of the container.

    The browser takes the left of the window and vim the rest, in the
    proportion the divider was last dragged to. What vim rounds off its width
    is given back to the browser once vim has answered, which is meet()'s work
    rather than this one's.
    """
    here = container.get_geometry()
    boxes = pane_boxes(here.width, here.height)
    for name, box in zip(('browser', 'vim'), boxes):
        window = panes.get(name)
        if window is not None:
            window.configure(x=box[0], y=box[1], width=box[2], height=box[3])
    divider_at(divider, boxes[1][0], here.height)
    d.sync()


def locked():
    """Return the plain click and the same click under each lock key.

    A grab names one set of modifiers, and caps lock or num lock being down
    makes a different set, so a click has to be asked for under each of them or
    it is missed while a lock is on. Asking for every modifier at once is the
    shorter way to say this and cannot be used: it fails outright if any other
    program holds any button on the window, and on this desktop one does.
    """
    return (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask)


def make_container(d, document):
    """Put an empty window on the desktop for the reading to live in.

    It asks for the work area, so that nothing in the reading is put under a
    panel, and the window manager takes what its own border needs out of that.
    The name is the reading's own, since the container is the only window the
    desktop can see and there is nothing left to borrow a name from. It carries
    the document from the start, and the page's own title takes over once the
    page is up, so the panel never shows an address on its way to a name.

    It is white because it is seen before either pane is in it, and again
    afterwards in the band vim rounds off its height. A browser takes a moment
    to start, and a container of any other colour would open as a rectangle of
    that colour and then become a reading.
    """
    root = d.screen().root
    area = root.get_full_property(d.intern_atom('_NET_WORKAREA'), Xatom.CARDINAL)
    if area:
        x, y, width, height = tuple(area.value[:4])
    else:
        x, y = 0, 0
        width, height = d.screen().width_in_pixels, d.screen().height_in_pixels
    container = root.create_window(
        x, y, width, height, 0, X.CopyFromParent, X.InputOutput, X.CopyFromParent,
        background_pixel=d.screen().white_pixel,
        event_mask=(
            X.StructureNotifyMask | X.SubstructureNotifyMask | X.FocusChangeMask
        ),
    )
    container.set_wm_class(NAME, NAME.capitalize())
    set_icon(d, container)
    set_title(d, container, TITLE + document)
    container.change_property(
        d.intern_atom('_NET_WM_PID'), Xatom.CARDINAL, 32, [os.getpid()]
    )
    container.set_wm_hints(flags=Xutil.InputHint, input=1)
    container.set_wm_protocols([d.intern_atom('WM_DELETE_WINDOW')])
    container.map()
    settle(container)
    return container


def make_divider(d, container):
    """Put a strip over the seam for the pointer to take hold of.

    It draws nothing at all. The two panes meet exactly and there is no gap
    between them to grab, so what is dragged is a window of its own laid over
    the join, there for the pointer and for nothing else. The pointer changes
    shape over it, which is the whole of what says the seam can be moved.
    """
    font = d.open_font('cursor')
    divider = container.create_window(
        0, 0, DIVIDER, 1, 0, 0, X.InputOnly, X.CopyFromParent,
        cursor=font.create_glyph_cursor(
            font, DIVIDER_CURSOR, DIVIDER_CURSOR + 1,
            (0, 0, 0), (65535, 65535, 65535),
        ),
        event_mask=X.ButtonPressMask,
    )
    divider.map()
    return divider


def meet(d, container, panes, divider):
    """Put the two panes edge to edge, whatever vim rounded off its width.

    vim settles on a whole number of character columns however wide it is asked
    to be. So it is asked for its share, told where to sit once it has
    answered, and the browser beside it is given what was rounded off, and the
    two meet exactly however the reading is resized or dragged.

    The rows rounded off in the other direction leave a band of the container
    showing below vim, and nothing here can close it: vim settles on whole rows
    as it settles on whole columns, and there is no third pane to hand the
    remainder to.
    """
    browser, vim = panes.get('browser'), panes.get('vim')
    if vim is None:
        return
    here = container.get_geometry()
    there = vim.get_geometry()
    left = here.width - there.width
    # Asked for only where it is wrong, since a request answered by no change
    # still arrives back here and would otherwise go round for ever.
    if there.x != left:
        vim.configure(x=left)
    if browser is not None and browser.get_geometry().width != left:
        browser.configure(width=left)
    divider_at(divider, left, here.height)
    d.sync()


def open_page(url, servername, app_window=True, box=None, origin=(0, 0)):
    """Open the reading's page, in a window of its own where a browser can give one.

    The page is opened at the reading's own name rather than at the root,
    because the browser names the window it puts up after the address it was
    given, and that name is the whole of how a session picks the page's window
    out of the desktop when it comes to take it in. Every reading opens this
    way, whether or not it ever edits, since the name has to be settled before
    the window exists.

    Where the page is going to end up is worth saying only to a browser the
    reading has to start, because a browser already running puts its own window
    where it likes. It saves that one case a visible jump on the way in.
    """
    page = f'{url}/{servername}'
    browser = browser_path() if app_window else None
    if browser:
        # Started and not held on to. The command hands the asking to a browser
        # already running and is gone within the moment, so what it leaves
        # behind is a window rather than a process to wait on, and the window is
        # what a session holds the page by.
        subprocess.Popen(
            browser_command(browser, page, box, origin),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return
    # On a thread of its own: opening a browser can block until it exits. A
    # desktop with nothing to open it with is not a failure either, since the
    # address is already printed and the reading stays reachable by hand.
    threading.Thread(target=webbrowser.open, args=(page, 2), daemon=True).start()


def page_window(d, listed, servername):
    """Return the window the browser has put up for the page, or nothing while it has not.

    The window belongs to the browser and to no process of the reading's, so it
    is known by its name instead. A browser names a window opened with --app
    after the address the page came from, and the reading serves its page under
    a name of its own for exactly this, so the name is in that address and in
    nobody else's. The host is not enough on its own: every reading on the
    machine serves on the same one, and the port never reaches the name.

    The address ends at the name, so the name is looked for at the end and not
    anywhere inside, and one reading whose name begins another's is not read as
    that other one.
    """
    for xid in listed:
        window = d.create_resource_object('window', xid)
        try:
            classes = window.get_wm_class()
        except Exception:
            # The window has gone in the moment since the desktop listed it.
            continue
        if classes and any(name.endswith(servername) for name in classes):
            return window
    return None


def pane_boxes(width, height):
    """Return where each pane goes inside a container of this size."""
    left = round(width * browser_share)
    return ((0, 0, left, height), (left, 0, width - left, height))


def place(d, window, box):
    """Ask the desktop to put a window exactly where it is wanted, frame and all.

    A plain configure request is read against the window's gravity, and under
    the ordinary one the numbers name where the frame goes rather than where
    the window does, so a window put back that way walks down and to the right
    by the depth of its own title bar every time it makes the journey. This
    says static gravity outright, which means the numbers are the window's own
    and the manager works out where its frame has to go for them to be true.

    It is a request and not an instruction. A manager that ignores it leaves
    the window wherever the configure before it landed, which is close.
    """
    x, y, width, height = box
    root = d.screen().root
    root.send_event(
        protocol.event.ClientMessage(
            window=window,
            client_type=d.intern_atom('_NET_MOVERESIZE_WINDOW'),
            data=(32, [X.StaticGravity | MOVERESIZE, x, y, width, height]),
        ),
        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
    )
    d.sync()


def release(d, container, panes, ending, was_at):
    """Put the session's window away, and settle what becomes of the page's own.

    A reading going back to viewing gets its page handed back to the desktop,
    at the size and in the place it had before the session took it. A reading
    that is ending has nowhere to hand it to, so the window is asked to close in
    the way its close button asks, and asked before the container it sits in is
    taken away, so that the browser closes the window rather than losing it.

    The page's window is missing from the panes where it was closed by whoever
    is reading, which is one of the ways a reading ends, and there is nothing
    left to do about it either way.
    """
    page = panes.get('browser')
    if page is not None:
        if ending:
            close_page(d, page)
        else:
            hand_back(d, container, page, was_at or where_of(d, container))
    if container is not None:
        container.destroy()
        d.sync()


def set_icon(d, container):
    """Give the reading its own image on the panel and on its title bar.

    The desktop asks for the icon as pixels rather than as a file, so the files
    are decoded here, and Pillow is what decodes them. Without Pillow the window
    goes without, and the desktop draws it with whatever it gives a window that
    carries no icon of its own. Every size the reading ships is handed over at
    once, and the desktop takes whichever fits where it is drawing.
    """
    if Image is None:
        return
    data = []
    for path in ICONS:
        with Image.open(path) as image:
            pixels = image.convert('RGBA')
        data += [pixels.width, pixels.height]
        data += [a << 24 | r << 16 | g << 8 | b for r, g, b, a in pixels.getdata()]
    container.change_property(d.intern_atom('_NET_WM_ICON'), Xatom.CARDINAL, 32, data)


def set_title(d, container, title):
    """Say what the reading is called, on its title bar and on the panel.

    The modern name and the old one both, since which of the two a desktop
    reads is the desktop's business and the two are meant to agree.
    """
    utf8 = d.intern_atom('UTF8_STRING')
    container.set_wm_name(title)
    container.set_wm_icon_name(title)
    for atom in ('_NET_WM_NAME', '_NET_WM_ICON_NAME'):
        container.change_property(d.intern_atom(atom), utf8, 8, title.encode('utf-8'))


def settle(window):
    """Wait for a window to stop changing size, since a request is only a request."""
    was = None
    for _ in range(SETTLE_TRIES):
        time.sleep(SETTLE_WAIT)
        here = window.get_geometry()
        now = (here.width, here.height)
        if now == was:
            return
        was = now


def take_in(d, container, wanted):
    """Take each pane into the container as its window appears.

    Both halves are asked for together and either may be up first, so both are
    watched at once and each is taken in the moment it arrives. Waiting for them
    in turn left whichever came first standing on the desktop as a window of its
    own, with a title bar of its own, for as long as the other one took.

    Each pane says how its own window is to be picked out of the desktop's list,
    since the two are found in quite different ways: vim is a process of the
    reading's and the page's window is not.
    """
    panes = {}
    waiting = list(wanted)
    deadline = time.monotonic() + WINDOW_WAIT
    while waiting and time.monotonic() < deadline:
        # The desktop's list is asked for once a turn rather than once a pane,
        # since both panes are looked for in the same list.
        listed = client_list(d)
        for pane in list(waiting):
            name, find, box = pane
            window = find(listed)
            if window is not None:
                adopt(d, container, window, box)
                panes[name] = window
                waiting.remove(pane)
        if waiting:
            time.sleep(SETTLE_WAIT)
    return panes


def top_level(d, window_id):
    """Return the window the desktop lists for the one holding the keyboard.

    An application commonly puts the keyboard on a window inside its own, and
    the desktop's list of windows names only the outer one. The outer one is
    the window carrying WM_STATE, which is what the desktop writes on a window
    it has taken charge of, so the tree is climbed until that is found.

    Nothing is found for a window that has gone in the meantime, which is the
    same answer as for a window the desktop never took charge of, and both mean
    the same thing to the one caller: nobody else's keyboard is being taken.
    """
    state = d.intern_atom('WM_STATE')
    window = d.create_resource_object('window', window_id)
    root = d.screen().root.id
    try:
        while window.id != root:
            if window.get_full_property(state, X.AnyPropertyType):
                return window.id
            window = window.query_tree().parent
            if window is None:
                return None
    except Exception:
        # The window belongs to another program and may go at any moment,
        # including between two of the questions asked about it here.
        return None
    return None


def under_pointer(container, panes):
    """Return the name of the pane the pointer is over, or None if it is over neither.

    This is how the keyboard is handed from one pane to the other, and it is
    read at the moment the desktop points the keyboard at the container. The
    desktop is set to give a window the keyboard when it is clicked, and since
    the two panes are inside one window every click in either of them is a click
    on that window, so the desktop asks this question for us and the answer is
    simply where the pointer was when it asked.

    A click on the title bar or on the entry on the panel is over neither pane
    and says nothing about which one is wanted, so it leaves the keyboard where
    it was.
    """
    child = container.query_pointer().child
    inside = child if isinstance(child, int) else child.id
    for name, window in panes.items():
        if window.id == inside:
            return name
    return None


def vim_command(servername, document, box, origin):
    """Return the command that opens the vim the reading is read with.

    gvim rather than vim in a terminal of the reading's own. A terminal is a
    third program standing between the reading and vim, and what it does to the
    pane it draws in has to be undone again: it holds on to the rows vim named
    when it started, whatever the pane is resized to afterwards, and it passes
    the title vim writes on to the window the reading has already named.

    In the foreground, since gvim otherwise forks and leaves nothing to hold.
    The process started here is the whole of how the reading knows vim is still
    up, and its ending is how the reading ends.

    The headroom gvim keeps goes before the vimrc, since it is read once as the
    window is made and not again. It is fifty pixels by default, kept clear so
    that a window and the border a window manager draws round it both fit the
    screen, and it costs the pane two rows it could have filled: the pane is
    inside the reading's window and nothing is drawn round it.

    The menu bar and the scrollbar go after the vimrc rather than before it, so
    that a vimrc asking for either does not win. The reading's own window
    carries a title bar and a close button for the pair of panes, and neither
    pane carries anything of the kind itself. Keeping the window is asked for
    first and the two are dropped after it, because gvim otherwise takes the
    room they were using out of its own window rather than giving it to the
    document. That resize lands after the reading has placed the pane as often
    as it lands before, and the reading gives the page whatever width vim
    settles on, so without this the seam sits somewhere else every second or
    third reading.
    """
    command = ['gvim', '-f', '--servername', servername]
    if box is not None:
        command += ['-geometry', f'+{origin[0] + box[0]}+{origin[1] + box[1]}']
    return command + [
        '--cmd', 'set guiheadroom=0',
        '-c', 'set guioptions+=k guioptions-=m guioptions-=r',
        '-S', SCRIPT, '--', str(document),
    ]


def where_of(d, window):
    """Return where a window stands on the screen and how big it is.

    Read in root coordinates rather than in its parent's, since a window the
    desktop is managing sits inside a frame the manager drew and its own
    geometry is measured from the corner of that frame.
    """
    here = window.get_geometry()
    where = d.screen().root.translate_coords(window, 0, 0)
    return (where.x, where.y, here.width, here.height)


def white(d, window):
    """Return opaque white for a window, whatever depth it draws at.

    A browser and gvim both ask for a visual with an alpha channel where the
    screen itself has none, and the screen's white on such a visual is white
    with nothing of it left, which is to say nothing at all.
    """
    if window.get_geometry().depth == 32:
        return 0xFFFFFFFF
    return d.screen().white_pixel


def window_name(d, window):
    """Return what a window calls itself, or nothing where it says nothing.

    The modern name only, which is the one a browser writes and the one that
    says it is UTF-8, so a document name with anything but ASCII in it arrives
    as itself. The old name is bytes with no encoding named, and the browser
    leaves it empty anyway.
    """
    try:
        said = window.get_full_property(d.intern_atom('_NET_WM_NAME'), X.AnyPropertyType)
    except Exception:
        # The window belongs to the browser and may go at any moment.
        return None
    return said.value.decode('utf-8', 'replace') if said else None


def window_of(d, listed, pid):
    """Return the window a program has put up, or nothing while it has put up none.

    A program may put up a window of its own as well as the one wanted, so the
    widest is taken. Each width is asked for once and carried, since this runs
    many times a second while a reading opens.
    """
    wide = []
    for window in windows_of(d, listed, pid):
        try:
            wide.append((window.get_geometry().width, window))
        except Exception:
            continue
    if not wide:
        return None
    return max(wide, key=lambda found: found[0])[1]


def windows_of(d, listed, pid):
    """Return the windows belonging to a process, out of the desktop's own list."""
    windows = []
    for xid in listed:
        window = d.create_resource_object('window', xid)
        owner = window.get_full_property(d.intern_atom('_NET_WM_PID'), Xatom.CARDINAL)
        if owner and owner.value[0] == pid:
            windows.append(window)
    return windows


def withdraw(d, window):
    """Ask the window manager to let go of a window without letting go of the window.

    A window reparented while the manager is still managing it is handed
    straight back to the root, because the manager reads the reparent as the
    window having gone and its own tidying up is what puts it there. Unmapping
    the window and telling the root about it is the way the ICCCM gives to say
    that a window is no longer the manager's, and it is waited on rather than
    assumed, since everything after it depends on the manager having finished.
    """
    root = d.screen().root
    window.unmap()
    root.send_event(
        protocol.event.UnmapNotify(window=window, event=root, from_configure=False),
        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
    )
    d.sync()
    deadline = time.monotonic() + WITHDRAW_WAIT
    while time.monotonic() < deadline and window.id in client_list(d):
        time.sleep(SETTLE_WAIT)


def x_display():
    """Return the X display, or None where there is nothing to talk to it with."""
    if display is None:
        return None
    try:
        d = display.Display()
        d.set_error_handler(ignore_gone)
        return d
    except Exception:
        # Xlib raises several unrelated errors for a display it cannot reach,
        # and none of them is worth stopping a reading for.
        return None
