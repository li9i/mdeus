"""
Turn markdown source into blocks that carry the source lines they came from.

This is the one renderer behind every tool here that draws markdown. A document
becomes an ordered list of top level blocks, each tagged with the range of
source lines it was built from, so a browser can map a click back to an exact
line of the file. Alongside the blocks it reports the heading outline, the
relative image paths and the relative links to other markdown documents.

The rendered HTML carries no heading ids. The outline is reported as data and
whoever draws the page decides what the headings are called, so that a name
chosen in the browser is the only name a heading ever has.
"""

from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

MARKDOWN_SUFFIX = '.md'


def asset_paths(root):
    """Return the sorted relative paths of the images a document references."""
    return sorted(
        {
            node.attrGet('src')
            for node in root.walk()
            if node.type == 'image' and is_relative(node.attrGet('src'))
        }
    )


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


def markdown_links(root):
    """Return the sorted relative links a document makes to other markdown files."""
    return sorted(
        {
            node.attrGet('href')
            for node in root.walk()
            if node.type == 'link'
            and is_relative(node.attrGet('href'))
            and urlsplit(node.attrGet('href')).path.endswith(MARKDOWN_SUFFIX)
        }
    )


def render_blocks(source):
    """Split rendered markdown into top-level blocks tagged with source lines."""
    return render_document(source)['blocks']


def render_document(source):
    """Return a document's blocks, heading outline, image paths and markdown links."""
    md = MarkdownIt('commonmark').enable(['table', 'strikethrough'])
    # One env for the whole document. Link reference definitions are collected
    # into it while parsing and read back out while rendering, so a fresh env
    # per block would leave every reference link unresolved.
    env = {}
    root = SyntaxTreeNode(md.parse(source, env))
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
        'assets': asset_paths(root),
        'links': markdown_links(root),
    }
