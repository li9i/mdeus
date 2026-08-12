"""
Serve one markdown document to a browser on this machine.

The page is an empty shell. Everything in it is drawn from what this server
sends: the document as blocks carrying their source lines, the heading outline
the contents list is built from, and the stored theme. This server watches the
source file and tells the page the moment it is written, so a write from any
editor is on the screen as soon as it lands on the disk.

A reading is either viewing, which is the page alone, or editing, which is the
page with vim beside it. The page asks to move between the two through
/api/edit, and this server does no more than record the asking and say what the
state is: the window and vim are the session's business, not this file's. The
routes that speak to vim answer only while editing.

The page holds the reading open by one request that is never answered, and the
reading ends a moment after that request's connection drops. That connection is
also how the page is told anything: down it goes a line whenever the document is
written or vim comes or goes. Nothing is asked of the page's clock, because a
browser is free to slow the timers of a window that is not in front of you and to
stop them outright while the machine sleeps, and a reading resting on one of
those ticks is a reading that dies behind its own window, or one that shows a
file as it was a minute ago. A connection survives both, and a window closed or a
browser killed drops it there and then.

Images and links to other documents are served only from inside the directory
tree the reading started in. Anything resolving outside it is not found. The
source document is opened read only and is never written to.
"""

import json
import mimetypes
import os
import select
import threading
import time
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import vimlink
from render import render_document
from state import THEMES, load_state, save_state

ASSET_DIR = Path(__file__).resolve().parent
# Where a reading starts looking. A port already taken sends the reading to
# the next free one, so this is a starting point rather than a fixed address,
# and several readings at once each end up somewhere of their own.
DEFAULT_PORT = 8766
# Where an image beside the document is served from. The page itself is served
# at the root, so a document's own relative target would resolve against that
# and name nothing.
FILE_ROUTE = '/file/'
HOST = '127.0.0.1'
# Where the image a reading wears is served from, and which of the sizes it
# ships goes down that route. The icons sit outside the directory the page's own
# files are served from, so they come by a route of their own rather than as one
# more asset. The larger size is the one sent, since it is the browser and the
# panel that decide what they are drawing it at.
ICON_ROUTE = '/icon.png'
ICON_SIZE = 128
MAX_BODY = 256 * 1024
# What the command is called. It names the icon files and the window class, and
# nothing else: a reading is titled by the document it is showing and says the
# command nowhere.
NAME = 'mdeus'
# How long a reading with no page holding it is left standing, in seconds. A
# reload lets go on its way out and the page coming back takes hold before it
# draws anything, so the wait is long enough to carry a reload across, and short
# enough that closing the window ends the reading while the hand is still on the
# mouse.
RETURN_GRACE = 1
# How often a held page's document is looked at, in seconds. This is the whole of
# what stands between saving in vim and seeing it on the page, so it is short
# enough to read as at once, and a look is one stat of one file.
TELL_TICK = 0.05
# How often the watcher looks at the clock, in seconds. Short enough that it
# adds little to the wait it is timing, long enough to cost nothing.
WATCH_TICK = 0.25


def build_server(reading, port=DEFAULT_PORT):
    """Bind a server for one reading, taking any free port if the preferred one is busy."""
    handler = partial(ReadingHandler, reading=reading)
    try:
        return ThreadingHTTPServer((HOST, port), handler)
    except OSError:
        return ThreadingHTTPServer((HOST, 0), handler)


def icon_path(size):
    """Return the file the reading's image of one size lives in.

    The images sit one directory above this file, so the path is found from the
    checkout however the command was reached. Both the panel and the page ask
    for them, so the tree is named here rather than again in each file that
    wants it.
    """
    return ASSET_DIR.parent / 'icons' / 'hicolor' / f'{size}x{size}' / 'apps' / f'{NAME}.png'


def page_html(title, state, head, body_tail=''):
    """Return the empty page. The controls and the document are filled in by page.js.

    The one skeleton behind both a served reading and a printed copy. What
    differs between them is how the stylesheet and the script arrive, which is
    the caller's to hand in: linked from this server, or inlined whole.
    """
    # Both settings the stylesheet reads are already on the root element here,
    # so that the first paint is the page the reader left rather than an
    # unstyled one for a moment, or one that rewraps as the script catches up.
    # The reader marker beside them says this is a page for reading, which is
    # what drops the github theme below the size github.com itself sets.
    classes = f"{state['theme']} reader" + (' wide' if state['wide'] else '')
    return f"""<!doctype html>
<html lang="en" class="{classes}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
{head}
  </head>
  <body>
    <div class="controls"></div>
    <main class="doc"></main>
{body_tail}  </body>
</html>
"""


def resolve_inside(root, relative):
    """Return the file a request names, or None if it is not a file inside the tree.

    The path is resolved before it is compared, so a symlink pointing out of
    the tree is caught rather than followed. An absolute path lands outside
    the root and is caught by the same comparison.
    """
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def serve(server, reading):
    """Serve until interrupted, or until no page is holding the reading."""
    threading.Thread(target=watch_pages, args=(server, reading), daemon=True).start()
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    # The reading is over, and whoever is waiting on it is told so twice: the
    # flag is what the wait looks at, and the event is what wakes it to look.
    # Without the waking it goes on waiting out the turn it was in, which is a
    # second of a reading whose page closed a moment ago.
    reading.over.set()
    reading.asked.set()


def start(document, servername, editable=False):
    """Bind a reading and return it, its server, and the address it landed on."""
    reading = Reading(document, servername, editable=editable)
    bound = build_server(reading)
    return bound, reading, f'http://{HOST}:{bound.server_port}'


def wanted_block(body):
    """Return the first and last source lines a request names, or raise ValueError.

    The page knows which lines every block was built from, so a jump carries
    both ends of them and vim marks the whole of the block without this having
    to read the document again to find where it ends.
    """
    try:
        return int(body['line']), int(body['last'])
    except (KeyError, TypeError) as error:
        raise ValueError('no block') from error


def wanted_line(body):
    """Return the source line a request names, or raise ValueError."""
    try:
        return int(body['line'])
    except (KeyError, TypeError) as error:
        raise ValueError('no line') from error


def wanted_state(body):
    """Return the state a request asks to store, or raise ValueError.

    A body naming no full width setting reads as the setting being on, which is
    the same reading the stored state gets when its file has no field for it.
    """
    theme = body.get('theme')
    if theme not in THEMES:
        raise ValueError('unknown theme')
    return {
        'contents': bool(body.get('contents')),
        'theme': theme,
        'wide': bool(body.get('wide', True)),
    }


def watch_pages(server, reading):
    """Stop the server once no page is holding the reading open any longer.

    A reading opened from the file manager has no terminal to interrupt, so the
    page going is what ends it. Every page holds the reading by a request that is
    never answered, so a window closed, a tab closed and a browser killed all
    look the same from here: the connection drops and nothing holds the reading
    any more.

    The letting go is waited on rather than acted on at once, because a reload
    lets go on its way out exactly as a close does. The page that comes back
    takes hold well inside the wait.

    Nothing is timed against the page's own clock, so a window left in the
    background for an hour, or a machine asleep for a night, keeps its reading.
    A reading no page has ever held keeps serving as well, so one whose browser
    never opened stays reachable by hand.

    A reading that is editing is held up by vim instead, and the page is not
    asked to hold it. Otherwise closing the page of a reading whose vim has
    unsaved work would stop the server from under work vim is quite right to be
    refusing to let go of.
    """
    while True:
        time.sleep(WATCH_TICK)
        alone = reading.alone
        if reading.editing:
            continue
        if alone is not None and time.monotonic() - alone > RETURN_GRACE:
            server.shutdown()
            return


class Reading:
    """One document being read, and the tree it may serve files from."""

    def __init__(self, document, servername, editable=False):
        # When the reading was left with no page holding it, or nothing while one
        # holds it. It is nothing to begin with as well, since a reading no page
        # has ever held is one whose browser has yet to open rather than one
        # whose page has gone.
        self.alone = None
        # Whoever is waiting on the page, woken whenever the page asks to move
        # between viewing and editing.
        self.asked = threading.Event()
        # How many clicks vim has reported. A click there is the one thing that
        # brings the page along, and the throttled report of the same line
        # follows a moment later, so the page is told a running count rather
        # than a flag the report behind it would take back.
        self.clicks = 0
        self.current = document.resolve()
        self.cursor = None
        # Set once the page has said it has drawn the document it was sent. vim
        # is started after that and not before, so that the browser has the
        # machine to itself while it is doing the one thing the reader is waiting
        # on.
        self.drawn = threading.Event()
        # Whether the Edit toggle belongs on the page at all, which is to say
        # whether there is a desktop session to open vim into.
        self.editable = editable
        # Whether vim is up. Written by the session that opens and closes it,
        # and read here to decide which routes answer.
        self.editing = False
        # How many pages are holding the reading open, and the lock that count
        # and the moment at the top of this are moved under together. A reload can
        # have the page coming back taking hold before the one going has let go,
        # so the two overlap and what is kept is a count rather than a flag.
        self.holding = 0
        self.holds = threading.Lock()
        # The two ends of the pipe an asking is also said down, for a waiter
        # that cannot hear the event above. A reading with vim up is inside its
        # X event loop, waiting on a socket, and one wait can cover a socket and
        # a pipe but not a socket and an event. Without this the box being
        # unticked is not noticed until that wait times out, which is a quarter
        # of a second of a session nobody wants any more.
        self.heard, self.said = os.pipe()
        # Written to without waiting, so that a page asking many times over
        # while nobody is reading the other end cannot hold the server up.
        os.set_blocking(self.said, False)
        # Whether the reading has ended, set when the server stops. Whoever is
        # holding the reading up waits on this rather than on the serving
        # thread, which is still tidying itself away for a moment after the
        # last request has been answered.
        self.over = threading.Event()
        # The tree is fixed by the document the reading started at. Following
        # a link moves the current document but never widens what is served.
        self.root = self.current.parent
        # The name vim answers to and the name the page is served under. It is
        # settled before the page exists, because the browser writes the name
        # of the window it puts up out of the address it was given, and that
        # name is the whole of how a reading finds its own page's window.
        self.servername = servername
        # Whether a vim is up and waiting to be shown, which is a vim started
        # ahead of the toggle so that pressing it has nothing left to wait for.
        # It answers to the servername like any other, so anything the reading
        # sends vim reaches it, and a link followed while it waits is followed
        # by it too.
        self.waiting = False
        # What the page last asked for. The truth is `editing` above; this is
        # the wish, left where whoever acts on it will find it.
        self.wanted = False

    def ask(self, editing):
        """Record what the page asked for and wake whoever acts on it.

        A reading with no desktop behind it has nowhere to open vim into, so a
        request to edit is not recorded rather than acted on and then found
        impossible. Its page carries no Edit toggle, so nothing belonging to the
        reading is asking. A request to stop is always taken, since it can
        always be honoured.

        Said twice, because a reading waits in two quite different ways
        depending on which of its states it is in. Between sessions it waits on
        the event, and inside one it waits on its X connection, where only
        something with a file of its own can reach it.
        """
        if editing and not self.editable:
            return
        self.wanted = editing
        self.asked.set()
        try:
            os.write(self.said, b'.')
        except OSError:
            # Nobody is reading, and the pipe is full of earlier askings. The
            # wish is recorded either way, and a session opening later reads it
            # rather than being told it.
            pass

    def hold(self):
        """Take the reading into a page's keeping."""
        with self.holds:
            self.holding += 1
            self.alone = None

    def let_go(self):
        """Give the reading back, and note the moment where the last page did.

        The moment is what the reading is ended on, a grace later, so a reload is
        not read as the window having been closed.
        """
        with self.holds:
            self.holding -= 1
            if not self.holding:
                self.alone = time.monotonic()


class ReadingHandler(BaseHTTPRequestHandler):
    """Serve the reading page and the small JSON API behind it."""

    protocol_version = 'HTTP/1.1'

    def __init__(self, *args, reading, **kwargs):
        self.reading = reading
        super().__init__(*args, **kwargs)

    def do_GET(self):  # noqa: N802 (name fixed by BaseHTTPRequestHandler)
        """Answer a read. Even a refusal is JSON, so the page can decode every reply."""
        parts = urlsplit(self.path)
        path = parts.path
        # A reading answers at its own name as well as at the root, because the
        # browser names the window it puts up after the address it was given,
        # and that name is what tells one reading's page window from another's.
        # Several readings run at once and they all serve on the same host, so
        # the host says nothing about which reading a window belongs to.
        if path == '/' or path[1:] == self.reading.servername:
            self.send_page()
        # The routes that speak to vim are open only while vim is up, so a
        # reading that is viewing has no more of an API than a bare page needs.
        elif path == '/api/cursor' and self.reading.editing:
            self.send_json({'clicks': self.reading.clicks, 'line': self.reading.cursor})
        elif path.startswith('/assets/'):
            self.send_from(ASSET_DIR, unquote(path[len('/assets/') :]))
        elif path == '/doc':
            self.send_doc(parse_qs(parts.query).get('path', [''])[0])
        elif path.startswith(FILE_ROUTE):
            self.send_from(self.reading.root, unquote(path[len(FILE_ROUTE) :]))
        elif path == '/hold':
            self.hold_open()
        elif path == ICON_ROUTE:
            self.send_icon()
        else:
            self.send_json({'error': 'not found'}, code=404)

    def do_POST(self):  # noqa: N802 (name fixed by BaseHTTPRequestHandler)
        """Answer a write. Every refusal is caught here rather than dropped."""
        try:
            body = self.read_json()
            if self.path == '/api/cursor' and self.reading.editing:
                self.reading.cursor = wanted_line(body)
                if body.get('clicked'):
                    self.reading.clicks += 1
                self.send_json({'ok': True})
            elif self.path == '/api/drawn':
                # Said by the page once the document is on the screen, which is
                # where the reading learns that the window it opened is finished
                # and the machine is free for the vim it warms behind it.
                self.reading.drawn.set()
                self.send_json({'ok': True})
            elif self.path == '/api/edit':
                # Recorded and answered at once. Opening vim takes a second and
                # closing it may be refused outright, so what comes back is the
                # state as it stands rather than the state that was asked for,
                # and the outcome reaches the page down the connection it holds.
                self.reading.ask(bool(body.get('editing')))
                self.send_json({'editing': self.reading.editing})
            elif self.path == '/api/jump' and self.reading.editing:
                vimlink.jump(self.reading.servername, *wanted_block(body))
                self.send_json({'ok': True})
            elif self.path == '/api/state':
                state = wanted_state(body)
                save_state(state)
                self.send_json(state)
            else:
                self.send_json({'error': 'not found'}, code=404)
        except ValueError as error:
            self.send_json({'error': str(error)}, code=400)

    def hold_open(self):
        """Answer the page's headers, then hold its connection and say what moves down it.

        This is how a reading knows its page is still there, and how the page
        knows anything at all. The reply is opened and never finished, so the
        connection stays up for as long as the page does, and the page is asked
        for nothing: it holds the reading by being there rather than by
        remembering to speak, which is what carries a reading through a window
        left in the background and a machine put to sleep.

        Down that connection goes one line for each of the two things the page
        cannot see for itself: when the document was last written, and whether
        vim is up. Both are sent as they stand the moment the page takes hold,
        and again whenever either moves. A write is therefore on the screen as
        soon as it is noticed, rather than whenever a page that had to ask
        happened to ask next, and a browser slowing the timers of a window it is
        not showing cannot leave a reading behind the file it is reading.

        The socket becoming readable is the page going. Nothing is ever sent up
        this connection, so there is nothing else it could be, and a browser
        closing a window drops it in the same movement. A page that goes while a
        line is being written to it is the same news arriving the other way
        round.

        The wait is broken into turns so that the reading ending also lets go.
        Otherwise the last page of a reading stopped by ctrl-c would sit here
        holding a connection nobody is on the other end of.
        """
        self.send_response(200)
        self.send_header('Cache-Control', 'no-store')
        # Said outright, since the reply carries no length and ends where the
        # connection does. It is also what stops this connection being offered
        # back for another request afterwards.
        self.send_header('Connection', 'close')
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        # Nothing may be held back to see what kind of file this is. The lines
        # come one at a time and minutes may pass between them, and a browser
        # sniffing at the first would keep the page from hearing it.
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.reading.hold()
        told = None
        try:
            while not self.reading.over.is_set():
                said = {'editing': self.reading.editing, 'mtime': self.mtime()}
                if said != told:
                    told = said
                    self.wfile.write(json.dumps(said).encode('utf-8') + b'\n')
                if select.select([self.connection], [], [], TELL_TICK)[0]:
                    return
        except OSError:
            pass  # the page went as it was being spoken to
        finally:
            self.reading.let_go()

    def image_src(self, target):
        """Return where this server answers for an image beside the current document.

        The page is served at the root, so a document's own relative target
        would be read against that and name nothing. The address is built from
        the root of the tree rather than from the document holding the image,
        since a document reached by following a link sits further down. An
        image resolving outside the tree is left as it was written, and the
        reading serves nothing for it.
        """
        path = (self.reading.current.parent / unquote(target)).resolve()
        try:
            relative = path.relative_to(self.reading.root)
        except ValueError:
            return target
        return FILE_ROUTE + quote(relative.as_posix())

    def log_message(self, fmt, *args):
        """Stay quiet, the terminal is the user's."""

    def mtime(self):
        """Return when the current document was last written, or nothing once it is gone."""
        try:
            return self.reading.current.stat().st_mtime_ns
        except OSError:
            return None

    def name(self):
        """Return the current document's name, as far down the tree as it sits."""
        return str(self.reading.current.relative_to(self.reading.root))

    def read_json(self):
        """Return the decoded request body."""
        length = int(self.headers.get('Content-Length', 0))
        if length > MAX_BODY:
            raise ValueError('request too large')
        try:
            return json.loads(self.rfile.read(length) or b'{}')
        except json.JSONDecodeError as error:
            raise ValueError('malformed JSON') from error

    def send_bytes(self, payload, content_type, code=200):
        """Send one complete response."""
        self.send_response(code)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def send_doc(self, relative):
        """Send the current document, moving the reading to a linked one first if asked."""
        if relative:
            target = resolve_inside(self.reading.root, relative)
            if target is None:
                self.send_json({'error': 'not found'}, code=404)
                return
            self.reading.current = target
            # vim follows the link too, so that both halves of a reading are
            # always of the same file and the sync never marks a document vim
            # does not have open. A vim still waiting to be shown follows it as
            # well, so that it is already on the right document when it is.
            if self.reading.editing or self.reading.waiting:
                vimlink.edit(self.reading.servername, target)
        self.send_json(self.snapshot())

    def send_from(self, root, relative):
        """Send a file from inside one tree, or refuse to look outside it.

        Both the page's own stylesheet and script and the images a document
        points at come this way, since the only difference between them is
        which tree they must stay inside.
        """
        path = resolve_inside(root, relative)
        if path is None:
            self.send_json({'error': 'not found'}, code=404)
            return
        self.send_bytes(path.read_bytes(), mimetypes.guess_type(path)[0] or 'text/plain')

    def send_icon(self):
        """Send the image the reading wears, or say there is none where the file is gone.

        A page that is served an error here is no worse off than one that named
        no icon at all, so a missing file ends as a refusal rather than as a
        reading that will not open.
        """
        path = icon_path(ICON_SIZE)
        if not path.is_file():
            self.send_json({'error': 'not found'}, code=404)
            return
        self.send_bytes(path.read_bytes(), 'image/png')

    def send_json(self, payload, code=200):
        """Send a JSON response."""
        self.send_bytes(json.dumps(payload).encode('utf-8'), 'application/json', code)

    def send_page(self):
        """Send the empty page, linking the stylesheets and the scripts it draws with."""
        # The two files behind the sync with vim are linked by every reading,
        # whether or not vim is up, because editing may begin at any moment and
        # a page that had to reload to gain them would lose its place in the
        # document. They cost nothing while a reading is viewing: sync.js asks
        # for the vim cursor only while editing, and its stylesheet marks blocks
        # that are never marked. They load after page.js, which draws the
        # document they mark.
        # The icon is named by the page because the window a reading opens in
        # belongs to the browser, and a browser window wears the icon its page
        # names. It is linked by a served reading only: a printed copy reaches
        # for no file of its own, and an icon is not worth breaking that for.
        head = [
            f'    <link rel="icon" href="{ICON_ROUTE}" />',
            '    <link rel="stylesheet" href="/assets/themes.css" />',
            '    <link rel="stylesheet" href="/assets/sync.css" />',
            '    <script src="/assets/page.js" defer></script>',
            '    <script src="/assets/sync.js" defer></script>',
        ]
        page = page_html(self.name(), load_state(), '\n'.join(head))
        self.send_bytes(page.encode('utf-8'), 'text/html')

    def snapshot(self):
        """Return what the page draws, or the reply that says the file is gone."""
        # The state travels with the document because the page reads its theme
        # from the first reply it gets, which may well be the gone one. The
        # modification time travels with it for the same reason the blocks do:
        # it is the time of the document the page is about to draw, so what the
        # page is told next is measured against what is on the screen.
        # The document's name travels with it because the page writes its own
        # title as it draws, so that following a link to another document says
        # so on the tab and, in a reading with vim beside it, on the panel.
        # Whether the Edit toggle belongs on the page travels with the document
        # rather than with the markup, because the controls are built from the
        # first reply and a printed copy, which is answered by no server at all,
        # then carries no toggle without having to be told not to.
        common = {
            'editable': self.reading.editable,
            # Whether vim is up travels with the document as well as down the
            # held connection, so that a page reloaded in the middle of a session
            # draws its Edit toggle pressed on the first paint rather than a
            # moment later, once it has been told.
            'editing': self.reading.editing,
            'mtime': self.mtime(),
            'name': self.name(),
            'state': load_state(),
        }
        try:
            source = self.reading.current.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return dict(common, gone=True)
        rendered = render_document(source, image_src=self.image_src)
        return dict(common, blocks=rendered['blocks'], outline=rendered['outline'])
