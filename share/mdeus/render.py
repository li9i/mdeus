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

Two versions of a document can also be drawn as one comparison, the words that
went and the words that came each marked in the block they belong to.
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache
from html import escape, unescape
from urllib.parse import urlsplit

from emoji import EMOJI_DATA, STATUS
from lxml.html import fragment_fromstring, tostring
from lxml.html.diff import (
    fixup_ins_del_tags,
    htmldiff_tokens,
    start_tag,
    token,
    tokenize,
)
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

ALERTS = {
    'caution': 'Caution',
    'important': 'Important',
    'note': 'Note',
    'tip': 'Tip',
    'warning': 'Warning',
}
ALERT_MARKER = re.compile(r'\[!([a-zA-Z]+)\][ \t]*(?:\n|$)')
CHECKBOX = 'task-list-item-checkbox'
CHECKED = 'checked="checked"'
FULLY_QUALIFIED = STATUS['fully_qualified']
GLUE_AFTER = '\ue000'
GLUE_BEFORE = '\ue001'
GLUED_AFTER = re.compile('\ue000(?:(</ins>)(?= <del>)|(</(?:del|ins)>)? ?)')
GLUED_BEFORE = re.compile(
    '(</ins> <del>)\ue001|(</(?:del|ins)>)? ?(<(?:del|ins)>)?\ue001'
)
LIKENESS = 0.5
PARTS = ('code_block', 'fence', 'heading', 'hr', 'paragraph', 'tr')
PUNCTUATION = re.compile(r'(\W*)(.*?)(\W*)', re.S)
SHORTCODE = re.compile(r':[a-z0-9_+-]+:')
WORD = re.compile(r'\w+')


def aim(node, span):
    """Mark every part of a block that owns fewer source lines than the block does.

    A block is as fine as a click can be aimed without this. A list, a table and
    a quote are each one block however far they run, so a click anywhere inside
    one answers with the whole of it. The parts within carry lines of their own,
    and each part carrying fewer lines than the block does is marked with them,
    so a click lands on the item, the row or the paragraph it was made in.

    What is marked is the parts that hold words rather than the parts that hold
    other parts. A list item is marked through its own text, so an item with a
    list under it answers for the line it was written on and leaves the items
    beneath it to answer for theirs. An item in a tight list has no paragraph of
    its own in the markup GitHub renders, so its text is wrapped in a span,
    which is drawn exactly as the bare text was.

    A part whose lines are the block's own lines is passed over, since the block
    already answers for those and nothing finer is there to aim at. So is a raw
    HTML block, which is written out as it stands and carries nothing of ours.
    """
    for inside in node.walk(include_self=False):
        if inside.type not in PARTS or not inside.map or list(inside.map) == list(span):
            continue
        opening = inside.nester_tokens.opening if inside.is_nested else inside.token
        opening.attrJoin('class', 'aim')
        opening.attrSet('data-start', str(inside.map[0] + 1))
        opening.attrSet('data-end', str(inside.map[1]))
        if opening.hidden:
            closing = inside.nester_tokens.closing
            opening.hidden = closing.hidden = False
            opening.tag = closing.tag = 'span'


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
    """Return the tokens for the title GitHub puts at the head of a callout.

    The title carries no source lines of its own. It is drawn out of the marker
    line, and the body of the callout already answers for that line, so a title
    naming it as well would put two answers on one line of the document.
    """
    level = opening.level + 1
    return [
        Token(
            'paragraph_open',
            'p',
            1,
            attrs={'class': 'markdown-alert-title'},
            block=True,
            level=level,
        ),
        Token(
            'inline',
            '',
            0,
            block=True,
            children=[],
            content=ALERTS[kind],
            level=level + 1,
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
        opening.tag = 'div'
        opening.attrJoin('class', f'markdown-alert markdown-alert-{kind}')
        state.tokens[closing_index(state.tokens, index)].tag = 'div'
        body = state.tokens[index + 2]
        body.content = ALERT_MARKER.sub('', body.content, count=1)
        tokens.append(opening)
        tokens.extend(alert_title(opening, kind))
        index += 1 if body.content.strip() else 4
    state.tokens = tokens


def alike(older, newer):
    """Say whether two texts share enough words to stand for one another.

    Only the words are weighed, so a full stop or a bracket that came or went
    does not count against them.
    """
    words = SequenceMatcher(
        None, WORD.findall(older), WORD.findall(newer), autojunk=False
    )
    return words.ratio() >= LIKENESS


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


def changed_blocks(older, after, start, end):
    """Return the blocks one run of changed blocks is drawn as.

    older holds the run as the older version has it, and the newer version
    has it from start to end of after. A table both versions have in the run
    is compared on its own, row by row and cell by cell. Compared word by word
    with the rest, the words of one cell drift into the next once a column or
    a row comes or goes. The blocks between those tables are compared
    together, the last stretch running to the end of the run.
    """
    newer = after[start:end]
    matcher = SequenceMatcher(
        None,
        [block['type'] for block in older],
        [block['type'] for block in newer],
        autojunk=False,
    )
    tables = [
        (i + n, j + n)
        for i, j, size in matcher.get_matching_blocks()
        for n in range(size)
        if older[i + n]['type'] == 'table'
    ]
    blocks = []
    i = j = 0
    for table_i, table_j in tables + [(len(older), len(newer))]:
        if i < table_i or j < table_j:
            compared = compared_html(
                joined_html(older[i:table_i]), joined_html(newer[j:table_j])
            )
            blocks.append(
                diff_block(after, start + j, start + table_j, compared)
            )
        if table_i < len(older):
            compared = compared_table(
                older[table_i]['html'], newer[table_j]['html']
            )
            index = start + table_j
            blocks.append(diff_block(after, index, index + 1, compared))
        i, j = table_i + 1, table_j + 1
    return blocks


def changed_lines(after, start, end):
    """Return the lines of the newer version a run of changed blocks stands on.

    A run holding only deleted blocks has no lines of its own in the newer
    version, so it stands on the line after the block it followed, or on the
    first line where it led the document.
    """
    if start < end:
        return after[start]['line_start'], after[end - 1]['line_end']
    line = after[start - 1]['line_end'] + 1 if start else 1
    return line, line


def checkbox(line, checked):
    """Return the markup for one task list box that can be pressed.

    It carries the line of the document its item was written on, since a press
    is answered by rewriting that line and the page has no other way to say
    which item was pressed.
    """
    return (
        f'<input class="{CHECKBOX}" data-line="{line}" type="checkbox"'
        + (' checked' if checked else '')
        + '>'
    )


def closing_index(tokens, index):
    """Return where whatever opened at this position is closed again."""
    depth = 0
    for position in range(index, len(tokens)):
        depth += tokens[position].nesting
        if depth == 0:
            return position
    return len(tokens) - 1


def compared_cells(old_row, new_row, columns):
    """Return one row of a compared table, with a cell for every column.

    columns pairs the place of each column in the older version with its
    place in the newer, None for the version a column is missing from. A row
    only one version has is None in the other. A cell is compared with the
    cell it stands for, or with nothing where there is none.
    """
    cells = []
    for i, j in columns:
        old = None if old_row is None or i is None else old_row[i]
        new = None if new_row is None or j is None else new_row[j]
        cell = old if new is None else new
        if cell is None:
            cells.append('<td></td>')
            continue
        old_html = '' if old is None else inner_html(old)
        new_html = '' if new is None else inner_html(new)
        if old_html != new_html:
            new_html = compared_html(old_html, new_html)
        cells.append(f'{start_tag(cell)}{new_html}</{cell.tag}>')
    return f'<tr>{"".join(cells)}</tr>'


def compared_html(old, new):
    """Return two pieces of HTML as one, with the words that changed marked.

    This is the comparison lxml's htmldiff makes, run on the words diff_tokens
    gives rather than on lxml's own. lxml puts a space on either side of every
    change it marks, so each piece of a word is marked as glued to the piece
    after it and to the piece before it. Either piece can be the one left on
    the page, the new one or the deleted one, so both marks are written. Once
    the changes are marked, each mark goes with the space lxml put beside it.
    The space between an inserted word and the deleted word it stands for is
    kept, so the two still read as two words.
    """
    marked = ''.join(htmldiff_tokens(diff_tokens(old), diff_tokens(new)))
    marked = GLUED_AFTER.sub(r'\1\2', marked)
    marked = GLUED_BEFORE.sub(r'\1\2\3', marked)
    return fixup_ins_del_tags(marked.strip())


def compared_table(old, new):
    """Return two versions of one table as one, compared cell by cell.

    The columns are paired by their headings, and the rows by their words in
    the columns the two share. A column or a row only one version has is
    drawn in the place it had, inserted or deleted whole, so every cell keeps
    its place in the grid.
    """
    old_head, *old_body = fragment_fromstring(old).iter('tr')
    new_head, *new_body = fragment_fromstring(new).iter('tr')
    columns = paired(
        [cell.text_content() for cell in old_head],
        [cell.text_content() for cell in new_head],
    )
    shared = [(i, j) for i, j in columns if i is not None and j is not None]
    rows = paired(
        [
            '\n'.join(row[i].text_content() for i, _ in shared)
            for row in old_body
        ],
        [
            '\n'.join(row[j].text_content() for _, j in shared)
            for row in new_body
        ],
    )
    head = compared_cells(old_head, new_head, columns)
    body = ''.join(
        compared_cells(
            None if i is None else old_body[i],
            None if j is None else new_body[j],
            columns,
        )
        for i, j in rows
    )
    return f'<table><thead>{head}</thead><tbody>{body}</tbody></table>'


def diff_block(after, start, end, html):
    """Return one block of a comparison, drawn from some compared HTML.

    It stands on the lines the newer blocks from start to end of after stand
    on.
    """
    line_start, line_end = changed_lines(after, start, end)
    return {
        'type': 'diff',
        'line_start': line_start,
        'line_end': line_end,
        'html': f'<div class="diff">{html}</div>',
    }


def diff_tokens(html):
    """Return the words of some HTML to compare, with the marks at their ends.

    lxml splits words only at spaces, so to it `done` and `done.` are two
    different words, and a word that only gained a full stop reads as deleted
    and inserted again. A bracket, a comma or a full stop at either end of a
    word is taken off as a word of its own. One in the middle stays, so a date
    or a hyphenated name is still one word. An image is left whole.

    A link is compared by its words alone. lxml would write its address out
    as words beside them, which the page never shows, so a link whose address
    alone changed is left unmarked.

    HTML with nothing in it, such as an empty cell, gives no words. lxml gives
    one empty word for it, which a comparison marks as an empty change.
    """
    tokens = []
    for word in tokenize(html, include_hrefs=False):
        if not (word or word.pre_tags):
            continue
        found = PUNCTUATION.fullmatch(unescape(word))
        parts = [token(escape(part)) for part in found.groups() if part]
        if type(word) is not token or len(parts) < 2:
            tokens.append(word)
            continue
        for before, after in zip(parts, parts[1:]):
            before.trailing_whitespace = GLUE_AFTER
            after.pre_tags = [GLUE_BEFORE]
        parts[0].pre_tags = word.pre_tags
        parts[-1].post_tags = word.post_tags
        parts[-1].trailing_whitespace = word.trailing_whitespace
        tokens.extend(parts)
    return tokens


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
    return ''.join(
        child.content
        for child in node.children[0].walk()
        if child.type in ('text', 'code_inline')
    ).strip()


def inner_html(element):
    """Return what an element holds, as HTML, without the element itself."""
    return escape(element.text or '', quote=False) + ''.join(
        tostring(child, encoding='unicode') for child in element
    )


def is_relative(target):
    """Say whether a link or image target names a file beside the document."""
    parts = urlsplit(target or '')
    return bool(
        not parts.scheme
        and not parts.netloc
        and parts.path
        and not parts.path.startswith('/')
    )


def joined_html(blocks):
    """Return a run of blocks as the one piece of HTML they draw."""
    return ''.join(block['html'] for block in blocks)


def paired(older, newer):
    """Return which texts of two versions stand for one another, in order.

    Texts the two share are paired first. Between those, where as many texts
    went as came, they are paired in order, since that is a text edited where
    it stands. Otherwise each older text is paired with the first newer text
    after the last pair that it is alike to. A text left over stands alone.
    Each pair holds the places of its two texts in their lists, None for the
    version a text is missing from.
    """
    pairs = []
    matcher = SequenceMatcher(None, older, newer, autojunk=False)
    for kind, i1, i2, j1, j2 in matcher.get_opcodes():
        if i2 - i1 == j2 - j1:
            pairs.extend(zip(range(i1, i2), range(j1, j2)))
            continue
        j = j1
        for i in range(i1, i2):
            match = next(
                (k for k in range(j, j2) if alike(older[i], newer[k])), None
            )
            if match is None:
                pairs.append((i, None))
                continue
            pairs.extend((None, k) for k in range(j, match))
            pairs.append((i, match))
            j = match + 1
        pairs.extend((None, k) for k in range(j, j2))
    return pairs


def render_blocks(source):
    """Split rendered markdown into top-level blocks tagged with source lines."""
    return render_document(source)['blocks']


def render_diff(old, new, image_src=None):
    """Return the blocks of one comparison between two versions of a document.

    Both versions are drawn first and the drawings are compared, rather than
    the sources, so that a change reads as the page reads: a link or a table
    row is never cut through the middle of its markup. The blocks are matched
    whole, and a block the two share is drawn exactly as a reading draws it.
    A run of blocks that changed is compared word by word, the new words in an
    ins element and the old ones in a del element, inside the paragraph, item
    or cell they belong to. That comparison writes its markup out again, so it
    is spent only where something changed. A table both versions have in such
    a run is compared on its own, cell by cell, see changed_blocks.

    The blocks are matched however often one repeats, since a rule or a blank
    callout recurring through a long document is still a block of it.

    No outline is reported. A deleted heading is still drawn, so the headings
    on the page are those of neither version alone.
    """
    before = render_document(old, image_src=image_src)['blocks']
    after = render_document(new, image_src=image_src)['blocks']
    matcher = SequenceMatcher(
        None,
        [block['html'] for block in before],
        [block['html'] for block in after],
        autojunk=False,
    )
    blocks = []
    for kind, i1, i2, j1, j2 in matcher.get_opcodes():
        if kind == 'equal':
            blocks.extend(after[j1:j2])
            continue
        blocks.extend(changed_blocks(before[i1:i2], after, j1, j2))
    return {'blocks': blocks, 'outline': []}


def render_document(source, aimed=False, image_src=None, tickable=False):
    """Return a document's blocks and heading outline.

    aimed says whether the parts inside a block are marked with the lines they
    own. A reading has a vim beside it that answers a click with a jump, so the
    finer the mark the closer the jump lands. A printed copy has nothing to
    answer a click with, so it keeps the plain markup a rendered document gets.

    image_src, where it is given, says what every image beside the document is
    written as: the address a server answers for the file at, or the bytes of
    the file itself. Without it the targets are left exactly as the document
    wrote them.

    tickable says whether the task list boxes may be pressed. A reading has a
    document behind it to write a tick into, and a printed copy has nothing, so
    a copy keeps the dead boxes a rendered document ordinarily gets.
    """
    md = (
        MarkdownIt('commonmark', {'linkify': True})
        .enable(['table', 'strikethrough', 'linkify'])
        .use(footnote_plugin)
        .use(tasklists_plugin)
    )
    md.core.ruler.after('block', 'alerts', alerts)
    md.core.ruler.push('emoji', emojis)
    if tickable:
        md.core.ruler.push('ticks', ticks)
    md.linkify.set({'fuzzy_link': False})
    md.linkify.add('www.', {'normalize': www_url, 'validate': www_address})
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
        if aimed:
            aim(node, span)
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


def ticks(state):
    """Draw every task list box as one that can be pressed, naming its own line.

    The plugin draws a box that cannot be, since a rendered document is
    ordinarily nobody's to change. A reading has the document behind it and
    writes a press straight into the source, so its boxes are live.

    The line comes off the item the box belongs to rather than off the box,
    which is written as text in the middle of the item's first line and carries
    no place of its own.
    """
    line = None
    for token in state.tokens:
        if token.type == 'list_item_open' and token.map:
            line = token.map[0] + 1
        for child in token.children or ():
            if child.type == 'html_inline' and CHECKBOX in child.content and line:
                child.content = checkbox(line, CHECKED in child.content)


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
