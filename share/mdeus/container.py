"""
One window with both halves of a reading inside it.

A reading with vim beside it is two programs, a browser and a terminal, and the
desktop would ordinarily give each of them a window of its own. This makes one
window and puts both inside it, so that the reading is one entry on the panel,
is moved as one, resized as one and closed as one.

Taking a window off the window manager has an order to it. Reparenting a window
the manager is still managing loses a race: the manager sees its client leave
the frame it drew, runs the same tidying up it runs for a window that has gone,
and that tidying up hands the client back to the root window. So each window is
withdrawn first, in the way the ICCCM asks for, and reparented only once the
manager has let go of it.

Nothing manages the two windows once they are inside, and the work a window
manager would have done falls here. The panes are laid out again whenever the
container is resized, the seam between them is dragged with the pointer, and
the keyboard is handed from one pane to the other on a click, which is how the
desktop is set to hand it between windows.

Without python3-xlib there is no container to be made, so the reading opens in
two ordinary windows wherever the desktop puts them. It says so and carries on.
"""

import os
import select
import shutil
import signal
import subprocess
import sys
import time

import vimlink
from state import MAX_SPLIT, MIN_SPLIT, load_split, save_split

try:
    from Xlib import X, Xatom, Xutil, display, error, protocol
except ImportError:  # python3-xlib is not installed
    X = Xatom = Xutil = display = error = protocol = None

# The browsers a reading can own a window of, in the order they are looked for.
# Each of them gives a window with nothing in it but the page, and a profile of
# its own, which is what lets the reading close that window again.
BROWSERS = ('google-chrome', 'chromium', 'chromium-browser')
# How long to give the browser to close before it is made to, in seconds.
BROWSER_STOP = 5
# How wide a strip of the reading you can take hold of the seam by. It lies
# over the join rather than between the panes, so the two go on meeting exactly
# and the reading looks no different for being draggable.
DIVIDER = 6
# The glyph in the cursor font that says a thing can be dragged sideways, and
# the glyph after it, which is its mask.
DIVIDER_CURSOR = 108
# What the reading is called, on its title bar and on the panel.
NAME = b'bmvim'
NO_BROWSER = (
    'bmvim: no chrome or chromium here, so the page opens in a tab of your\n'
    '       usual browser, which is neither placed nor closed for you'
)
# How often the two programs are looked in on, in seconds.
POLL = 0.25
SETTLE_TRIES = 20
SETTLE_WAIT = 0.05
UNPLACED = 'bmvim: the reading is in two windows of its own, wherever the desktop put them'
# How long to go on waiting for a program to put its window up, in seconds.
WINDOW_WAIT = 15
# How long to go on waiting for the window manager to let go of a window.
WITHDRAW_WAIT = 5

# The share of the window the browser pane takes. A reading opens at whatever
# the last drag of the divider left, and every layout is measured from this, so
# it is kept here rather than handed down through the events that read it.
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


def browser_command(browser, url, profile, box, origin):
    """Return the command that opens the page in a window of its own.

    --app gives a window with nothing in it but the page, and a profile of its
    own makes that window a process of its own, which is what lets the reading
    own it and close it. A profile that has never been used greets you on the
    way in, and the greeting would arrive over the document, so it is turned
    off. The window is asked for where it is going to end up, so that the moment
    before it is taken into the container looks like no moment at all.
    """
    command = [browser, f'--app={url}', '--no-first-run', f'--user-data-dir={profile}']
    if box is not None:
        x, y, width, height = box
        command.append(f'--window-position={origin[0] + x},{origin[1] + y}')
        command.append(f'--window-size={width},{height}')
    return command


def browser_path():
    """Return the browser a reading can own a window of, or nothing where there is none."""
    for candidate in BROWSERS:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def client_list(d):
    """Return the windows the desktop says it is managing."""
    listed = d.screen().root.get_full_property(
        d.intern_atom('_NET_CLIENT_LIST'), Xatom.WINDOW
    )
    return list(listed.value) if listed else []


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
    will land: a terminal settles on whole character columns, so the reading
    snaps to the nearest one and dragging is how you see which. Where it was
    left is stored, so the next reading opens at the same split.
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
                # The terminal answering with the width it settled on. The
                # browser is given the remainder now rather than after the
                # drag, so the seam stays under the pointer as it moves.
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


def focus(d, window):
    """Point the keyboard at one of the panes."""
    if window is None:
        return
    window.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.sync()


def focus_pane(d, panes, focused):
    """Point the keyboard at the pane last clicked in, or at vim where that has gone."""
    focus(d, panes.get(focused) or panes.get('terminal'))


def ignore_gone(problem, request):
    """Say nothing when a window a request named has gone in the meantime.

    Everything here is asked of windows belonging to two other programs, either
    of which may close at any moment, and half of what is asked is asked as a
    reading is ending. The X server answers late, so the answer arrives here
    rather than where the request was made and cannot be caught there. Anything
    that is not a window having gone is still worth hearing about.
    """
    if not isinstance(problem, (error.BadWindow, error.BadDrawable, error.BadMatch)):
        sys.stderr.write(f'bmvim: {problem}\n')


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

    The browser takes the left of the window and the terminal the rest, in the
    proportion the divider was last dragged to. What the terminal rounds off its
    width is given back to the browser once the terminal has answered, which is
    meet()'s work rather than this one's.
    """
    here = container.get_geometry()
    boxes = pane_boxes(here.width, here.height)
    for name, box in zip(('browser', 'terminal'), boxes):
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


def main(argv):
    """Open a reading, hold it up, and put everything away when it ends."""
    url, servername, profile, script, document = argv
    browser = browser_path()
    if not browser:
        print(NO_BROWSER, flush=True)
    d = x_display() if browser else None
    container = make_container(d) if d is not None else None
    if browser and container is None:
        print(UNPLACED, flush=True)

    if container is None:
        boxes, divider, origin = (None, None), None, (0, 0)
    else:
        here = container.get_geometry()
        boxes = pane_boxes(here.width, here.height)
        divider = make_divider(d, container)
        where = d.screen().root.translate_coords(container, 0, 0)
        origin = (where.x, where.y)

    if browser:
        page = subprocess.Popen(
            browser_command(browser, url, profile, boxes[0], origin),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        page = None
        subprocess.Popen(
            ['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    terminal = subprocess.Popen(
        terminal_command(servername, script, document, boxes[1], origin),
        env=dict(
            os.environ,
            MDVIEW_LINK=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vimlink.py'),
            MDVIEW_URL=url,
        ),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    panes = {}
    try:
        if container is not None:
            # A window narrower than half the pane is one the browser put up for
            # itself rather than the one the page is in. The terminal is taken
            # at whatever width it comes up at.
            wanted = [('terminal', terminal.pid, boxes[1], 0)]
            if page is not None:
                wanted.append(('browser', page.pid, boxes[0], boxes[0][2] // 2))
            panes = take_in(d, container, wanted)
            # The panes were mapped after the strip and are sitting over it, so
            # the seam is laid again now that there is something to lay it on.
            meet(d, container, panes, divider)
            focus(d, panes.get('terminal'))
        watch(d, container, panes, divider, page, terminal, servername)
    finally:
        if page is not None and page.poll() is None:
            # Waited for rather than left to close in its own time, because the
            # profile it is still writing to is about to be taken away from it.
            page.terminate()
            try:
                page.wait(timeout=BROWSER_STOP)
            except subprocess.TimeoutExpired:
                page.kill()
        if container is not None:
            container.destroy()
            d.sync()
    return 0


def make_container(d):
    """Put an empty window on the desktop for the reading to live in.

    It asks for the work area, so that nothing in the reading is put under a
    panel, and the window manager takes what its own border needs out of that.
    The name is the reading's own, since the container is the only window the
    desktop can see and there is nothing left to borrow a name from.

    It is white because it is seen before either pane is in it, and again
    afterwards in the band the terminal rounds off its height. A browser takes
    a moment to start, and a container of any other colour would open as a
    rectangle of that colour and then become a reading.
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
    utf8 = d.intern_atom('UTF8_STRING')
    container.set_wm_name(NAME.decode())
    container.set_wm_icon_name(NAME.decode())
    container.set_wm_class('bmvim', 'Bmvim')
    container.change_property(d.intern_atom('_NET_WM_NAME'), utf8, 8, NAME)
    container.change_property(d.intern_atom('_NET_WM_ICON_NAME'), utf8, 8, NAME)
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
    """Put the two panes edge to edge, whatever the terminal rounded off its width.

    A terminal settles on a whole number of character columns however wide it is
    asked to be. So it is asked for its share, told where to sit once it has
    answered, and the browser beside it is given what was rounded off, and the
    two meet exactly however the reading is resized or dragged.

    The rows rounded off in the other direction leave a band of the container
    showing below the terminal, and nothing here can close it. A terminal fills
    a height it cannot divide only by being maximised against the desktop, and
    inside a window there is no desktop left to maximise it against.
    """
    browser, terminal = panes.get('browser'), panes.get('terminal')
    if terminal is None:
        return
    here = container.get_geometry()
    there = terminal.get_geometry()
    left = here.width - there.width
    # Asked for only where it is wrong, since a request answered by no change
    # still arrives back here and would otherwise go round for ever.
    if there.x != left:
        terminal.configure(x=left)
    if browser is not None and browser.get_geometry().width != left:
        browser.configure(width=left)
    divider_at(divider, left, here.height)
    d.sync()


def pane_boxes(width, height):
    """Return where each pane goes inside a container of this size."""
    left = round(width * browser_share)
    return ((0, 0, left, height), (left, 0, width - left, height))


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

    Both programs are started together and either may be up first, and a
    browser is commonly seconds behind a terminal. So both are watched at once
    and each is taken in the moment it arrives. Waiting for them in turn left
    whichever came first standing on the desktop as a window of its own, with a
    title bar of its own, for as long as the other one took to start.
    """
    panes = {}
    waiting = list(wanted)
    deadline = time.monotonic() + WINDOW_WAIT
    while waiting and time.monotonic() < deadline:
        # The desktop's list is asked for once a turn rather than once a pane,
        # since both panes are looked for in the same list.
        listed = client_list(d)
        for pane in list(waiting):
            name, pid, box, least_width = pane
            window = window_of(d, listed, pid, least_width)
            if window is not None:
                adopt(d, container, window, box)
                panes[name] = window
                waiting.remove(pane)
        if waiting:
            time.sleep(SETTLE_WAIT)
    return panes


def terminal_command(servername, script, document, box, origin):
    """Return the command that opens the terminal the reading's vim runs in.

    A terminal of the reading's own rather than the one the command was typed
    into. Everything inside the container goes when the container does, and a
    terminal somebody else is using is not the reading's to take that risk with.

    notitle comes after the vimrc rather than before it, since a vimrc that
    turns the title on would otherwise win, and vim writing the name of the file
    onto the terminal writes over the name the reading has put on the window.
    """
    command = ['mate-terminal', '--disable-factory', '--hide-menubar']
    if box is not None:
        command.append(f'--geometry=+{origin[0] + box[0]}+{origin[1] + box[1]}')
    return command + [
        '--', 'vim', '--servername', servername, '-c', 'set notitle',
        '-S', script, '--', document,
    ]


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


def watch(d, container, panes, divider, page, terminal, servername):
    """Hold the reading up until it ends.

    It ends when vim quits, which is what the terminal is waiting on, or when
    the terminal is killed outright, which comes to the same thing here. The
    browser window being closed asks vim to quit instead, and vim refuses while
    anything in it is unwritten, so a reading is never taken away from under
    unsaved work. The container's close button and an interrupt in the terminal
    the command was typed into both ask the same question.

    The keyboard reaches a pane by two roads, because the desktop only lends
    the click on the first of them. A reading that has just been clicked into
    from elsewhere is one the desktop takes the click for, and it says only
    that the container was clicked, so where the pointer is says which pane was
    meant. Once the reading has the keyboard the desktop stops taking the
    clicks, and from then on they arrive here and name their own pane.
    """
    signal.signal(signal.SIGINT, lambda number, frame: vimlink.quit_vim(servername))
    focused = 'terminal'
    while terminal.poll() is None:
        if page is not None and page.poll() is not None:
            vimlink.quit_vim(servername)
            page = None
            panes.pop('browser', None)
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
            elif event.type == X.FocusIn and event.window.id == container.id:
                if event.mode == X.NotifyNormal:
                    focused = under_pointer(container, panes) or focused
                    focus_pane(d, panes, focused)
            elif event.type == X.ClientMessage:
                if event.data[1][0] == d.intern_atom('WM_DELETE_WINDOW'):
                    vimlink.quit_vim(servername)


def white(d, window):
    """Return opaque white for a window, whatever depth it draws at.

    A browser and a terminal both ask for a visual with an alpha channel where
    the screen itself has none, and the screen's white on such a visual is
    white with nothing of it left, which is to say nothing at all.
    """
    if window.get_geometry().depth == 32:
        return 0xFFFFFFFF
    return d.screen().white_pixel


def window_of(d, listed, pid, least_width):
    """Return the window a program has put up, or nothing while it has put up none.

    A program may put up a window of its own as well as the one wanted, so the
    widest is taken and anything too narrow to be a pane is passed over. Each
    width is asked for once and carried, since this runs many times a second
    while a browser starts.
    """
    wide = []
    for window in windows_of(d, listed, pid):
        try:
            width = window.get_geometry().width
        except Exception:
            continue
        if width >= least_width:
            wide.append((width, window))
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


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
