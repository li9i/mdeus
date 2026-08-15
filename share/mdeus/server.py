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
routes that speak to vim answer only while editing, and so do the two vim
speaks back on: where its cursor is, and whether the vim now leaving is taking
the whole reading with it or handing the page back.

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
tree the reading started in. Anything resolving outside it is not found.

One thing in the page writes to the document: a task list box pressed there is
that box's own line of the source rewritten, and nothing else in the file is
touched. While vim is up the press is sent to vim instead, so a document
somebody is editing is never written round the back of them.
"""

import json
import mimetypes
import os
import re
import select
import sys
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
DEFAULT_PORT = 8766
FILE_ROUTE = '/file/'
HOST = '127.0.0.1'
ICON_ROUTE = '/icon.png'
ICON_SIZE = 128
MAX_BODY = 256 * 1024
NAME = 'mdeus'
RETURN_GRACE = 1
TASK_ITEM = re.compile(r'([ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+\[)([ xX])\]')
TELL_TICK = 0.05
TICKING = threading.Lock()
WATCH_TICK = 0.25


def build_server(reading, port=DEFAULT_PORT):
    """Bind a server for one reading, taking any free port if the preferred one is busy."""
    handler = partial(ReadingHandler, reading=reading)
    try:
        return ReadingServer((HOST, port), handler)
    except OSError:
        return ReadingServer((HOST, 0), handler)


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
    classes = (
        f"{state['theme']} reader"
        + (' middle' if state['middle'] else '')
        + (' wide' if state['wide'] else '')
    )
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
    reading.over.set()
    reading.asked.set()


def start(document, servername, editable=False):
    """Bind a reading and return it, its server, and the address it landed on."""
    reading = Reading(document, servername, editable=editable)
    bound = build_server(reading)
    return bound, reading, f'http://{HOST}:{bound.server_port}'


def tick_line(path, line, done):
    """Write one task list item as ticked or unticked, and say whether it was.

    Only the mark between the brackets is written. The line keeps its
    indentation, its list marker, its words and its ending, so a document
    ticked in the page reads afterwards as the same document with one character
    changed, and a document under version control shows exactly that.

    A line that is not a task list item is refused rather than rewritten, which
    is what answers a page drawn from a version of the document that has since
    been written by somebody else: the lines have moved under it, and the tick
    lands nowhere rather than on whatever is at that line now. The refusal is
    the page's to act on.

    One press is written at a time. The whole document is read to change one
    line of it and the whole of it is written back, and the page sends the next
    press without waiting for the last to land, so two presses served at once
    would each write back the document they read and the one that lost would be
    a box the page shows ticked and the document does not carry.
    """
    with TICKING:
        try:
            lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return False
        if not 1 <= line <= len(lines):
            return False
        found = TASK_ITEM.match(lines[line - 1])
        if found is None:
            return False
        rest = lines[line - 1][found.end(2):]
        lines[line - 1] = f"{found.group(1)}{'x' if done else ' '}{rest}"
        try:
            path.write_text(''.join(lines), encoding='utf-8')
        except OSError:
            return False
        return True


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

    A body naming no full width setting or no centring setting reads as that
    setting being on, which is the same reading the stored state gets when its
    file has no field for it.
    """
    theme = body.get('theme')
    if theme not in THEMES:
        raise ValueError('unknown theme')
    return {
        'contents': bool(body.get('contents')),
        'middle': bool(body.get('middle', True)),
        'theme': theme,
        'wide': bool(body.get('wide', True)),
    }


def wanted_tick(body):
    """Return the line a tick names and whether it is now ticked, or raise ValueError."""
    try:
        return int(body['line']), bool(body['done'])
    except (KeyError, TypeError) as error:
        raise ValueError('no tick') from error


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
        self.alone = None
        self.asked = threading.Event()
        self.asks = 0
        self.clicks = 0
        self.current = document.resolve()
        self.cursor = None
        self.drawn = threading.Event()
        self.editable = editable
        self.editing = False
        self.ends = False
        self.holding = 0
        self.holds = threading.Lock()
        self.heard, self.said = os.pipe()
        os.set_blocking(self.said, False)
        self.over = threading.Event()
        self.root = self.current.parent
        self.servername = servername
        self.waiting = False
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

        Every asking is counted as well as recorded, because two of them in a
        row can ask for the same thing and still be two. A press that asks vim
        to go while vim is refusing to go, made again once the reader has
        written their work, says nothing new about what is wanted and everything
        about its being wanted again.
        """
        if editing and not self.editable:
            return
        self.asks += 1
        self.wanted = editing
        self.asked.set()
        try:
            os.write(self.said, b'.')
        except OSError:
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

    def do_GET(self):
        """Answer a read. Even a refusal is JSON, so the page can decode every reply."""
        parts = urlsplit(self.path)
        path = parts.path
        if path == '/' or path[1:] == self.reading.servername:
            self.send_page()
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

    def do_POST(self):
        """Answer a write. Every refusal is caught here rather than dropped."""
        try:
            body = self.read_json()
            if self.path == '/api/cursor' and self.reading.editing:
                self.reading.cursor = wanted_line(body)
                if body.get('clicked'):
                    self.reading.clicks += 1
                self.send_json({'ok': True})
            elif self.path == '/api/drawn':
                self.reading.drawn.set()
                self.send_json({'ok': True})
            elif self.path == '/api/edit':
                self.reading.ask(bool(body.get('editing')))
                self.send_json({'editing': self.reading.editing})
            elif self.path == '/api/ending' and self.reading.editing:
                self.reading.ends = True
                self.send_json({'ok': True})
            elif self.path == '/api/jump' and self.reading.editing:
                vimlink.jump(self.reading.servername, *wanted_block(body))
                self.send_json({'ok': True})
            elif self.path == '/api/state':
                state = wanted_state(body)
                save_state(self.reading.current, state)
                self.send_json(state)
            elif self.path == '/api/tick':
                self.send_json({'ticked': self.tick(*wanted_tick(body))})
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
        self.send_header('Connection', 'close')
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
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
            pass
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
        """Return the object a request carries, refusing anything the page could not send.

        A length below nothing is refused rather than read. Read as it stands it
        says to go on reading until the sender stops, which is to say for as
        long as it likes and as much as it likes, and the turn spent on that
        request never comes back.

        What comes out has to be an object, since every route reads its request
        by name, and it has to be shallow enough for JSON itself to have read
        without running out of stack. Neither is anything the page would send,
        and both arrive from whatever else on the machine cares to send them.
        """
        length = int(self.headers.get('Content-Length', 0))
        if length < 0:
            raise ValueError('no such body')
        if length > MAX_BODY:
            raise ValueError('request too large')
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError('malformed JSON') from error
        if not isinstance(body, dict):
            raise ValueError('malformed JSON')
        return body

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
        head = [
            f'    <link rel="icon" href="{ICON_ROUTE}" />',
            '    <link rel="stylesheet" href="/assets/themes.css" />',
            '    <link rel="stylesheet" href="/assets/sync.css" />',
            '    <script src="/assets/page.js" defer></script>',
            '    <script src="/assets/sync.js" defer></script>',
        ]
        page = page_html(self.name(), load_state(self.reading.current), '\n'.join(head))
        self.send_bytes(page.encode('utf-8'), 'text/html')

    def snapshot(self):
        """Return what the page draws, or the reply that says the file is gone."""
        common = {
            'editable': self.reading.editable,
            'editing': self.reading.editing,
            'mtime': self.mtime(),
            'name': self.name(),
            'state': load_state(self.reading.current),
        }
        try:
            source = self.reading.current.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return dict(common, gone=True)
        rendered = render_document(source, image_src=self.image_src, tickable=True)
        return dict(common, blocks=rendered['blocks'], outline=rendered['outline'])

    def tick(self, line, done):
        """Write a tick into the document, and say whether it landed.

        While vim is up the document is vim's, so the tick is sent there and
        left unwritten for whoever is editing to save with the rest of their
        work. Writing the file under vim instead would put a question up in the
        pane, and a vim with a question up hears nothing else until it has been
        answered.

        While the page is alone there is nobody holding the document but the
        reading, and the line is rewritten in the file. A vim warmed out of
        sight behind the page holds the document too, and asks whether to load a
        file written under it, so vim is told first that this one is the
        reading's own and takes it without asking. What another program writes
        is asked about as it should be, which is the point of telling the two
        apart.
        """
        if self.reading.editing:
            return vimlink.tick(
                self.reading.servername, line, done, self.reading.current
            )
        vimlink.mine(self.reading.servername, True)
        ticked = tick_line(self.reading.current, line, done)
        if not ticked:
            vimlink.mine(self.reading.servername, False)
        return ticked


class ReadingServer(ThreadingHTTPServer):
    """The server one reading is answered from.

    It differs in one thing from the server it is built on: a page that goes
    while it is being answered is not something the reader has to hear about.
    Closing a browser window drops whatever that page had in flight, and the
    reading finds out by the write it was in the middle of failing. A stack
    printed for that says something has gone wrong where nothing has, over a
    terminal that belongs to whoever started the reading.

    Everything else is still said. A fault the reading swallows is a fault
    nobody can act on.
    """

    def handle_error(self, request, client_address):
        """Say nothing where the page has gone, and speak up for anything else."""
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)
