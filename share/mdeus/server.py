"""
Serve one markdown document to a browser on this machine.

The page is an empty shell. Everything in it is drawn from what this server
sends: the document as blocks carrying their source lines, the heading outline
the contents list is built from, and the stored theme. The page polls for the
source file's modification time and redraws when it moves, so a write from any
editor is picked up.

Images and links to other documents are served only from inside the directory
tree the reading started in. Anything resolving outside it is not found. The
source document is opened read only and is never written to.
"""

import json
import mimetypes
import sys
import threading
import time
import uuid
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import vimlink
from render import render_document

ASSET_DIR = Path(__file__).resolve().parent
# One above the spec review tool's port, so a reading and a review opened at
# the same time do not push each other onto a fallback port.
DEFAULT_PORT = 8766
# The share of the window the browser pane takes in a reading with vim beside
# it, before the divider between them has ever been dragged. It matches the
# split the same document read in a terminal already uses.
DEFAULT_SPLIT = 0.44
# Long enough that a page reloading or a machine pausing for a moment does not
# end the reading, short enough that a closed window does not leave a server
# behind.
HEARTBEAT_TIMEOUT = 10
HOST = '127.0.0.1'
MAX_BODY = 256 * 1024
# How far the divider may be dragged either way. Far enough to read in either
# pane alone, and never so far that the other one has nothing left to draw in.
MAX_SPLIT = 0.85
MIN_SPLIT = 0.15
STATE_PATH = Path.home() / '.config' / 'mdview' / 'state.json'
THEMES = ('browser', 'report', 'github')


def block_range(document, line):
    """Return the first and last source lines of the block that begins at this line.

    The page sends only the line it wants vim on, and the block it came from is
    found again here, so that vim can mark the whole of the block without the
    page having to say any more than it already does. A line no block begins,
    or a document that will not be read, gives that one line back on its own.
    """
    try:
        source = document.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return (line, line)
    for block in render_document(source)['blocks']:
        if block['line_start'] == line:
            return (line, block['line_end'])
    return (line, line)


def build_server(reading, port=DEFAULT_PORT):
    """Bind a server for one reading, taking any free port if the preferred one is busy."""
    handler = partial(ReadingHandler, reading=reading)
    try:
        return ThreadingHTTPServer((HOST, port), handler)
    except OSError:
        return ThreadingHTTPServer((HOST, 0), handler)


def load_split():
    """Return the share of the window the browser pane takes.

    A share the divider could not have left behind, whether it is missing,
    unreadable or outside what can be dragged to, means the reading opens at
    the split the very first one did.
    """
    try:
        share = float(stored_state()['split'])
    except (KeyError, TypeError, ValueError):
        return DEFAULT_SPLIT
    return share if MIN_SPLIT <= share <= MAX_SPLIT else DEFAULT_SPLIT


def load_state():
    """Return the stored theme and contents setting, or the ones a first reading gets.

    A missing, unreadable or malformed file is not an error, and neither is a
    theme naming something that does not exist. Any of them means the reading
    opens the way the very first one did.
    """
    stored = stored_state()
    if stored.get('theme') in THEMES:
        return {'contents': bool(stored.get('contents')), 'theme': stored['theme']}
    return {'contents': False, 'theme': 'browser'}


def main(argv):
    """Serve one reading with vim beside it, saying on its output where it landed.

    The command that starts such a reading is a shell script, and it has to be
    told the port, since a reading already up may hold the preferred one.
    """
    document, servername = argv
    reading = Reading(Path(document), servername=servername)
    bound = build_server(reading)
    print(f'http://{HOST}:{bound.server_port}', flush=True)
    serve(bound, reading)


def page_html(name, theme, vim):
    """Return the empty page. The controls and the document are filled in by page.js."""
    # The two files behind the sync with vim are linked only by a reading that
    # has vim beside it. Anyone may ask for them, so the markup is what keeps
    # them out of a reading that is only a browser. They load after page.js,
    # which draws the document they mark.
    sync = (
        '\n    <link rel="stylesheet" href="/assets/bmvim.css" />'
        '\n    <script src="/assets/bmvim.js" defer></script>'
        if vim
        else ''
    )
    # The theme is already on the root element here so that the first paint is
    # the theme the reader chose, rather than an unstyled page for a moment.
    # The reader marker beside it says this is a page for reading rather than
    # the spec review tool, which shares the stylesheet and sizes github larger.
    return f"""<!doctype html>
<html lang="en" class="{theme} reader">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(name)}</title>
    <link rel="stylesheet" href="/assets/themes.css" />
    <script src="/assets/page.js" defer></script>{sync}
  </head>
  <body>
    <div class="controls"></div>
    <main class="doc"></main>
  </body>
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


def save_split(share):
    """Store where the divider was left, for the next reading to open at."""
    save_state({'split': round(share, 4)})


def save_state(state):
    """Write the state file atomically, so a reading never reads half a file.

    What is written is merged into what is already there. Two things store into
    this file and neither knows the other's field: the page stores the theme
    and the contents setting, and a reading with vim beside it stores where the
    divider was left.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own for every write, beside the target so the rename stays
    # on one filesystem. Several readings may run at once, and one fixed
    # temporary name would let two of them fill the same file and each rename
    # the other's content into place.
    temp = STATE_PATH.with_name(f'{STATE_PATH.name}.{uuid.uuid4().hex}.tmp')
    merged = dict(stored_state(), **state)
    temp.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8')
    temp.replace(STATE_PATH)


def serve(server, reading):
    """Serve until interrupted, or until the page stops answering."""
    threading.Thread(target=watch_heartbeat, args=(server, reading), daemon=True).start()
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def stored_state():
    """Return what the state file holds, or nothing where it holds nothing usable."""
    try:
        stored = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def wanted_line(body):
    """Return the source line a request names, or raise ValueError."""
    try:
        return int(body['line'])
    except (KeyError, TypeError) as error:
        raise ValueError('no line') from error


def wanted_state(body):
    """Return the state a request asks to store, or raise ValueError."""
    theme = body.get('theme')
    if theme not in THEMES:
        raise ValueError('unknown theme')
    return {'contents': bool(body.get('contents')), 'theme': theme}


def watch_heartbeat(server, reading):
    """Stop the server once the page it was opened for has gone quiet.

    A reading opened from the file manager has no terminal to interrupt, so a
    page that has stopped speaking is what ends it. The clock starts at the
    first heartbeat, so a reading whose browser never opened keeps serving and
    stays reachable by hand.
    """
    while True:
        time.sleep(1)
        beat = reading.beat
        if beat is not None and time.monotonic() - beat > HEARTBEAT_TIMEOUT:
            server.shutdown()
            return


class Reading:
    """One document being read, and the tree it may serve files from."""

    def __init__(self, document, servername=None):
        self.beat = None
        # How many clicks vim has reported. A click there is a jump the page
        # goes to whatever the distance, and the throttled report of the same
        # line follows a moment later, so the page is told a running count
        # rather than a flag the report behind it would take back.
        self.clicks = 0
        self.current = document.resolve()
        self.cursor = None
        # The tree is fixed by the document the reading started at. Following
        # a link moves the current document but never widens what is served.
        self.root = self.current.parent
        # The name vim answers to, where a reading has vim beside it. It is
        # what the page asks for the cursor line, and what the routes that
        # speak to vim exist for at all.
        self.servername = servername


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
        if path == '/':
            self.send_page()
        # The routes that speak to vim are there only while vim is, so a
        # reading that is only a browser has no more of an API than before.
        elif path == '/api/cursor' and self.reading.servername:
            self.send_json({'clicks': self.reading.clicks, 'line': self.reading.cursor})
        elif path.startswith('/assets/'):
            self.send_asset(unquote(path[len('/assets/') :]))
        elif path == '/doc':
            self.send_doc(parse_qs(parts.query).get('path', [''])[0])
        elif path.startswith('/file/'):
            self.send_file(unquote(path[len('/file/') :]))
        elif path == '/mtime':
            self.send_mtime()
        else:
            self.send_json({'error': 'not found'}, code=404)

    def do_POST(self):  # noqa: N802 (name fixed by BaseHTTPRequestHandler)
        """Answer a write. Every refusal is caught here rather than dropped."""
        try:
            body = self.read_json()
            if self.path == '/api/cursor' and self.reading.servername:
                self.reading.cursor = wanted_line(body)
                if body.get('clicked'):
                    self.reading.clicks += 1
                self.send_json({'ok': True})
            elif self.path == '/api/heartbeat':
                self.reading.beat = time.monotonic()
                self.send_json({'ok': True})
            elif self.path == '/api/jump' and self.reading.servername:
                first, last = block_range(self.reading.current, wanted_line(body))
                vimlink.jump(self.reading.servername, first, last)
                self.send_json({'ok': True})
            elif self.path == '/api/state':
                state = wanted_state(body)
                save_state(state)
                self.send_json(state)
            else:
                self.send_json({'error': 'not found'}, code=404)
        except ValueError as error:
            self.send_json({'error': str(error)}, code=400)

    def log_message(self, fmt, *args):
        """Stay quiet, the terminal is the user's."""

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

    def send_asset(self, name):
        """Send the page's own stylesheet or script."""
        path = (ASSET_DIR / name).resolve()
        if not path.is_relative_to(ASSET_DIR) or not path.is_file():
            self.send_json({'error': 'not found'}, code=404)
            return
        self.send_bytes(path.read_bytes(), mimetypes.guess_type(path)[0] or 'text/plain')

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
            # does not have open.
            if self.reading.servername:
                vimlink.edit(self.reading.servername, target)
        self.send_json(self.snapshot())

    def send_file(self, relative):
        """Send an image or other file the document points at."""
        path = resolve_inside(self.reading.root, relative)
        if path is None:
            self.send_json({'error': 'not found'}, code=404)
            return
        self.send_bytes(path.read_bytes(), mimetypes.guess_type(path)[0] or 'text/plain')

    def send_json(self, payload, code=200):
        """Send a JSON response."""
        self.send_bytes(json.dumps(payload).encode('utf-8'), 'application/json', code)

    def send_mtime(self):
        """Send the time the page polls to decide whether to redraw."""
        try:
            mtime = self.reading.current.stat().st_mtime_ns
        except OSError:
            mtime = None
        self.send_json({'mtime': mtime})

    def send_page(self):
        """Send the empty page."""
        page = page_html(
            self.name(), load_state()['theme'], bool(self.reading.servername)
        )
        self.send_bytes(page.encode('utf-8'), 'text/html')

    def snapshot(self):
        """Return what the page draws, or the reply that says the file is gone."""
        # The state travels with the document because the page reads its theme
        # from the first reply it gets, which may well be the gone one.
        state = load_state()
        try:
            source = self.reading.current.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return {'name': self.name(), 'gone': True, 'state': state}
        rendered = render_document(source)
        return {
            'name': self.name(),
            'blocks': rendered['blocks'],
            'outline': rendered['outline'],
            'state': state,
        }


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
