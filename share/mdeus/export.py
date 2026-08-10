"""
Write one markdown document as a single self contained HTML file.

The file has to survive being moved, copied to another machine or sent to
somebody, so it carries everything it needs: the images the document points at
are embedded as data: URIs, and the stylesheet and the page script are inlined
whole from the ones a served reading uses.

That last part is the whole design. A printed copy is the reading page with the
document baked into it rather than fetched, so the themes, the contents list and
the names the headings are given are the reading's own and are not written a
second time here. The requests the page would make are answered from the baked
document by the short script below, which refuses the two that write. Changing
the theme or opening the contents list therefore affects that one file and
stores nothing.

Links to other markdown documents are left exactly as they were written. There
is nothing behind the file to render a target, so following one is the
browser's business and not this module's.
"""

import base64
import hashlib
import json
import mimetypes
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from render import render_document
from server import ASSET_DIR, page_html, resolve_inside
from state import load_state

CACHE_DIR = Path.home() / '.cache' / 'mdview'
# Everything the reading page asks a server for, answered from the document
# printed beside it. Nothing here reaches the network, and a request to store
# the theme or the contents setting is refused rather than answered, because a
# printed copy has nowhere to store it.
STUB = """\
window.fetch = (path) => {
  const answers = { '/doc': DOC, '/mtime': { mtime: 0 } };
  const body = answers[path];
  return Promise.resolve({
    ok: body !== undefined,
    json: () => Promise.resolve(body),
  });
};

/* A link to another document was left as it was written, and there is nothing
   here to render a target, so the browser follows it the way it would in any
   other page. The reading page takes such links over as the click travels back
   up, which stopping it on the way down prevents. */
document.querySelector('.doc').addEventListener(
  'click',
  (event) => {
    if (event.target.closest('a')) {
      event.stopPropagation();
    }
  },
  true
);
"""


def cache_path(source):
    """Return the file a document is printed to.

    The name carries a digest of the absolute source path, so two documents
    called README.md in two projects never land on each other, and printing the
    same document again overwrites the copy it made last time.
    """
    digest = hashlib.sha1(str(source).encode('utf-8')).hexdigest()[:8]
    return CACHE_DIR / f'{source.stem}-{digest}.html'


@lru_cache(maxsize=None)
def data_uri(path):
    """Return a file as the data: URI that stands in for it.

    Held for as long as one export runs, so a logo used in ten places is read
    and encoded once rather than ten times.
    """
    kind = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    payload = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{kind};base64,{payload}'


def embedded_image(root):
    """Return what writes every image inside the tree as the bytes of the file.

    An image the document reaches for by any other means is left alone. An
    absolute path, an http address or a name resolving outside the tree all
    stay as they are, the same way a link to another document does.
    """

    def embed(target):
        """Return one image as its own bytes, or as the target that was there."""
        # The value is percent encoded on the way into the document, so that
        # has to come off before it names a file.
        path = resolve_inside(root, unquote(target))
        return target if path is None else data_uri(path)

    return embed


def printed_page(document):
    """Return the whole file: the reading page, its stylesheet, and the document."""
    # Both go in whole rather than a piece at a time, so a printed copy can
    # never be missing a theme, or name a heading differently from the reading
    # it was printed out of.
    styles = (ASSET_DIR / 'themes.css').read_text(encoding='utf-8')
    page = (ASSET_DIR / 'page.js').read_text(encoding='utf-8')
    return page_html(
        document['name'],
        document['state'],
        f'    <style>\n{styles}\n    </style>',
        f'    <script>\n{stub_script(document)}\n    </script>\n'
        f'    <script>\n{page}\n    </script>\n',
    )


def stub_script(document):
    """Return the script that answers the reading page from the printed document."""
    # A document holding the end of a script tag would otherwise close the one
    # it is being carried inside. The slash is escaped instead, which a
    # JavaScript string reads as the slash it was.
    baked = json.dumps(document).replace('</', '<\\/')
    return f'const DOC = {baked};\n\n{STUB}'


def write_export(source):
    """Write a document as one self contained file and return where it went."""
    source = source.resolve()
    rendered = render_document(
        source.read_text(encoding='utf-8'), image_src=embedded_image(source.parent)
    )
    document = {
        'blocks': rendered['blocks'],
        # There is no server behind a printed copy to answer for a write, so
        # the page is told the document never changes.
        'mtime': 0,
        'name': source.name,
        'outline': rendered['outline'],
        'state': load_state(),
    }
    path = cache_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(printed_page(document), encoding='utf-8')
    data_uri.cache_clear()
    return path
