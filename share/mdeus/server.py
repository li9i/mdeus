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
# One above the spec review tool's port, so a reading and a review opened at
# the same time do not push each other onto a fallback port.
DEFAULT_PORT = 8766
# Where an image beside the document is served from. The page itself is served
# at the root, so a document's own relative target would resolve against that
# and name nothing.
FILE_ROUTE = '/file/'
# Long enough that a page reloading or a machine pausing for a moment does not
# end the reading, short enough that a closed window does not leave a server
# behind.
HEARTBEAT_TIMEOUT = 10
HOST = '127.0.0.1'
MAX_BODY = 256 * 1024


def build_server(reading, port=DEFAULT_PORT):
    """Bind a server for one reading, taking any free port if the preferred one is busy."""
    handler = partial(ReadingHandler, reading=reading)
    try:
        return ThreadingHTTPServer((HOST, port), handler)
    except OSError:
        return ThreadingHTTPServer((HOST, 0), handler)


def page_html(title, state, head, body_tail=''):
    """Return the empty page. The controls and the document are filled in by page.js.

    The one skeleton behind both a served reading and a printed copy. What
    differs between them is how the stylesheet and the script arrive, which is
    the caller's to hand in: linked from this server, or inlined whole.
    """
    # Both settings the stylesheet reads are already on the root element here,
    # so that the first paint is the page the reader left rather than an
    # unstyled one for a moment, or one that rewraps as the script catches up.
    # The reader marker beside them says this is a page for reading rather than
    # the spec review tool, which shares the stylesheet and sizes github larger.
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
    """Serve until interrupted, or until the page stops answering."""
    threading.Thread(target=watch_heartbeat, args=(server, reading), daemon=True).start()
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def start(document, servername=None):
    """Bind a reading and return it, its server, and the address it landed on."""
    reading = Reading(document, servername=servername)
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
        # How many clicks vim has reported. A click there is the one thing that
        # brings the page along, and the throttled report of the same line
        # follows a moment later, so the page is told a running count rather
        # than a flag the report behind it would take back.
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
        # A reading with vim beside it answers at its own name as well as at
        # the root, because the browser names the window it puts up after the
        # address it was given, and that name is what tells one reading's page
        # window from another's. Several such readings run at once and they all
        # serve on the same host, so the host says nothing about which reading a
        # window belongs to.
        if path == '/' or path[1:] == self.reading.servername:
            self.send_page()
        # The routes that speak to vim are there only while vim is, so a
        # reading that is only a browser has no more of an API than before.
        elif path == '/api/cursor' and self.reading.servername:
            self.send_json({'clicks': self.reading.clicks, 'line': self.reading.cursor})
        elif path.startswith('/assets/'):
            self.send_from(ASSET_DIR, unquote(path[len('/assets/') :]))
        elif path == '/doc':
            self.send_doc(parse_qs(parts.query).get('path', [''])[0])
        elif path.startswith(FILE_ROUTE):
            self.send_from(self.reading.root, unquote(path[len(FILE_ROUTE) :]))
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
            # does not have open.
            if self.reading.servername:
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

    def send_json(self, payload, code=200):
        """Send a JSON response."""
        self.send_bytes(json.dumps(payload).encode('utf-8'), 'application/json', code)

    def send_mtime(self):
        """Send the time the page polls to decide whether to redraw."""
        self.send_json({'mtime': self.mtime()})

    def send_page(self):
        """Send the empty page, linking the stylesheet and the script it draws with."""
        head = [
            '    <link rel="stylesheet" href="/assets/themes.css" />',
            '    <script src="/assets/page.js" defer></script>',
        ]
        # The two files behind the sync with vim are linked only by a reading
        # that has vim beside it. Anyone may ask for them, so the markup is what
        # keeps them out of a reading that is only a browser. They load after
        # page.js, which draws the document they mark.
        if self.reading.servername:
            head.append('    <link rel="stylesheet" href="/assets/bmvim.css" />')
            head.append('    <script src="/assets/bmvim.js" defer></script>')
        page = page_html(self.title(), load_state(), '\n'.join(head))
        self.send_bytes(page.encode('utf-8'), 'text/html')

    def snapshot(self):
        """Return what the page draws, or the reply that says the file is gone."""
        # The state travels with the document because the page reads its theme
        # from the first reply it gets, which may well be the gone one. The
        # modification time travels with it for the same reason the blocks do:
        # it is the time of the document the page is about to draw, so the poll
        # that follows compares against what is on the screen without having to
        # ask a second question.
        # The title travels with it because the page writes its own title as it
        # draws, so that following a link to another document says so on the tab
        # and, in a reading with vim beside it, on the panel. It is written here
        # rather than put together again in the page, so the title a reading
        # opened at and the title it moves on to are the one string.
        common = {
            'mtime': self.mtime(),
            'name': self.name(),
            'state': load_state(),
            'title': self.title(),
        }
        try:
            source = self.reading.current.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return dict(common, gone=True)
        rendered = render_document(source, image_src=self.image_src)
        return dict(common, blocks=rendered['blocks'], outline=rendered['outline'])

    def title(self):
        """Return what the page is called: the command, then the document.

        A window on the panel and a tab among twenty others both say what they
        are as well as what they are showing. Which command is running is not
        stored anywhere: a reading with vim beside it is the one that has a
        servername, and there is no third command.
        """
        command = 'bmvim' if self.reading.servername else 'bmv'
        return f'{command}: {self.name()}'
