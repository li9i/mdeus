"""
Turn markdown source into blocks that carry the source lines they came from.

A document becomes an ordered list of top level blocks, each tagged with the
range of source lines it was built from, so a browser can map a click back to
an exact line of the file. Alongside the blocks it reports the heading outline.

The rendered HTML carries no heading ids. The outline is reported as data and
whoever draws the page decides what the headings are called, so that a name
chosen in the browser is the only name a heading ever has.

Where an image beside the document is served from is the caller's to say, since
a served reading and a printed copy answer for the same file in different ways.

What is rendered is the markdown GitHub renders, so a document reads here the
way it reads there: tables, strikethrough, task lists, footnotes, bare
addresses, emoji shortcodes and the five callouts. Four of those come from the
parser and its plugins. The callouts are GitHub's own and no plugin draws them,
so they are put together below.
"""

import re
from functools import lru_cache
from urllib.parse import urlsplit

from emoji import EMOJI_DATA, STATUS
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

# The five callouts GitHub draws, and the word each one is titled with.
ALERTS = {
    'caution': 'Caution',
    'important': 'Important',
    'note': 'Note',
    'tip': 'Tip',
    'warning': 'Warning',
}
# A callout is named on a line of its own at the head of a quote. Words after
# the marker on that line make the whole of it prose and not a marker.
ALERT_MARKER = re.compile(r'\[!([a-zA-Z]+)\][ \t]*(?:\n|$)')
# A character with a name is written several ways in the emoji data and only
# this one is the picture. The others carry the same name over a piece of
# punctuation, which is not what a document asking for an emoji is after.
FULLY_QUALIFIED = STATUS['fully_qualified']
SHORTCODE = re.compile(r':[a-z0-9_+-]+:')


def alert_kind(tokens, index):
    """Return which callout a quote opens as, or None if it is a plain quote."""
    if tokens[index].type != 'blockquote_open':
        return None
    if index + 2 >= len(tokens) or tokens[index + 1].type != 'paragraph_open':
        return None
    found = ALERT_MARKER.match(tokens[index + 2].content)
    kind = found.group(1).lower() if found else None
    return kind if kind in ALERTS else None


def alert_title(opening, kind):
    """Return the tokens for the title GitHub puts at the head of a callout."""
    # The icon beside the word is the stylesheet's, so the title is the word
    # alone and the markup carries no drawing of its own.
    level = opening.level + 1
    return [
        Token(
            'paragraph_open',
            'p',
            1,
            attrs={'class': 'markdown-alert-title'},
            block=True,
            level=level,
            map=opening.map,
        ),
        Token(
            'inline',
            '',
            0,
            block=True,
            children=[],
            content=ALERTS[kind],
            level=level + 1,
            map=opening.map,
        ),
        Token('paragraph_close', 'p', -1, block=True, level=level),
    ]


def alerts(state):
    """Draw a quote opening on one of GitHub's alert markers as that callout.

    The marker names the callout rather than saying anything, so it comes off
    the first line and goes back as the title above the body. A marker alone in
    its paragraph takes the paragraph with it. Everything else stays the quote
    it was written as: a marker that is not one of the five, and a marker with
    words after it on the same line, are both prose.

    This runs before the inline pass, so a line is taken off a block's text and
    the text is read afterwards, rather than being read and then edited.
    """
    tokens = []
    index = 0
    while index < len(state.tokens):
        opening = state.tokens[index]
        kind = alert_kind(state.tokens, index)
        if kind is None:
            tokens.append(opening)
            index += 1
            continue
        # GitHub's markup for a callout is a div, so the close goes with the
        # open. Left as it was, the two would name different elements.
        opening.tag = 'div'
        opening.attrJoin('class', f'markdown-alert markdown-alert-{kind}')
        state.tokens[closing_index(state.tokens, index)].tag = 'div'
        body = state.tokens[index + 2]
        body.content = ALERT_MARKER.sub('', body.content, count=1)
        tokens.append(opening)
        tokens.extend(alert_title(opening, kind))
        index += 1 if body.content.strip() else 4
    state.tokens = tokens


def block_span(node):
    """Return the source lines a top level block was built from.

    A block the parser cut out of the document carries its own range. The
    collected footnotes do not: they are drawn at the foot of the page out of
    definitions written anywhere above it, so their range is taken from the
    lines those definitions were written on.
    """
    if node.map:
        return node.map
    spans = [child.map for child in node.walk() if child.map]
    if not spans:
        return None
    return min(span[0] for span in spans), max(span[1] for span in spans)


def closing_index(tokens, index):
    """Return where whatever opened at this position is closed again."""
    depth = 0
    for position in range(index, len(tokens)):
        depth += tokens[position].nesting
        if depth == 0:
            return position
    return len(tokens) - 1


@lru_cache(maxsize=None)
def emoji_names():
    """Return every shortcode GitHub answers to, mapped to the character it draws.

    GitHub's own names for these characters are the aliases in the data, so
    those go over the standard names rather than under them.
    """
    pictures = {
        character: entry
        for character, entry in EMOJI_DATA.items()
        if entry['status'] == FULLY_QUALIFIED
    }
    names = {entry['en']: character for character, entry in pictures.items()}
    names.update(
        (alias, character)
        for character, entry in pictures.items()
        for alias in entry.get('alias', ())
    )
    return names


def emojis(state):
    """Write every shortcode GitHub knows as the character it names.

    Only the words of the document are read. A code span carries its text as it
    was written and a link's target is not prose, so a name in either is left
    exactly where it is.
    """
    for token in state.tokens:
        for child in token.children or ():
            if child.type == 'text':
                child.content = SHORTCODE.sub(shortcode, child.content)


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
    md = (
        MarkdownIt('commonmark', {'linkify': True})
        .enable(['table', 'strikethrough', 'linkify'])
        .use(footnote_plugin)
        .use(tasklists_plugin)
    )
    # The callouts read a block's first line before that line is parsed, and
    # the shortcodes are written over the words once everything else has had
    # its say, so one rule goes in early and the other goes in last.
    md.core.ruler.after('block', 'alerts', alerts)
    md.core.ruler.push('emoji', emojis)
    # GitHub links an address and never guesses at one. Left as it comes, the
    # parser guesses at anything shaped like a host, and `install.sh` in a
    # sentence is shaped like one, so the guessing is turned off and the one
    # address GitHub links without a scheme is put back as a rule of its own.
    md.linkify.set({'fuzzy_link': False})
    md.linkify.add('www.', {'normalize': www_url, 'validate': www_address})
    # One env for the whole document. Link reference definitions and footnotes
    # are collected into it while parsing and read back out while rendering, so
    # a fresh env per block would leave every reference and note unresolved.
    env = {}
    tokens = md.parse(source, env)
    if image_src is not None:
        retarget_images(tokens, image_src)
    root = SyntaxTreeNode(tokens)
    blocks = []
    for node in root.children:
        span = block_span(node)
        if span is None:
            continue
        blocks.append(
            {
                'type': node.type,
                'line_start': span[0] + 1,
                'line_end': span[1],
                'html': md.renderer.render(node.to_tokens(), md.options, env),
            }
        )
    return {'blocks': blocks, 'outline': heading_outline(root)}


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


def shortcode(found):
    """Return one shortcode as the character it names, or as the text it was."""
    return emoji_names().get(found.group(0), found.group(0))


def www_address(linkify, text, position):
    """Return how much of what follows a `www.` belongs to the address.

    The host and the path are the parser's own patterns rather than a second
    reading of what an address looks like, so this rule sees exactly what the
    rules for the addresses that carry a scheme see.
    """
    tail = re.match(
        linkify.re['src_host_port_strict'] + linkify.re['src_path'],
        text[position:],
        re.IGNORECASE,
    )
    return len(tail.group()) if tail else 0


def www_url(linkify, match):
    """Give a `www.` address the scheme a browser needs to follow it."""
    match.url = f'http://{match.url}'
