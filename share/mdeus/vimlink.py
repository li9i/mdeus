"""
The link between a reading in the browser and the vim beside it.

Everything a reading with vim needs that is not the serving itself: finding out
whether one is already up, sending vim to a line or to another document, putting
the two windows where they go, and lending the terminal's window list entry to
the reading for as long as it lasts.

The server imports this to reach vim. The rest is reached from the command line,
because the command that starts a reading is a shell script, and because vim
reports its cursor by starting a process rather than by waiting on one.

Placing a window takes three things the desktop knows and nothing else can be
told. The work area, so that neither window is put under a panel. The borders
the window manager draws, since a window is asked to be one size and is drawn
another. And where a window ended up once it settled, since a terminal answers a
resize with the nearest whole number of characters rather than the size it was
given. Those come from Xlib, and the moving and sizing itself from xdotool.

Two things here are allowed to be missing. Without python3-xlib the window list
entry keeps the terminal's own name and nothing is said about it, which is how
the reading in the terminal has always behaved, the windows are placed by the
rougher measure of the whole screen, and the terminal is not maximised for its
height, so it falls short of the work area by part of a row. Without xdotool, or
where a placement call fails, the reading says so and carries on with the
windows wherever the desktop put them. Neither is worth stopping a reading for.
"""

import json
import subprocess
import sys
import time
import urllib.request

try:
    from Xlib import X, Xatom, display, protocol
except ImportError:  # python3-xlib is not installed
    X = Xatom = display = protocol = None

# The two names a terminal is known by: the one on its window list entry and
# the one on its title bar. Each is put away under a name of ours for as long
# as the reading has it, and copied back afterwards.
BORROWED = (
    ('_NET_WM_ICON_NAME', '_MDVIEW_KEPT_ICON_NAME'),
    ('_NET_WM_NAME', '_MDVIEW_KEPT_NAME'),
)
BROWSER_SHARE = 0.44
# How long to go on waiting for the browser to put a window up.
BROWSER_WAIT = 5
# Set while the reading holds the terminal's names, so that giving them back
# twice cannot hand the terminal an empty entry the second time.
HELD = '_MDVIEW_HELD'
# Leaves whatever mode vim is in, and unlike Escape cannot be read as the
# opening of the line that follows it.
NORMAL_MODE = r'<C-\><C-n>'
PANEL_NAME = b'cvim'
SETTLE_TRIES = 10
SETTLE_WAIT = 0.05
# Nothing here is worth waiting on. A vim busy enough not to answer, or a
# server that has stopped listening, must not hold up whoever asked.
TIMEOUT = 2
UNPLACED = 'cvim: the windows are wherever the desktop put them, not placed'


def borrow(d, window):
    """Write cvim on the terminal's window list entry, keeping its own names aside.

    Only the names are taken, so the entry keeps the terminal's own icon
    throughout.
    """
    utf8 = d.intern_atom('UTF8_STRING')
    for live, kept in BORROWED:
        was = window.get_full_property(d.intern_atom(live), 0)
        if was is not None:
            window.change_property(
                d.intern_atom(kept), was.property_type, was.format, was.value
            )
        window.change_property(d.intern_atom(live), utf8, 8, PANEL_NAME)
    window.change_property(d.intern_atom(HELD), Xatom.CARDINAL, 32, [1])
    d.sync()


def boxes():
    """Return where the browser and the terminal go, or None if nothing can say.

    The browser takes 44 percent of the width on the left and the terminal the
    rest, which is how the same document read in a terminal is already split.
    """
    area = screen_area()
    if area is None:
        return None
    x, y, width, height = area
    left = round(width * BROWSER_SHARE)
    return ((x, y, left, height), (x + left, y, width - left, height))


def browser_flags():
    """Return the flags that open the browser window near its place, or an empty string.

    Near it rather than on it. The browser window is drawn a little larger than
    the size it is given, so it is put right afterwards, and this is only to
    keep it from opening in the middle of the screen and jumping.
    """
    box = boxes()
    if box is None:
        return ''
    x, y, width, height = box[0]
    return f'--window-position={x},{y} --window-size={width},{height}'


def browser_window(d, pid, least_width):
    """Return the browser's own window once the desktop has one, or None.

    The window is looked for by the process the reading started, and waited
    for, since a browser takes a moment to put one up. A browser may put up a
    window of its own as well as the page, so the widest is taken and anything
    too narrow to be the page is passed over.
    """
    deadline = time.monotonic() + BROWSER_WAIT
    while time.monotonic() < deadline:
        wide = [w for w in windows_of(d, pid) if frame_rect(d, w)[2] >= least_width]
        if wide:
            return max(wide, key=lambda window: frame_rect(d, window)[2])
        time.sleep(SETTLE_WAIT)
    return None


def document_open(servername):
    """Return the file the reading under this name has open, or nothing if it will not say."""
    return remote(servername, '--remote-expr', 'expand("%:p")') or ''


def edit(servername, path):
    """Send vim to another document, so that both halves of a reading show the same file.

    The file travels as an argument rather than as typed keys, so a name with a
    space or a per cent sign in it arrives as itself. vim takes this in any
    mode and is left in normal mode by it.
    """
    remote(servername, '--remote-silent', str(path))


def frame_extents(d, window):
    """Return the borders the window manager drew round a window: left, right, top, bottom.

    A window asked to be as wide as its share of the screen is drawn that wide
    plus its borders, so two windows placed side by side without allowing for
    them overlap by exactly this much.
    """
    extents = window.get_full_property(d.intern_atom('_NET_FRAME_EXTENTS'), Xatom.CARDINAL)
    if not extents:
        return (0, 0, 0, 0)
    return tuple(extents.value[:4])


def frame_rect(d, window):
    """Return where a window's frame sits and how big it is: x, y, width, height.

    The frame rather than the window inside it, since the frame is what the
    desktop shows and what the window beside it has to meet.
    """
    left, right, top, bottom = frame_extents(d, window)
    here = d.screen().root.translate_coords(window, 0, 0)
    size = window.get_geometry()
    return (
        here.x - left,
        here.y - top,
        size.width + left + right,
        size.height + top + bottom,
    )


def give_back(d, window):
    """Hand the terminal its own window list entry back.

    A window that is not holding anything is left alone, so the trap firing
    twice, or a reading that never got as far as borrowing, costs nothing.
    """
    if window.get_full_property(d.intern_atom(HELD), 0) is None:
        return
    for live, kept in BORROWED:
        was = window.get_full_property(d.intern_atom(kept), 0)
        if was is None:
            window.delete_property(d.intern_atom(live))
        else:
            window.change_property(
                d.intern_atom(live), was.property_type, was.format, was.value
            )
            window.delete_property(d.intern_atom(kept))
    window.delete_property(d.intern_atom(HELD))
    d.sync()


def jump(servername, first, last):
    """Send vim to a block of the document it has open, and light the whole of it.

    What vim does on arrival is a function of vim's own, sourced when the
    reading started, since centring the block and marking it for a moment is
    more than a line of typed keys can carry.
    """
    remote(
        servername,
        '--remote-send',
        f'{NORMAL_MODE}:call CvimJumpTo({int(first)}, {int(last)})<CR>',
    )


def maximise_height(d, window):
    """Ask the desktop to give a window the whole height of the work area.

    A terminal settles on a whole number of character rows however its size was
    asked for. Sized by hand it comes up short of the work area by whatever the
    last row would not fill, and a strip of desktop is left above it that no
    size can fill, since the terminal springs back from any height that is not a
    whole number of rows. Maximised upwards it keeps the height it is given and
    pads the remainder inside itself instead, which is the only way the strip
    goes rather than moves. The width is left to be asked for as before, since
    the browser beside it takes up whatever the terminal rounds off there.
    """
    # A window is maximised by asking the desktop rather than by resizing it.
    # The message says to add the state that follows it, on behalf of an
    # ordinary application.
    message = protocol.event.ClientMessage(
        window=window,
        client_type=d.intern_atom('_NET_WM_STATE'),
        data=(32, [1, d.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT'), 0, 1, 0]),
    )
    d.screen().root.send_event(
        message, event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask
    )
    d.sync()


def main(argv):
    """Run one of the small jobs the reading asks for from the command line."""
    what = argv[0]
    if what == 'borrow' and argv[1]:
        d = x_display()
        if d is not None:
            borrow(d, d.create_resource_object('window', int(argv[1])))
    elif what == 'browser-flags':
        print(browser_flags())
    elif what == 'cursor':
        report_cursor(argv[1], argv[2])
    elif what == 'give-back' and argv[1]:
        d = x_display()
        if d is not None:
            give_back(d, d.create_resource_object('window', int(argv[1])))
    elif what == 'holder':
        if argv[1].upper() not in servers():
            return 1
        print(document_open(argv[1]))
    elif what == 'place-browser':
        place_browser(argv[1], argv[2])
    elif what == 'place-terminal':
        place_terminal(argv[1])
    elif what == 'quit':
        quit_vim(argv[1])
    elif what == 'window':
        print(terminal_window())
    return 0


def place_browser(window_id, pid):
    """Put the browser in what the terminal left of the work area, meeting it exactly.

    Silent throughout, and run while vim is starting. Anything it had to say
    would be said over a screen vim is drawing, and a browser window a little
    out of place is not worth that.
    """
    box = boxes()
    d = x_display()
    if box is None or d is None:
        return
    x, y, width, height = box[0]
    try:
        if window_id:
            # Up to where the terminal actually is, rather than up to where it
            # was asked to be. What the terminal rounded off its own width is
            # given to the browser, and the two meet whatever the rounding was.
            terminal = d.create_resource_object('window', int(window_id))
            width = frame_rect(d, terminal)[0] - x
        window = browser_window(d, int(pid), width // 2)
        if window is None:
            return
        left, right, top, bottom = frame_extents(d, window)
        run(['xdotool', 'windowsize', str(window.id),
             str(width - left - right), str(height - top - bottom)])
        run(['xdotool', 'windowmove', str(window.id), str(x), str(y)])
    except Exception:
        # A reading that ends while this is still waiting leaves it holding
        # windows that have gone, and a browser window nobody could place is
        # not worth a word about, let alone a failure.
        pass


def place_terminal(window_id):
    """Put the terminal on the right of the work area, or say that it stayed where it was."""
    box = boxes()
    if box is None or not window_id:
        print(UNPLACED)
        return
    x, y, width, height = box[1]
    try:
        d = x_display()
        window = (
            d.create_resource_object('window', int(window_id)) if d is not None else None
        )
        if window is not None:
            maximise_height(d, window)
        left, right, top, bottom = (
            (0, 0, 0, 0) if window is None else frame_extents(d, window)
        )
        run(['xdotool', 'windowsize', window_id,
             str(width - left - right), str(height - top - bottom)])
        if window is not None:
            # Held against the right and the bottom of the work area. The height
            # is the work area's own, since the window is maximised upwards, and
            # what the terminal rounds off its width is left at its left edge for
            # the browser beside it to take up.
            settled = settled_rect(d, window)
            x = x + width - settled[2]
            y = y + height - settled[3]
        run(['xdotool', 'windowmove', window_id, str(x), str(y)])
    except Exception:
        # Placement is a convenience rather than the reading. No xdotool to
        # move a window with, a desktop that will not answer for one, or a
        # window that has gone, all end here and the reading carries on.
        print(UNPLACED)


def quit_vim(servername):
    """Ask vim to quit, which it refuses to do while anything in it is unwritten."""
    remote(servername, '--remote-send', f'{NORMAL_MODE}:qa<CR>')


def remote(servername, *args):
    """Return what one vim client command said, or None if it did not answer."""
    try:
        return run(['vim', '--servername', servername, *args])
    except (OSError, subprocess.SubprocessError):
        return None


def report_cursor(url, line):
    """Tell the reading where the vim cursor is now.

    vim starts this and leaves it to itself, so a server that has stopped
    listening costs a moment of a process nobody is waiting for and no more.
    """
    request = urllib.request.Request(
        f'{url}/api/cursor',
        data=json.dumps({'line': int(line)}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    try:
        urllib.request.urlopen(request, timeout=TIMEOUT).close()
    except OSError:
        pass


def run(command):
    """Return what a command printed, raising if it is missing, fails or hangs."""
    done = subprocess.run(
        command, capture_output=True, check=True, text=True, timeout=TIMEOUT
    )
    return done.stdout.strip()


def screen_area():
    """Return the strip of screen the windows are placed in, as x, y, width and height.

    The work area rather than the whole screen, so that nothing is put under
    the desktop's panels. Without Xlib there is nothing to ask that of, and the
    whole screen from xdotool is the roughest form of the same answer. Without
    either there is nothing to place windows by at all.
    """
    d = x_display()
    if d is not None:
        area = d.screen().root.get_full_property(
            d.intern_atom('_NET_WORKAREA'), Xatom.CARDINAL
        )
        if area:
            return tuple(area.value[:4])
        return (0, 0, d.screen().width_in_pixels, d.screen().height_in_pixels)
    try:
        width, height = run(['xdotool', 'getdisplaygeometry']).split()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return (0, 0, int(width), int(height))


def servers():
    """Return the names vim answers to on this display, upper cased as vim keeps them."""
    try:
        return run(['vim', '--serverlist']).split()
    except (OSError, subprocess.SubprocessError):
        return []


def settled_rect(d, window):
    """Return where a window ended up, once the desktop has finished with it.

    A move or a resize is a request, answered in the desktop's own time, and a
    terminal answers by settling on the nearest whole number of characters. The
    answer is waited for rather than assumed, so that the window beside it is
    placed against where it really is, and so that vim starts in a terminal that
    has stopped changing size under it.
    """
    was = None
    for _ in range(SETTLE_TRIES):
        time.sleep(SETTLE_WAIT)
        now = frame_rect(d, window)
        if now == was:
            return now
        was = now
    return was


def terminal_window():
    """Return the window the desktop has in front, which is the terminal the reading is in.

    Asking the terminal which window it is would be the plainer answer, and
    mate-terminal answers in WINDOWID, but a terminal that passes on whatever
    was in the environment it started from names a window belonging to somebody
    else. The window in front is the one the command was typed into, and the one
    a launcher has just opened and put there.
    """
    d = x_display()
    if d is not None:
        active = d.screen().root.get_full_property(
            d.intern_atom('_NET_ACTIVE_WINDOW'), Xatom.WINDOW
        )
        if active and active.value[0]:
            return active.value[0]
    try:
        return int(run(['xdotool', 'getactivewindow']))
    except (OSError, ValueError, subprocess.SubprocessError):
        return ''


def windows_of(d, pid):
    """Return the desktop's own list of the windows belonging to a process."""
    listed = d.screen().root.get_full_property(
        d.intern_atom('_NET_CLIENT_LIST'), Xatom.WINDOW
    )
    if not listed:
        return []
    windows = []
    for xid in listed.value:
        window = d.create_resource_object('window', xid)
        owner = window.get_full_property(d.intern_atom('_NET_WM_PID'), Xatom.CARDINAL)
        if owner and owner.value[0] == pid:
            windows.append(window)
    return windows


def x_display():
    """Return the X display, or None where there is nothing to talk to it with."""
    if display is None:
        return None
    try:
        return display.Display()
    except Exception:
        # Xlib raises several unrelated errors for a display it cannot reach,
        # and none of them is worth stopping a reading for.
        return None


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
