"""
Behaviour tests for server.py and export.py. Run with: python3 test_server.py

Each test builds a fixture tree in a temporary directory, binds a real server
on a free port and speaks to it over HTTP. No browser, no vim, no test
framework. Needs markdown_it, which render.py needs anyway.

Nothing here may reach the state file or the export cache in the home
directory, so both paths are pointed into the temporary tree before any request
is made, and the run checks at the end that neither was written to.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

# The state file and the export cache both hang off the home directory, and
# where that is gets read once, when the modules below are imported. So it
# is pointed at a temporary directory first, and the run is given a home of its
# own that nothing else on the machine knows about. A test that forgets to
# redirect either path then writes here rather than into the real home, and the
# check at the end stays honest: a reading open on the same desktop writes the
# real state file every time somebody picks a theme, which would otherwise be
# read as a leak out of these tests.
TEST_HOME = tempfile.mkdtemp(prefix='mdview-test-home-')
os.environ['HOME'] = TEST_HOME

import export
import render
import server
import state


OTHER_MD = """\
# Other document

Linked from the start.
"""

# Not valid UTF-8, so a server sending this as text rather than as bytes shows
# up as a decoding failure rather than as a quietly mangled image.
PIXEL_PNG = b'\x89PNG\r\n\x1a\n\x00\x01\x02\x03'

# Both captured before anything rebinds them, so the checks at the end of the
# run look at exactly what a leaking test would have written. They sit under
# the run's own home rather than the real one, see TEST_HOME above.
HOME_CACHE_DIR = export.CACHE_DIR
HOME_STATE_PATH = state.STATE_PATH

SECRET_MD = """\
# Outside the tree

This document sits above the directory the reading started in.
"""

SECRET_PNG = b'\x89PNG\r\n\x1a\nsecret'

START_BLOCKS = [
    ('heading', 1, 1),
    ('paragraph', 3, 3),
    ('paragraph', 5, 5),
    ('heading', 7, 7),
    ('bullet_list', 9, 10),
]

START_MD = """\
# Start

A paragraph.

![a pixel](images/pixel.png)

## Second heading

* first item
* second item
"""

START_OUTLINE = [
    {'text': 'Start', 'level': 1, 'line': 1},
    {'text': 'Second heading', 'level': 2, 'line': 7},
]

# The three theme names, written out here rather than read from the server, so
# that a theme quietly added or dropped there is caught instead of followed.
THEMES = ('browser', 'report', 'github')

TIMEOUT = 5


def fetch(port, path, method='GET', body=None):
    """Make one request and return the status, the content type and the body."""
    # http.client sends the path exactly as given, which is what lets a test
    # ask for ../ or an absolute path without the client tidying it away first.
    connection = HTTPConnection(server.HOST, port, timeout=TIMEOUT)
    try:
        headers = {'Connection': 'close'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        return response.status, response.headers.get('Content-Type', ''), response.read()
    except OSError as error:
        # A request the server drops rather than answers is a failure of the
        # test that made it, not of the run, so report it as one.
        raise AssertionError(f'{method} {path} went unanswered: {error}')
    finally:
        connection.close()


def fetch_json(port, path, method='GET', body=None):
    """Make one request carrying JSON and return the status and the decoded reply."""
    payload = None if body is None else json.dumps(body).encode('utf-8')
    status, _, data = fetch(port, path, method, payload)
    try:
        return status, json.loads(data)
    except ValueError:
        raise AssertionError(f'{method} {path} did not answer with JSON: {data[:80]!r}')


def home_cache_snapshot():
    """Return what the export cache under the run's own home holds, or None where there is none."""
    try:
        return sorted(path.name for path in HOME_CACHE_DIR.iterdir())
    except OSError:
        return None


def home_state_snapshot():
    """Return whether the state file under the run's own home exists and what is in it."""
    exists = HOME_STATE_PATH.parent.is_dir()
    try:
        return exists, HOME_STATE_PATH.read_bytes()
    except OSError:
        return exists, None


def served_blocks(source):
    """Return the blocks a reading sends: the renderer's, images pointed at /file/."""
    return render.render_document(
        source, image_src=lambda target: f'/file/{target}'
    )['blocks']


def start_export():
    """Build a fixture tree for the printed copy and return its root and a stop call.

    Nothing is served here, so no server is bound. The cache and the state file
    are pointed into the temporary tree first, so that no test can write into
    the real ones however it is written.
    """
    base = Path(tempfile.mkdtemp(prefix='mdview-test-')).resolve()
    export.CACHE_DIR = base / 'cache'
    state.STATE_PATH = base / 'state.json'
    root = base / 'tree'
    (root / 'images').mkdir(parents=True)
    (root / 'start.md').write_text(START_MD, encoding='utf-8')
    (root / 'images' / 'pixel.png').write_bytes(PIXEL_PNG)

    def stop():
        """Remove the fixture tree."""
        shutil.rmtree(base, ignore_errors=True)

    return root, stop


def start_reading(servername=None):
    """Serve a fixture tree on a free port and return its root, the port and a stop call.

    The state path is redirected here rather than in each test, so that no test
    can reach the real state file however it is written.

    A servername turns on the routes a reading with vim beside it has, and no
    vim ever answers to it here, so only the routes that do not speak to vim
    may be asked for under one.
    """
    base = Path(tempfile.mkdtemp(prefix='mdview-test-')).resolve()
    state.STATE_PATH = base / 'state.json'
    root = base / 'tree'
    (root / 'images').mkdir(parents=True)
    (root / 'notes').mkdir()
    (base / 'outside').mkdir()
    (root / 'start.md').write_text(START_MD, encoding='utf-8')
    (root / 'images' / 'pixel.png').write_bytes(PIXEL_PNG)
    (root / 'notes' / 'other.md').write_text(OTHER_MD, encoding='utf-8')
    (base / 'outside' / 'secret.md').write_text(SECRET_MD, encoding='utf-8')
    (base / 'outside' / 'secret.png').write_bytes(SECRET_PNG)
    # Two names inside the tree that lead out of it. A containment check
    # comparing the path before resolving it would hand both of these over.
    (root / 'escape.md').symlink_to('../outside/secret.md')
    (root / 'escape.png').symlink_to('../outside/secret.png')
    bound = server.build_server(
        server.Reading(root / 'start.md', servername=servername), port=0
    )
    thread = threading.Thread(target=bound.serve_forever, daemon=True)
    thread.start()

    def stop():
        """Stop the server, wait for it, and remove the fixture tree."""
        bound.shutdown()
        bound.server_close()
        thread.join(timeout=TIMEOUT)
        shutil.rmtree(base, ignore_errors=True)

    return root, bound.server_address[1], stop


def test_a_click_in_vim_is_counted_and_a_move_is_not():
    """The page is told how many clicks vim has reported, so it can follow every one.

    A click is a jump the page goes to whatever the distance, and the moves
    around it are not, so the two have to be told apart. They are counted
    rather than flagged because the throttled report that follows a click
    carries the same line a moment later, and a flag would be taken back by it
    before the page had come round to look.
    """
    root, port, stop = start_reading(servername='TESTVIM')
    try:
        status, state = fetch_json(port, '/api/cursor')
        assert (status, state) == (200, {'clicks': 0, 'line': None}), state
        fetch_json(port, '/api/cursor', 'POST', {'line': 12})
        assert fetch_json(port, '/api/cursor')[1] == {'clicks': 0, 'line': 12}
        fetch_json(port, '/api/cursor', 'POST', {'clicked': True, 'line': 30})
        assert fetch_json(port, '/api/cursor')[1] == {'clicks': 1, 'line': 30}
        fetch_json(port, '/api/cursor', 'POST', {'line': 30})
        assert fetch_json(port, '/api/cursor')[1] == {'clicks': 1, 'line': 30}
        fetch_json(port, '/api/cursor', 'POST', {'clicked': True, 'line': 30})
        assert fetch_json(port, '/api/cursor')[1] == {'clicks': 2, 'line': 30}
    finally:
        stop()


def test_absolute_and_parent_paths_are_not_served():
    """A file named by ../ or by an absolute path is not found, on either route."""
    root, port, stop = start_reading()
    try:
        secret_png = root.parent / 'outside' / 'secret.png'
        secret_md = root.parent / 'outside' / 'secret.md'
        outside = [
            '/file/../outside/secret.png',
            f'/file/{secret_png}',
            '/doc?' + urlencode({'path': '../outside/secret.md'}),
            '/doc?' + urlencode({'path': str(secret_md)}),
        ]
        for path in outside:
            status, reply = fetch_json(port, path)
            assert status == 404, (path, status)
            assert reply == {'error': 'not found'}, (path, reply)
        # A refused path must not have moved the reading off its document.
        status, doc = fetch_json(port, '/doc')
        assert doc['name'] == 'start.md', doc['name']
    finally:
        stop()


def test_asset_inside_the_tree_is_served():
    """GET /file/ sends a file from inside the tree, bytes and type intact."""
    root, port, stop = start_reading()
    try:
        status, content_type, data = fetch(port, '/file/images/pixel.png')
        assert status == 200, status
        assert data == PIXEL_PNG, data
        assert content_type.startswith('image/png'), content_type
    finally:
        stop()


def test_blocks_carry_the_lines_render_gave_them():
    """GET /doc sends the blocks and the outline the renderer produced."""
    root, port, stop = start_reading()
    try:
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        assert doc['name'] == 'start.md', doc['name']
        ranges = [(block['type'], block['line_start'], block['line_end'])
                  for block in doc['blocks']]
        assert ranges == START_BLOCKS, ranges
        assert doc['outline'] == START_OUTLINE, doc['outline']
        # The line ranges above say the numbers are right. This says the server
        # hands the renderer's work over whole, with nothing changed in it but
        # where an image is fetched from.
        assert doc['blocks'] == served_blocks(START_MD), doc['blocks']
    finally:
        stop()


def test_document_image_is_reachable_where_the_page_is_told_to_look():
    """The address an image carries in the page is one this server answers with the file.

    The page is served at the root, so a document's own relative target would
    be read against that and reach nothing. What the page is handed has to be an
    address the reading answers, and the only way to say so is to follow it.
    """
    root, port, stop = start_reading()
    try:
        status, doc = fetch_json(port, '/doc')
        found = re.findall(r'src="([^"]*)"', ''.join(
            block['html'] for block in doc['blocks']))
        assert len(found) == 1, found
        status, content_type, data = fetch(port, found[0])
        assert status == 200, (found[0], status)
        assert data == PIXEL_PNG, data
        assert content_type.startswith('image/png'), content_type
    finally:
        stop()


def test_every_theme_is_accepted_and_a_fourth_is_not():
    """All three theme keys are stored and served back, and a name outside them is not."""
    root, port, stop = start_reading()
    try:
        for theme in THEMES:
            status, reply = fetch_json(
                port, '/api/state', 'POST', {'theme': theme, 'contents': False})
            assert status == 200, (theme, status)
            assert reply == {'contents': False, 'theme': theme, 'wide': True}, reply
            status, doc = fetch_json(port, '/doc')
            assert doc['state']['theme'] == theme, (theme, doc['state'])
        before = state.STATE_PATH.read_text(encoding='utf-8')
        status, reply = fetch_json(
            port, '/api/state', 'POST', {'theme': 'chartreuse', 'contents': False})
        assert status == 400, status
        assert reply == {'error': 'unknown theme'}, reply
        after = state.STATE_PATH.read_text(encoding='utf-8')
        assert after == before, 'a refused theme was written to the state file'
    finally:
        stop()


def test_export_carries_the_reading_page_whole():
    """A printed copy inlines the page and the themes a reading uses, and its own outline.

    The naming of headings, the contents list and the theme names all live in
    page.js. A copy carrying that file whole cannot name a heading differently
    from the reading it was printed out of, and this is what says so.
    """
    root, stop = start_export()
    try:
        printed = export.write_export(root / 'start.md').read_text(encoding='utf-8')
        for name in ('page.js', 'themes.css'):
            text = (server.ASSET_DIR / name).read_text(encoding='utf-8')
            assert text in printed, f'{name} was not inlined whole'
        # The page builds its contents list from the outline, so the outline
        # has to travel with the document rather than be worked out again here.
        assert json.dumps(START_OUTLINE) in printed, 'the outline was not carried over'
        # A document holding the end of a script tag must not be able to close
        # the one carrying it, or everything after it stops being the page.
        risky = root / 'risky.md'
        risky.write_text('# Risky\n\n<div>a </script> in raw html</div>\n', encoding='utf-8')
        carried = export.write_export(risky).read_text(encoding='utf-8')
        assert 'a </script> in' not in carried, 'a document could close the script carrying it'
        assert 'a <\\/script> in' in carried, 'the document was not carried over whole'
    finally:
        stop()


def test_export_embeds_images_and_reaches_for_nothing():
    """A printed copy carries its image as bytes and asks for no other file."""
    root, stop = start_export()
    try:
        printed = export.write_export(root / 'start.md').read_text(encoding='utf-8')
        pixel = base64.b64encode(PIXEL_PNG).decode('ascii')
        assert f'data:image/png;base64,{pixel}' in printed, 'the image was not embedded'
        # The inlined stylesheet draws the page structure in a comment, markup
        # and all, so the markup and the scripts are what is read below. Both
        # quoted forms are looked for, since the document travels as JSON and
        # its own quotes are escaped there.
        rest = re.sub(r'<style>.*</style>', '', printed, flags=re.DOTALL)
        sources = re.findall(r'src=\\?"([^"\\]*)', rest)
        assert len(sources) == 1, sources
        for value in sources:
            assert value.startswith('data:'), value
        # The fixture document has no links of its own, so the only ones left
        # are the page's own to a heading inside the file.
        for value in re.findall(r'href=\\?"([^"\\]*)', rest):
            assert value.startswith('#'), value
        assert '<link' not in rest, 'the copy loads a file of its own'
        assert '<script src' not in rest, 'the copy loads a script of its own'
    finally:
        stop()


def test_export_path_is_stable_and_differs_per_source():
    """The copy lands at the same path every time, and two of one name do not collide."""
    root, stop = start_export()
    try:
        source = root / 'start.md'
        digest = hashlib.sha1(str(source).encode('utf-8')).hexdigest()[:8]
        written = export.write_export(source)
        assert written == export.CACHE_DIR / f'start-{digest}.html', written
        assert written.is_file(), written
        # Printing the same document again overwrites the copy rather than
        # leaving a second one behind.
        assert export.write_export(source) == written, 'the path moved between runs'
        assert sorted(p.name for p in export.CACHE_DIR.iterdir()) == [written.name]
        twin = root / 'notes' / 'start.md'
        twin.parent.mkdir()
        twin.write_text(START_MD, encoding='utf-8')
        other = export.write_export(twin)
        assert other != written, other
        assert other.name.startswith('start-'), other.name
        assert sorted(p.name for p in export.CACHE_DIR.iterdir()) == sorted(
            [written.name, other.name])
    finally:
        stop()


def test_linked_document_inside_the_tree_is_rendered():
    """GET /doc?path= renders another document in the tree and the reading moves to it."""
    root, port, stop = start_reading()
    try:
        status, doc = fetch_json(
            port, '/doc?' + urlencode({'path': 'notes/other.md'}))
        assert status == 200, status
        assert doc['name'] == 'notes/other.md', doc['name']
        assert doc['blocks'] == served_blocks(OTHER_MD), doc['blocks']
        # The reading is of that document from then on, so a plain /doc must
        # now send it rather than the one the reading started at.
        status, again = fetch_json(port, '/doc')
        assert again['name'] == 'notes/other.md', again['name']
    finally:
        stop()


def test_full_width_is_on_until_it_is_unticked_and_lands_on_the_first_paint():
    """The full width setting is stored, reported back, and already on the root element.

    The page could turn the class on itself once it has the document, but the
    lines would be drawn one way and rewrap the moment it did, so the setting
    has to arrive with the markup rather than after it.
    """
    root, port, stop = start_reading()
    try:
        # Nothing stored yet, so the reading opens the way the very first one
        # did, which is with the box ticked.
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is True, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader wide"' in page, page[:200]

        status, reply = fetch_json(
            port, '/api/state', 'POST', {'theme': 'browser', 'contents': False,
                                         'wide': False})
        assert status == 200, status
        assert reply['wide'] is False, reply
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is False, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader"' in page, page[:200]

        # A state file written before the setting existed names no field for it,
        # and reads as the setting being on rather than as a broken file.
        state.STATE_PATH.write_text(
            '{"theme": "browser", "contents": false}', encoding='utf-8')
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is True, doc['state']
    finally:
        stop()


def test_missing_or_broken_state_falls_back_to_browser():
    """A state file that is absent, malformed or naming no theme is not an error."""
    root, port, stop = start_reading()
    try:
        default = {'contents': False, 'theme': 'browser', 'wide': True}
        assert not state.STATE_PATH.exists(), state.STATE_PATH
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        assert doc['state'] == default, doc['state']
        broken = (
            '{not json at all',
            '{"theme": "chartreuse", "contents": false}',
            '[]',
        )
        for content in broken:
            state.STATE_PATH.write_text(content, encoding='utf-8')
            status, doc = fetch_json(port, '/doc')
            assert status == 200, (content, status)
            assert doc['state'] == default, (content, doc['state'])
    finally:
        stop()


def test_mtime_moves_only_when_the_file_is_written():
    """/mtime holds still until the source file is written, and moves after it."""
    root, port, stop = start_reading()
    try:
        status, first = fetch_json(port, '/mtime')
        assert status == 200, status
        assert isinstance(first['mtime'], int), first
        status, unchanged = fetch_json(port, '/mtime')
        assert unchanged == first, (unchanged, first)
        # File timestamps advance in steps of a few milliseconds, so a write
        # landing in the same step as the reading above would report the same
        # time and say nothing about whether the server is watching the file.
        time.sleep(0.05)
        (root / 'start.md').write_text(START_MD + '\nA new paragraph.\n', encoding='utf-8')
        status, later = fetch_json(port, '/mtime')
        assert later['mtime'] > first['mtime'], (later, first)
    finally:
        stop()


def test_removed_file_gives_the_gone_reply_and_recovers():
    """A source file taken away gives the gone reply, and the reading survives it."""
    root, port, stop = start_reading()
    try:
        gone = {'name': 'start.md', 'gone': True,
                'state': {'contents': False, 'theme': 'browser', 'wide': True}}
        source = root / 'start.md'
        source.unlink()
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        # Equality rather than a lookup, so a reply still carrying stale blocks
        # or an outline is caught. A file that is away has no time to report.
        assert doc == dict(gone, mtime=None), doc
        source.write_text(START_MD, encoding='utf-8')
        status, back = fetch_json(port, '/doc')
        assert 'gone' not in back, back
        assert back['blocks'] == served_blocks(START_MD), back['blocks']
        # A file that cannot be decoded reads the same way as one that is away,
        # except that it is still there and still has a time of its own, which
        # is what lets the page see it put right again.
        source.write_bytes(b'# Start\n\n\xff\xfe not text at all\n')
        status, invalid = fetch_json(port, '/doc')
        assert status == 200, status
        assert isinstance(invalid.pop('mtime'), int), invalid
        assert invalid == gone, invalid
    finally:
        stop()


def test_split_is_kept_beside_the_theme_and_falls_back():
    """The divider's share and the page's theme share a file and neither puts the other out."""
    root, port, stop = start_reading()
    try:
        assert state.load_split() == state.DEFAULT_SPLIT, state.load_split()
        state.save_split(0.62)
        assert state.load_split() == 0.62, state.load_split()
        # The page stores through the route and knows nothing of the split.
        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'github', 'contents': True, 'wide': False})
        stored = json.loads(state.STATE_PATH.read_text(encoding='utf-8'))
        assert stored == {'contents': True, 'theme': 'github', 'wide': False,
                          'split': 0.62}, stored
        # And a reading storing the split knows nothing of the page's settings.
        state.save_split(0.5)
        assert state.load_state() == {'contents': True, 'theme': 'github',
                                      'wide': False}, stored
        # A share the divider could not have left behind, whichever way it is
        # wrong, opens the reading at the split the first one opened at.
        for share in ('sideways', None, 0.02, 0.99):
            state.save_state({'split': share})
            assert state.load_split() == state.DEFAULT_SPLIT, share
    finally:
        stop()


def test_state_file_is_never_read_half_written():
    """Somebody reading the state file only ever sees a whole and valid one."""
    root, port, stop = start_reading()
    try:
        writes = 120
        last = {'contents': bool((writes - 1) % 2),
                'theme': THEMES[(writes - 1) % len(THEMES)],
                'wide': not (writes - 1) % 2}

        def write_many():
            """Store a different state over and over, as the three controls would."""
            for index in range(writes):
                fetch_json(port, '/api/state', 'POST',
                           {'theme': THEMES[index % len(THEMES)],
                            'contents': bool(index % 2),
                            'wide': not index % 2})

        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'browser', 'contents': False, 'wide': True})
        writer = threading.Thread(target=write_many)
        writer.start()
        seen = 0
        deadline = time.monotonic() + TIMEOUT
        while writer.is_alive() and time.monotonic() < deadline:
            try:
                stored = json.loads(state.STATE_PATH.read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                raise AssertionError(f'the state file was not whole: {error}')
            assert stored['theme'] in THEMES, stored
            assert isinstance(stored['contents'], bool), stored
            assert isinstance(stored['wide'], bool), stored
            seen += 1
        writer.join(timeout=TIMEOUT)
        assert not writer.is_alive(), 'the writer never finished'
        assert seen > 10, f'only {seen} reads landed while the file was being written'
        # Proof that every write went through, so the reads above were racing a
        # writer rather than watching a file nobody was touching.
        final = json.loads(state.STATE_PATH.read_text(encoding='utf-8'))
        assert final == last, final
    finally:
        stop()


def test_state_is_stored_and_reported_back():
    """POST /api/state writes the file, and the next /doc reports what it wrote."""
    root, port, stop = start_reading()
    try:
        wanted = {'contents': True, 'theme': 'report', 'wide': False}
        status, reply = fetch_json(port, '/api/state', 'POST', wanted)
        assert status == 200, status
        assert reply == wanted, reply
        stored = json.loads(state.STATE_PATH.read_text(encoding='utf-8'))
        assert stored == wanted, stored
        status, doc = fetch_json(port, '/doc')
        assert doc['state'] == wanted, doc['state']
    finally:
        stop()


def test_symlink_out_of_the_tree_is_not_followed():
    """A name inside the tree pointing out of it is not found, on either route."""
    root, port, stop = start_reading()
    try:
        # If the targets were missing the server would refuse for the wrong
        # reason, so check both links really lead to readable files first.
        assert (root / 'escape.png').is_file(), 'the fixture symlink leads nowhere'
        assert (root / 'escape.md').is_file(), 'the fixture symlink leads nowhere'
        status, reply = fetch_json(port, '/file/escape.png')
        assert status == 404, status
        assert reply == {'error': 'not found'}, reply
        status, reply = fetch_json(port, '/doc?' + urlencode({'path': 'escape.md'}))
        assert status == 404, status
        assert reply == {'error': 'not found'}, reply
        status, doc = fetch_json(port, '/doc')
        assert doc['name'] == 'start.md', doc['name']
    finally:
        stop()


if __name__ == '__main__':
    cache_before = home_cache_snapshot()
    home_before = home_state_snapshot()
    tests = sorted(k for k in dict(globals()) if k.startswith('test_'))
    failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f'pass  {name}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL  {name}\n        {e}')
    if home_cache_snapshot() != cache_before:
        failed += 1
        print(f'FAIL  the cache at {HOME_CACHE_DIR} was written to')
    if home_state_snapshot() != home_before:
        failed += 1
        print(f'FAIL  the state file at {HOME_STATE_PATH} was written to')
    # A handler finishes a moment after its response, so give the last ones
    # time to go before counting what is left.
    for _ in range(50):
        if threading.active_count() == 1:
            break
        time.sleep(0.02)
    if threading.active_count() != 1:
        failed += 1
        print(f'FAIL  {threading.active_count() - 1} threads were left running')
    shutil.rmtree(TEST_HOME, ignore_errors=True)
    print(f'\n{len(tests)} tests, {failed} failed')
    sys.exit(1 if failed else 0)
