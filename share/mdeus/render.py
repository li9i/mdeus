"""
Turn markdown source into blocks that carry the source lines they came from.

This is the one renderer behind every tool here that draws markdown. A document
becomes an ordered list of top level blocks, each tagged with the range of
source lines it was built from, so a browser can map a click back to an exact
line of the file. Alongside the blocks it reports the heading outline.

The rendered HTML carries no heading ids. The outline is reported as data and
whoever draws the page decides what the headings are called, so that a name
chosen in the browser is the only name a heading ever has.

Where an image beside the document is served from is the caller's to say, since
a served reading and a printed copy answer for the same file in different ways.
"""

from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


def heading_outline(root):
    """Return every heading as its text, level and source line, in document order."""
    return [
        {
            'text': heading_text(node),
            'level': int(node.tag[1:]),
            'line': node.map[0] + 1,
        }
        for node in root.walk()
        if node.type == 'heading' and node.map
    ]


def heading_text(node):
    """Return a heading's text with its inline markers dropped."""
    # What the browser would read out of the rendered heading, so that a name
    # derived from this matches a name derived from the page.
    return ''.join(
        child.content
        for child in node.children[0].walk()
        if child.type in ('text', 'code_inline')
    ).strip()


def is_relative(target):
    """Say whether a link or image target names a file beside the document."""
    parts = urlsplit(target or '')
    return bool(
        not parts.scheme
        and not parts.netloc
        and parts.path
        and not parts.path.startswith('/')
    )


def render_blocks(source):
    """Split rendered markdown into top-level blocks tagged with source lines."""
    return render_document(source)['blocks']


def render_document(source, image_src=None):
    """Return a document's blocks and heading outline.

    image_src, where it is given, says what every image beside the document is
    written as: the address a server answers for the file at, or the bytes of
    the file itself. Without it the targets are left exactly as the document
    wrote them.
    """
    md = MarkdownIt('commonmark').enable(['table', 'strikethrough'])
    # One env for the whole document. Link reference definitions are collected
    # into it while parsing and read back out while rendering, so a fresh env
    # per block would leave every reference link unresolved.
    env = {}
    tokens = md.parse(source, env)
    if image_src is not None:
        retarget_images(tokens, image_src)
    root = SyntaxTreeNode(tokens)
    return {
        'blocks': [
            {
                'type': node.type,
                'line_start': node.map[0] + 1,
                'line_end': node.map[1],
                'html': md.renderer.render(node.to_tokens(), md.options, env),
            }
            for node in root.children
            if node.map
        ],
        'outline': heading_outline(root),
    }


def retarget_images(tokens, image_src):
    """Write every image beside the document as the caller serves it.

    An image reached for any other way is left alone. An absolute path or an
    http address names something the document does not carry with it, so it is
    nobody here's to answer for.

    The targets are rewritten on the parsed document rather than on the HTML it
    becomes, so what is matched is an image and never something in the prose
    that reads like one.
    """
    for token in tokens:
        for child in token.children or ():
            if child.type == 'image' and is_relative(child.attrGet('src')):
                child.attrSet('src', image_src(child.attrGet('src')))
