"""
Behaviour tests for render.py. Run with: python3 test_render.py

Needs markdown_it, which render.py needs anyway. Nothing else, and no test
framework.
"""

import re
import sys

import render


ALERT_FIXTURE = """\
> [!NOTE]
> Something worth knowing.

> [!warning]
> The marker is read whatever case it is written in.

> [!CAUTION]

> [!NOTHING]
> Not one of the five, so this stays a quote.

> [!NOTE] on the same line as the words.

> An ordinary quote.
"""

AUTOLINK_FIXTURE = """\
Bare https://example.com/a?b=1 and www.example.org and mail@example.com.

A written [link](http://example.com/page) and `https://example.com/code`.

Not addresses: run install.sh, read notes/other.md, on the example.com host.
"""

EMOJI_FIXTURE = """\
Shipped :tada: with a :+1: and an unknown :nonesuch: left alone.

In code: `:tada:`, and in a link [:tada:](notes/other.md).

Not an emoji: 10:30:45.
"""

FOOTNOTE_FIXTURE = """\
A paragraph with a note[^one] in it.

Another paragraph with a second[^two].

[^one]: The first note.

[^two]: The second note, which runs
    onto another line.
"""

LINE_FIXTURE = """\
# A heading

A paragraph.

* first item
* second item

| Left | Right |
| --- | --- |
| one | two |

```
fenced text
```

> A quote on two
> source lines.

---

The last paragraph.
"""

MULTI_LINE_FIXTURE = """\
A paragraph that runs
across three source
lines in total.

```
first line of code
second line of code
```
"""

OUTLINE_FIXTURE = """\
# Top level

## A `code` name

### *Deep* heading

Setext level one
================

Setext level two
----------------
"""

TABLE_FIXTURE = """\
| Left | Right |
| --- | --- |
| one | two |

Some ~~struck out~~ text.
"""

TARGET_FIXTURE = """\
A relative image: ![one](images/diagram.png)

An absolute image: ![two](/usr/share/pixmaps/logo.png)

An image over http: ![three](http://example.com/remote.png)

A relative link to [a document](notes/other.md).

A relative link to [a text file](notes/other.txt).

An absolute link to [a file](/usr/share/doc/README).

A link over http to [example](http://example.com/page.md).
"""

TASK_FIXTURE = """\
- [x] a finished thing
- [ ] an unfinished thing
- an ordinary item

1. [ ] numbered and unfinished

A paragraph holding a literal [x] and [ ] that are not a list.
"""

THREE_HEADING_FIXTURE = """\
# One

## Two

## Three
"""

TWO_HEADING_FIXTURE = """\
# One

## Two
"""


def test_only_images_beside_the_document_are_retargeted():
    """An image beside the document is written as the caller says. Nothing else moves."""
    document = render.render_document(
        TARGET_FIXTURE, image_src=lambda target: f'served/{target}'
    )
    html = ''.join(block['html'] for block in document['blocks'])
    sources = re.findall(r'src="([^"]*)"', html)
    # Only the first names a file the caller can answer for. An absolute path
    # and a remote address are nobody here's to serve, and a link is not an
    # image however relative it is.
    assert sources == [
        'served/images/diagram.png',
        '/usr/share/pixmaps/logo.png',
        'http://example.com/remote.png',
    ], sources
    assert 'href="notes/other.md"' in html, html


def test_alert_markers_become_callouts():
    """A quote opening on one of GitHub's five markers is drawn as a callout."""
    blocks = render.render_blocks(ALERT_FIXTURE)
    note, warning, caution, unknown, inline, plain = blocks
    assert 'class="markdown-alert markdown-alert-note"' in note['html'], note
    assert '<p class="markdown-alert-title">Note</p>' in note['html'], note
    # The marker line is the name of the callout and is not prose, so it does
    # not survive into the body.
    assert '[!NOTE]' not in note['html'], note
    assert '<p>Something worth knowing.</p>' in note['html'], note
    # Written in any case, and titled the way GitHub titles it either way.
    assert 'markdown-alert-warning' in warning['html'], warning
    assert '<p class="markdown-alert-title">Warning</p>' in warning['html'], warning
    # A marker on its own is still a callout, with nothing under the title.
    assert 'markdown-alert-caution' in caution['html'], caution
    assert '<p class="markdown-alert-title">Caution</p>' in caution['html'], caution
    # Everything else is left as the quote it was written as.
    for block in (unknown, inline, plain):
        assert '<blockquote>' in block['html'], block
        assert 'markdown-alert' not in block['html'], block
    assert '[!NOTHING]' in unknown['html'], unknown
    assert '[!NOTE] on the same line' in inline['html'], inline


def test_bare_addresses_become_links():
    """A bare web or mail address is a link, as it is on GitHub."""
    html = ''.join(
        block['html'] for block in render.render_blocks(AUTOLINK_FIXTURE)
    )
    assert '<a href="https://example.com/a?b=1">https://example.com/a?b=1</a>' in html, html
    assert '<a href="http://www.example.org">www.example.org</a>' in html, html
    assert '<a href="mailto:mail@example.com">mail@example.com</a>' in html, html
    # An address inside a code span is text and is not touched.
    assert '<code>https://example.com/code</code>' in html, html
    # GitHub links an address and never guesses at one, so a file name ending
    # in something a domain could end in stays a file name, and a bare host
    # with no scheme and no www stays words.
    assert 'href="http://install.sh"' not in html, html
    assert 'run install.sh' in html, html
    assert '<a href="http://example.com">' not in html, html
    assert 'the example.com host' in html, html


def test_block_lines_name_their_source():
    """Every block reports the source lines it was built from."""
    blocks = [(block['type'], block['line_start'], block['line_end'])
              for block in render.render_blocks(LINE_FIXTURE)]
    # The list runs to line 7, the blank line that closes it, because these
    # ranges are the parser's own source map and not a count of the text.
    assert blocks == [
        ('heading', 1, 1),
        ('paragraph', 3, 3),
        ('bullet_list', 5, 7),
        ('table', 8, 10),
        ('fence', 12, 14),
        ('blockquote', 16, 17),
        ('hr', 19, 19),
        ('paragraph', 21, 21),
    ], blocks


def test_frozen_fixture_renders_byte_for_byte():
    """The fixture renders exactly as the blocks frozen at the file's end.

    Those blocks are what the renderer that drew these documents beforehand
    produced. Any difference at all, in a tag, an attribute or a line range,
    means a document now reads differently than it used to.
    """
    blocks = render.render_blocks(FROZEN_SOURCE)
    assert len(blocks) == len(FROZEN_BLOCKS), (len(blocks), len(FROZEN_BLOCKS))
    for got, expected in zip(blocks, FROZEN_BLOCKS):
        assert got == expected, (got, expected)


def test_emoji_shortcodes_become_characters():
    """A shortcode GitHub knows is drawn as the character. Everything else stands."""
    blocks = render.render_blocks(EMOJI_FIXTURE)
    prose, code_and_link, clock = blocks
    assert 'Shipped \N{PARTY POPPER} with a \N{THUMBS UP SIGN}' in prose['html'], prose
    # Not a name anything answers to, so it is left as the words it was.
    assert ':nonesuch:' in prose['html'], prose
    # A code span is text, and a link's words are prose like any other.
    assert '<code>:tada:</code>' in code_and_link['html'], code_and_link
    assert '>\N{PARTY POPPER}</a>' in code_and_link['html'], code_and_link
    # Colons around something no shortcode names leave the text alone.
    assert '10:30:45' in clock['html'], clock


def test_footnotes_are_collected_and_name_their_source():
    """The notes are gathered into a last block carrying the lines they were defined on."""
    blocks = render.render_blocks(FOOTNOTE_FIXTURE)
    assert len(blocks) == 3, blocks
    first, second, notes = blocks
    assert 'footnote-ref' in first['html'], first
    assert 'footnote-ref' in second['html'], second
    assert 'class="footnotes"' in notes['html'], notes
    assert 'The first note.' in notes['html'], notes
    assert 'onto another line.' in notes['html'], notes
    # The notes belong to the lines the definitions were written on, so a click
    # on them reaches the definition rather than the end of the file.
    assert (notes['line_start'], notes['line_end']) == (5, 8), notes


def test_heading_html_carries_no_id():
    """A rendered heading carries no id, whatever level or spelling it has."""
    # Whoever draws the page names the headings from the outline. A second id
    # put here would rename every anchor the page has already handed out.
    headings = [block['html']
                for block in render.render_blocks(OUTLINE_FIXTURE)
                if block['type'] == 'heading']
    assert len(headings) == 5, headings
    for html in headings:
        assert 'id=' not in html, html


def test_heading_outline_lists_every_heading():
    """The outline gives the text, level and source line of every heading."""
    outline = render.render_document(OUTLINE_FIXTURE)['outline']
    assert outline == [
        {'text': 'Top level', 'level': 1, 'line': 1},
        {'text': 'A code name', 'level': 2, 'line': 3},
        {'text': 'Deep heading', 'level': 3, 'line': 5},
        {'text': 'Setext level one', 'level': 1, 'line': 7},
        {'text': 'Setext level two', 'level': 2, 'line': 10},
    ], outline


def test_multi_line_block_reports_its_whole_range():
    """A block built from several lines reports the first one and the last."""
    para, fence = render.render_blocks(MULTI_LINE_FIXTURE)
    assert (para['line_start'], para['line_end']) == (1, 3), para
    assert (fence['line_start'], fence['line_end']) == (5, 8), fence


def test_outline_size_drives_the_contents_threshold():
    """Three headings reach the contents threshold and two fall short of it."""
    # The page offers a contents list only from three headings up, and it
    # counts them in the outline, so the outline has to report all of them.
    three = render.render_document(THREE_HEADING_FIXTURE)['outline']
    two = render.render_document(TWO_HEADING_FIXTURE)['outline']
    assert len(three) == 3, three
    assert len(two) == 2, two


def test_table_and_strikethrough_render():
    """The table and strikethrough rules are on, not plain CommonMark alone."""
    blocks = render.render_blocks(TABLE_FIXTURE)
    assert '<table>' in blocks[0]['html'], blocks[0]
    assert '<th>Left</th>' in blocks[0]['html'], blocks[0]
    assert '<s>struck out</s>' in blocks[1]['html'], blocks[1]


def test_task_list_items_become_checkboxes():
    """An item written with a box is drawn as one, ticked or not as it was written."""
    bullets, numbered, prose = render.render_blocks(TASK_FIXTURE)
    assert 'class="contains-task-list"' in bullets['html'], bullets
    ticked, empty, ordinary = bullets['html'].split('<li')[1:]
    assert 'checked' in ticked, ticked
    assert 'checked' not in empty, empty
    assert 'task-list-item-checkbox' in empty, empty
    # A box is never something to be ticked on the page, only something read.
    assert 'disabled' in ticked and 'disabled' in empty, bullets
    assert 'task-list-item' not in ordinary, ordinary
    # The brackets are the box, so none of them are left as words.
    assert '[x]' not in bullets['html'] and '[ ]' not in bullets['html'], bullets
    assert 'task-list-item-checkbox' in numbered['html'], numbered
    # Brackets in a paragraph are brackets and nothing more.
    assert '[x]' in prose['html'] and '[ ]' in prose['html'], prose


# The fixture below, and the blocks it has to produce, are frozen here in full.
# Together they are the whole of the guard in the byte for byte test above, and
# they sit at the end of the file only because of their length.
FROZEN_SOURCE = """\
# Heading level one

A first paragraph, on one line.

[ref]: http://example.com/reference "Reference title"

A second paragraph that runs across
three source lines, so that a block
spanning several lines is covered.

## Heading level two

### Heading level three

#### Heading level four

##### Heading level five

###### Heading level six

Setext heading level one
========================

Setext heading level two
------------------------

A tight list:

* first item
* second item
* third item

A loose list:

* first item, with a blank line after it

* second item, whose text carries on
  onto a second source line

* third item

A nested list:

* outer item
  * inner item
    * innermost item
* second outer item

An ordered list:

1. first step
2. second step, which runs onto
   a second line
3. third step

A table with an alignment row:

| Left | Centre | Right |
| :--- | :----: | ----: |
| one | two | three |
| a longer cell | another cell | the last cell |
| four | five | six |

A fenced code block with a language:

```python
def add(a, b):
    return a + b
```

A fenced code block without one:

```
plain fenced text
across two lines
```

An indented code block:

    indented code, line one
    indented code, line two

> A blockquote, on two source
> lines.

> An outer blockquote.
>
> > A nested blockquote inside it.

***

Inline styles: `inline code`, ~~strikethrough~~, *emphasis*, **strong**.

A relative image: ![relative](images/diagram.png)

An absolute image path: ![absolute](/usr/share/pixmaps/debian-logo.png)

An image over http: ![remote](http://example.com/remote.png)

A relative link to [another document](notes/other.md).

An absolute link to [a file](/usr/share/doc/README).

A link over http to [example](http://example.com/page).

A reference link to [the reference target][ref], defined near the top.

<div class="raw">
  <p>A raw HTML block.</p>
</div>

The last paragraph.
"""

FROZEN_BLOCKS = [
    {
        'type': 'heading',
        'line_start': 1,
        'line_end': 1,
        'html': '<h1>Heading level one</h1>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 3,
        'line_end': 3,
        'html': '<p>A first paragraph, on one line.</p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 7,
        'line_end': 9,
        'html': (
            '<p>A second paragraph that runs across\n'
            'three source lines, so that a block\n'
            'spanning several lines is covered.</p>\n'
        ),
    },
    {
        'type': 'heading',
        'line_start': 11,
        'line_end': 11,
        'html': '<h2>Heading level two</h2>\n',
    },
    {
        'type': 'heading',
        'line_start': 13,
        'line_end': 13,
        'html': '<h3>Heading level three</h3>\n',
    },
    {
        'type': 'heading',
        'line_start': 15,
        'line_end': 15,
        'html': '<h4>Heading level four</h4>\n',
    },
    {
        'type': 'heading',
        'line_start': 17,
        'line_end': 17,
        'html': '<h5>Heading level five</h5>\n',
    },
    {
        'type': 'heading',
        'line_start': 19,
        'line_end': 19,
        'html': '<h6>Heading level six</h6>\n',
    },
    {
        'type': 'heading',
        'line_start': 21,
        'line_end': 22,
        'html': '<h1>Setext heading level one</h1>\n',
    },
    {
        'type': 'heading',
        'line_start': 24,
        'line_end': 25,
        'html': '<h2>Setext heading level two</h2>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 27,
        'line_end': 27,
        'html': '<p>A tight list:</p>\n',
    },
    {
        'type': 'bullet_list',
        'line_start': 29,
        'line_end': 32,
        'html': (
            '<ul>\n'
            '<li>first item</li>\n'
            '<li>second item</li>\n'
            '<li>third item</li>\n'
            '</ul>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 33,
        'line_end': 33,
        'html': '<p>A loose list:</p>\n',
    },
    {
        'type': 'bullet_list',
        'line_start': 35,
        'line_end': 41,
        'html': (
            '<ul>\n'
            '<li>\n'
            '<p>first item, with a blank line after it</p>\n'
            '</li>\n'
            '<li>\n'
            '<p>second item, whose text carries on\n'
            'onto a second source line</p>\n'
            '</li>\n'
            '<li>\n'
            '<p>third item</p>\n'
            '</li>\n'
            '</ul>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 42,
        'line_end': 42,
        'html': '<p>A nested list:</p>\n',
    },
    {
        'type': 'bullet_list',
        'line_start': 44,
        'line_end': 48,
        'html': (
            '<ul>\n'
            '<li>outer item\n'
            '<ul>\n'
            '<li>inner item\n'
            '<ul>\n'
            '<li>innermost item</li>\n'
            '</ul>\n'
            '</li>\n'
            '</ul>\n'
            '</li>\n'
            '<li>second outer item</li>\n'
            '</ul>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 49,
        'line_end': 49,
        'html': '<p>An ordered list:</p>\n',
    },
    {
        'type': 'ordered_list',
        'line_start': 51,
        'line_end': 55,
        'html': (
            '<ol>\n'
            '<li>first step</li>\n'
            '<li>second step, which runs onto\n'
            'a second line</li>\n'
            '<li>third step</li>\n'
            '</ol>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 56,
        'line_end': 56,
        'html': '<p>A table with an alignment row:</p>\n',
    },
    {
        'type': 'table',
        'line_start': 58,
        'line_end': 62,
        'html': (
            '<table>\n'
            '<thead>\n'
            '<tr>\n'
            '<th style="text-align:left">Left</th>\n'
            '<th style="text-align:center">Centre</th>\n'
            '<th style="text-align:right">Right</th>\n'
            '</tr>\n'
            '</thead>\n'
            '<tbody>\n'
            '<tr>\n'
            '<td style="text-align:left">one</td>\n'
            '<td style="text-align:center">two</td>\n'
            '<td style="text-align:right">three</td>\n'
            '</tr>\n'
            '<tr>\n'
            '<td style="text-align:left">a longer cell</td>\n'
            '<td style="text-align:center">another cell</td>\n'
            '<td style="text-align:right">the last cell</td>\n'
            '</tr>\n'
            '<tr>\n'
            '<td style="text-align:left">four</td>\n'
            '<td style="text-align:center">five</td>\n'
            '<td style="text-align:right">six</td>\n'
            '</tr>\n'
            '</tbody>\n'
            '</table>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 64,
        'line_end': 64,
        'html': '<p>A fenced code block with a language:</p>\n',
    },
    {
        'type': 'fence',
        'line_start': 66,
        'line_end': 69,
        'html': (
            '<pre><code class="language-python">def add(a, b):\n'
            '    return a + b\n'
            '</code></pre>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 71,
        'line_end': 71,
        'html': '<p>A fenced code block without one:</p>\n',
    },
    {
        'type': 'fence',
        'line_start': 73,
        'line_end': 76,
        'html': (
            '<pre><code>plain fenced text\n'
            'across two lines\n'
            '</code></pre>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 78,
        'line_end': 78,
        'html': '<p>An indented code block:</p>\n',
    },
    {
        'type': 'code_block',
        'line_start': 80,
        'line_end': 81,
        'html': (
            '<pre><code>indented code, line one\n'
            'indented code, line two\n'
            '</code></pre>\n'
        ),
    },
    {
        'type': 'blockquote',
        'line_start': 83,
        'line_end': 84,
        'html': (
            '<blockquote>\n'
            '<p>A blockquote, on two source\n'
            'lines.</p>\n'
            '</blockquote>\n'
        ),
    },
    {
        'type': 'blockquote',
        'line_start': 86,
        'line_end': 88,
        'html': (
            '<blockquote>\n'
            '<p>An outer blockquote.</p>\n'
            '<blockquote>\n'
            '<p>A nested blockquote inside it.</p>\n'
            '</blockquote>\n'
            '</blockquote>\n'
        ),
    },
    {
        'type': 'hr',
        'line_start': 90,
        'line_end': 90,
        'html': '<hr />\n',
    },
    {
        'type': 'paragraph',
        'line_start': 92,
        'line_end': 92,
        'html': '<p>Inline styles: <code>inline code</code>, <s>strikethrough</s>, <em>emphasis</em>, <strong>strong</strong>.</p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 94,
        'line_end': 94,
        'html': '<p>A relative image: <img src="images/diagram.png" alt="relative" /></p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 96,
        'line_end': 96,
        'html': '<p>An absolute image path: <img src="/usr/share/pixmaps/debian-logo.png" alt="absolute" /></p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 98,
        'line_end': 98,
        'html': '<p>An image over http: <img src="http://example.com/remote.png" alt="remote" /></p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 100,
        'line_end': 100,
        'html': '<p>A relative link to <a href="notes/other.md">another document</a>.</p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 102,
        'line_end': 102,
        'html': '<p>An absolute link to <a href="/usr/share/doc/README">a file</a>.</p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 104,
        'line_end': 104,
        'html': '<p>A link over http to <a href="http://example.com/page">example</a>.</p>\n',
    },
    {
        'type': 'paragraph',
        'line_start': 106,
        'line_end': 106,
        'html': '<p>A reference link to <a href="http://example.com/reference" title="Reference title">the reference target</a>, defined near the top.</p>\n',
    },
    {
        'type': 'html_block',
        'line_start': 108,
        'line_end': 110,
        'html': (
            '<div class="raw">\n'
            '  <p>A raw HTML block.</p>\n'
            '</div>\n'
        ),
    },
    {
        'type': 'paragraph',
        'line_start': 112,
        'line_end': 112,
        'html': '<p>The last paragraph.</p>\n',
    },
]

if __name__ == '__main__':
    tests = sorted(k for k in dict(globals()) if k.startswith('test_'))
    failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f'pass  {name}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL  {name}\n        {e}')
    print(f'\n{len(tests)} tests, {failed} failed')
    sys.exit(1 if failed else 0)
