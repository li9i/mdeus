"""
Behaviour tests for server.py and export.py. Run with: python3 test_server.py

Each test builds a fixture tree in a temporary directory, binds a real server
on a free port and speaks to it over HTTP. No browser, no vim, no test
framework. Needs markdown_it, which render.py needs anyway.

No test here opens vim. A reading is put into the editing state by hand, which
is all the routes that speak to vim ask for, and the one test that would reach
vim puts a stand in over the call.

Nothing here may reach the state file or the export cache in the home
directory, so both paths are pointed into the temporary tree before any request
is made, and the run checks at the end that neither was written to.
"""

import base64
import hashlib
import io
import json
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import redirect_stderr
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

TEST_HOME = tempfile.mkdtemp(prefix='mdeus-test-home-')
os.environ['HOME'] = TEST_HOME

import export
import render
import server
import state
import vimlink


OTHER_MD = """\
# Other document

Linked from the start.
"""

PIXEL_PNG = b'\x89PNG\r\n\x1a\n\x00\x01\x02\x03'

COMMAND = Path(__file__).resolve().parents[2] / 'bin' / 'mdeus'

HOME_CACHE_DIR = export.CACHE_DIR
HOME_STATE_PATH = state.STATE_PATH

LINGER = b'\x01\x00\x00\x00\x00\x00\x00\x00'

SECRET_MD = """\
# Outside the tree

This document sits above the directory the reading started in.
"""

SECRET_PNG = b'\x89PNG\r\n\x1a\nsecret'

SERVERNAME = 'MDEUSTEST'

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

TASKS_MD = """\
# Tasks

- [ ] first
- [x] second
  - [ ] nested

1. [ ] ordered

Not a task at all.

- [ ] outer
\t- [ ] indented with a tab
"""

THEMES = ('browser', 'report', 'github', 'wikipedia', 'wikipedia-classic')

TIMEOUT = 5


def broken_state(document):
    """Stand in for a settings file that falls over in a way nothing expects."""
    raise RuntimeError('the state file fell over')


def cursor_of(port):
    """Return the clicks and the line the reading is telling the page about."""
    state = fetch_json(port, '/api/cursor')[1]
    return state['clicks'], state['line']


def fetch(port, path, method='GET', body=None):
    """Make one request and return the status, the content type and the body."""
    connection = HTTPConnection(server.HOST, port, timeout=TIMEOUT)
    try:
        headers = {'Connection': 'close'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        return response.status, response.headers.get('Content-Type', ''), response.read()
    except OSError as error:
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


def fetch_raw(port, payload):
    """Send bytes straight at the server and return the first line of the answer.

    What http.client will not do for us is make a request that is malformed,
    and a malformed request is exactly what a reading has to answer rather than
    be held up by.
    """
    try:
        with socket.create_connection((server.HOST, port), timeout=TIMEOUT) as sock:
            sock.sendall(payload)
            answer = b''
            while b'\r\n' not in answer:
                got = sock.recv(4096)
                if not got:
                    break
                answer += got
    except OSError:
        return 'no answer'
    return answer.split(b'\r\n', 1)[0].decode('latin-1')


def heard_down(held):
    """Return the next thing a reading says down a connection a page is holding.

    The reply is never finished, so what comes down it is read one line at a
    time, and whatever of the next line arrived with this one is kept for the
    call after it.
    """
    while b'\n' not in held.rest:
        try:
            more = held.connection.recv(1024)
        except TimeoutError:
            raise AssertionError('the reading said nothing down the held connection')
        if not more:
            raise AssertionError('the connection ended rather than saying anything')
        held.rest += more
    line, held.rest = held.rest.split(b'\n', 1)
    return json.loads(line)


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


def request_head(port, method, path, *headers):
    """Return one request as bytes, said exactly rather than by http.client."""
    lines = [f'{method} {path} HTTP/1.1', f'Host: {server.HOST}:{port}',
             'Content-Type: application/json', *headers]
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('ascii')


def said_down(reading):
    """Say whether anything is waiting in the pipe a reading passes a wish down.

    Looked at rather than read, so that the pipe is left as a session would find
    it. A session empties it itself.
    """
    return bool(select.select([reading.heard], [], [], 0)[0])


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
    base = Path(tempfile.mkdtemp(prefix='mdeus-test-')).resolve()
    export.CACHE_DIR = base / 'cache'
    state.STATE_PATH = base / 'state.json'
    root = base / 'tree'
    (root / 'images').mkdir(parents=True)
    (root / 'start.md').write_text(START_MD, encoding='utf-8')
    (root / 'tasks.md').write_text(TASKS_MD, encoding='utf-8')
    (root / 'images' / 'pixel.png').write_bytes(PIXEL_PNG)

    def stop():
        """Remove the fixture tree."""
        shutil.rmtree(base, ignore_errors=True)

    return root, stop


def start_holding(port):
    """Take hold of a reading the way its page does, and return what holds it.

    The page holds a reading open by one request it never lets finish, so this
    reads the reply's headers and then leaves the connection exactly where it is.
    Closing it is what a page going away looks like from the server's side, and
    `close` on what comes back is that. What the reading says down it is read with
    heard_down above, so whatever of the first line arrived with the headers is
    carried along rather than dropped.

    Spoken over a bare socket rather than through http.client, which hangs up on
    a reply that carries no length the moment it has read the headers, and so
    could never hold anything.
    """
    connection = socket.create_connection((server.HOST, port), timeout=TIMEOUT)
    connection.sendall(f'GET /hold HTTP/1.1\r\nHost: {server.HOST}\r\n\r\n'.encode('ascii'))
    head = b''
    while b'\r\n\r\n' not in head:
        more = connection.recv(1024)
        if not more:
            raise AssertionError('GET /hold was dropped rather than answered')
        head += more
    assert head.startswith(b'HTTP/1.1 200 '), head.split(b'\r\n')[0]
    return SimpleNamespace(
        close=connection.close,
        connection=connection,
        rest=head.split(b'\r\n\r\n', 1)[1],
    )


def start_reading(editable=False, editing=False):
    """Serve a fixture tree on a free port and return its root, port, reading and a stop call.

    The state path is redirected here rather than in each test, so that no test
    can reach the real state file however it is written.

    A reading put into the editing state answers the routes that speak to vim.
    No vim answers to the name here, so only the routes that record something
    rather than send it on may be asked for under one.
    """
    base = Path(tempfile.mkdtemp(prefix='mdeus-test-')).resolve()
    state.STATE_PATH = base / 'state.json'
    root = base / 'tree'
    (root / 'images').mkdir(parents=True)
    (root / 'notes').mkdir()
    (base / 'outside').mkdir()
    (root / 'start.md').write_text(START_MD, encoding='utf-8')
    (root / 'tasks.md').write_text(TASKS_MD, encoding='utf-8')
    (root / 'images' / 'pixel.png').write_bytes(PIXEL_PNG)
    (root / 'notes' / 'other.md').write_text(OTHER_MD, encoding='utf-8')
    (base / 'outside' / 'secret.md').write_text(SECRET_MD, encoding='utf-8')
    (base / 'outside' / 'secret.png').write_bytes(SECRET_PNG)
    (root / 'escape.md').symlink_to('../outside/secret.md')
    (root / 'escape.png').symlink_to('../outside/secret.png')
    reading = server.Reading(root / 'start.md', SERVERNAME, editable=editable)
    reading.editing = editing
    bound = server.build_server(reading, port=0)
    thread = threading.Thread(target=bound.serve_forever, daemon=True)
    thread.start()

    def stop():
        """Stop the server, wait for it, and remove the fixture tree."""
        reading.over.set()
        bound.shutdown()
        bound.server_close()
        thread.join(timeout=TIMEOUT)
        shutil.rmtree(base, ignore_errors=True)

    return root, bound.server_address[1], reading, stop


def start_watching(reading):
    """Run the watcher that ends a reading and return the flag it ends by setting.

    The watcher is handed a stand in for the server rather than the server
    itself, so that a test can see the reading being ended without the server
    under it going away and taking the rest of the test's requests with it.

    The thread is the caller's to join. It ends of its own accord once it has
    ended the reading, and a test that leaves it running is caught by the check
    for stray threads at the end of the run.
    """
    stopped = threading.Event()
    watching = threading.Thread(
        target=server.watch_pages,
        args=(SimpleNamespace(shutdown=stopped.set), reading),
        daemon=True,
    )
    watching.start()
    return stopped, watching


def stored_settings(document):
    """Return what the state file holds under one document's own name."""
    whole = json.loads(state.STATE_PATH.read_text(encoding='utf-8'))
    return whole['documents'][str(document)]


def test_a_body_the_page_could_not_have_sent_is_refused():
    """A request the page would never make is answered, not fallen over.

    Everything a reading serves is reachable by anything else on the machine,
    and what arrives is not always JSON holding an object. A body that is a
    list, a bare word or a number, one nested deeper than JSON will read, and a
    length that is not a length at all: each is refused in the way every other
    refusal is refused, and the reading serves the next request as though the
    last had never come.

    A length below nothing is the one that matters most. It is not only
    malformed: read as it stands it says to read until the page stops sending,
    which is to say for as long as it likes and as much as it likes, and the
    turn spent on that request never comes back.
    """
    root, port, reading, stop = start_reading(editable=True)
    try:
        for path in ('/api/edit', '/api/state', '/api/tick'):
            for body in (b'[1, 2, 3]', b'"words"', b'3', b'true', b'null',
                         b'[' * 2000 + b']' * 2000):
                status, _, _ = fetch(port, path, 'POST', body)
                assert status == 400, (path, body[:20], status)
        answered = fetch_raw(port, request_head(
            port, 'POST', '/api/tick', 'Content-Length: -1'))
        assert answered.startswith('HTTP/1.1 400'), answered
        status, reply = fetch_json(port, '/api/edit', 'POST', {'editing': True})
        assert (status, reply) == (200, {'editing': False}), (status, reply)
    finally:
        stop()


def test_a_box_pressed_in_the_page_is_written_into_the_document():
    """A box pressed in the page rewrites its own line of the source and nothing else.

    The page is drawn from the document, so a tick kept anywhere but the
    document would be one the next reading never hears about. Only the mark
    between the brackets is written: the item keeps its indentation, its list
    marker and its words, whichever kind of list it is written in, so the
    document reads afterwards as the same document with one character changed.
    """
    root, port, reading, stop = start_reading()
    tasks = root / 'tasks.md'
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'tasks.md'}))
        for line, done, was, now in (
            (3, True, '- [ ] first', '- [x] first'),
            (4, False, '- [x] second', '- [ ] second'),
            (5, True, '  - [ ] nested', '  - [x] nested'),
            (7, True, '1. [ ] ordered', '1. [x] ordered'),
            (12, True, '\t- [ ] indented', '\t- [x] indented'),
        ):
            wanted = tasks.read_text(encoding='utf-8').replace(was, now)
            reply = fetch_json(port, '/api/tick', 'POST', {'done': done, 'line': line})
            assert reply == (200, {'ticked': True}), (line, reply)
            written = tasks.read_text(encoding='utf-8')
            assert written == wanted, (line, written)
    finally:
        stop()


def test_a_box_pressed_where_there_is_none_is_refused():
    """A tick naming a line that is not a task list item is refused, and writes nothing.

    That is what answers a page drawn before somebody else wrote the document:
    the lines have moved under it, and the tick has to land nowhere rather than
    on whatever is at that line now. A page that hears the refusal puts its own
    box back.
    """
    root, port, reading, stop = start_reading()
    tasks = root / 'tasks.md'
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'tasks.md'}))
        for line in (1, 2, 9, 0, -3, 999):
            reply = fetch_json(port, '/api/tick', 'POST', {'done': True, 'line': line})
            assert reply == (200, {'ticked': False}), (line, reply)
            assert tasks.read_text(encoding='utf-8') == TASKS_MD, line
        for body in ({}, {'done': True}, {'line': None}, {'line': 'three'}):
            status, reply = fetch_json(port, '/api/tick', 'POST', body)
            assert status == 400, (body, status, reply)
            assert tasks.read_text(encoding='utf-8') == TASKS_MD, body
    finally:
        stop()


def test_a_box_pressed_while_vim_is_up_is_left_to_vim():
    """While vim is up the tick goes to vim's copy of the document, not to the file.

    vim holds the document while it is up, and a file written under it puts a
    question up in the pane that has to be answered before vim hears anything
    else. So the line is set in the buffer and left unwritten, to be saved with
    whatever else the reader has open, and the file on the disk is not touched
    by the reading at all.
    """
    root, port, reading, stop = start_reading()
    tasks = root / 'tasks.md'
    told = []
    was = vimlink.tick
    vimlink.tick = lambda servername, line, done, path: (
        told.append((servername, line, done, Path(path).name)) or True
    )
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'tasks.md'}))
        reading.editing = True
        reply = fetch_json(port, '/api/tick', 'POST', {'done': True, 'line': 3})
        assert reply == (200, {'ticked': True}), reply
        assert told == [(SERVERNAME, 3, True, 'tasks.md')], told
        assert tasks.read_text(encoding='utf-8') == TASKS_MD, 'the file was written'
    finally:
        vimlink.tick = was
        stop()


def test_a_box_pressed_with_a_vim_behind_the_page_is_claimed_with_vim_first():
    """A tick the reading writes itself is claimed with vim, and given back where it is refused.

    A vim is warmed out of sight behind every reading and holds the same
    document, so a file the reading writes is a file written under vim, and vim
    asks whether to load what is written under it. Claiming the write is what
    keeps a box pressed while the page was alone from leaving a question
    standing in a pane nobody can see. A press that wrote nothing gives the
    claim back, so that the next write, which may be anybody's, is asked about
    as it should be.
    """
    root, port, reading, stop = start_reading()
    tasks = root / 'tasks.md'
    told = []
    was = vimlink.mine
    vimlink.mine = lambda servername, writing: told.append((servername, writing))
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'tasks.md'}))
        reply = fetch_json(port, '/api/tick', 'POST', {'done': True, 'line': 3})
        assert reply == (200, {'ticked': True}), reply
        assert told == [(SERVERNAME, True)], told
        assert tasks.read_text(encoding='utf-8') != TASKS_MD, 'nothing was written'
        told.clear()
        reply = fetch_json(port, '/api/tick', 'POST', {'done': True, 'line': 1})
        assert reply == (200, {'ticked': False}), reply
        assert told == [(SERVERNAME, True), (SERVERNAME, False)], told
    finally:
        vimlink.mine = was
        stop()


def test_a_box_pressed_while_another_is_being_written_waits_its_turn():
    """A press is one turn: the claim made with vim, the write, and the giving back.

    A tick the reading writes itself is claimed with vim first, so that the vim
    warmed behind the page takes that one write without putting a question up,
    and the claim is given back where the tick landed nowhere. Claim and write
    are therefore one act, and a press served while another is halfway through
    one would spend the other's claim on its own write, or hand back a claim the
    other still needed. What that leaves is the thing the claim exists to
    prevent: a question standing in a pane nobody is looking at.

    So the whole of a press is watched here rather than the write alone. Each
    press is served on a turn of its own and puts that turn's name down as it
    goes, and a record in which one turn appears in the middle of another is two
    presses that overlapped.
    """
    root, port, reading, stop = start_reading()
    record = []
    was_mine, was_line = vimlink.mine, server.tick_line

    def slow_line(path, line, done):
        """Write a tick slowly enough that another press would arrive mid write."""
        record.append((threading.current_thread().name, 'write'))
        time.sleep(0.05)
        return was_line(path, line, done)

    vimlink.mine = lambda servername, writing: record.append(
        (threading.current_thread().name, f'claim {writing}')
    )
    server.tick_line = slow_line
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'tasks.md'}))

        def press(line):
            """Press one box, as one page of a reading does."""
            fetch_json(port, '/api/tick', 'POST', {'done': True, 'line': line})

        pressing = [threading.Thread(target=press, args=(line,)) for line in (1, 3, 4)]
        for thread in pressing:
            thread.start()
        for thread in pressing:
            thread.join(timeout=TIMEOUT)
        whose = [name for name, _ in record]
        assert len(set(whose)) == 3, record
        assert whose == sorted(whose, key=whose.index), record
    finally:
        vimlink.mine, server.tick_line = was_mine, was_line
        stop()


def test_a_click_in_vim_is_counted_and_a_move_is_not():
    """The page is told how many clicks vim has reported, so it can follow every one.

    A click is a jump the page goes to whatever the distance, and the moves
    around it are not, so the two have to be told apart. They are counted
    rather than flagged because the throttled report that follows a click
    carries the same line a moment later, and a flag would be taken back by it
    before the page had come round to look.
    """
    root, port, reading, stop = start_reading(editing=True)
    try:
        status, state = fetch_json(port, '/api/cursor')
        assert status == 200 and (state['clicks'], state['line']) == (0, None), state
        fetch_json(port, '/api/cursor', 'POST', {'line': 12})
        assert cursor_of(port) == (0, 12)
        fetch_json(port, '/api/cursor', 'POST', {'clicked': True, 'line': 30})
        assert cursor_of(port) == (1, 30)
        fetch_json(port, '/api/cursor', 'POST', {'line': 30})
        assert cursor_of(port) == (1, 30)
        fetch_json(port, '/api/cursor', 'POST', {'clicked': True, 'line': 30})
        assert cursor_of(port) == (2, 30)
    finally:
        stop()


def test_a_cursor_report_carries_how_far_down_its_window_the_cursor_sits():
    """The page needs where vim is holding the line, not only which line it is.

    A page that only knew the line would have to choose a height of its own for
    it, and the block would land somewhere other than where the reader is
    already looking in the other half.
    """
    root, port, reading, stop = start_reading(editing=True)
    try:
        assert fetch_json(port, '/api/cursor')[1]['share'] == server.DEFAULT_SHARE
        fetch_json(port, '/api/cursor', 'POST', {'line': 12, 'share': 0.75})
        assert fetch_json(port, '/api/cursor')[1]['share'] == 0.75
        fetch_json(port, '/api/cursor', 'POST', {'line': 12})
        assert fetch_json(port, '/api/cursor')[1]['share'] == server.DEFAULT_SHARE
        fetch_json(port, '/api/cursor', 'POST', {'line': 12, 'share': 4})
        assert fetch_json(port, '/api/cursor')[1]['share'] == server.DEFAULT_SHARE
        fetch_json(port, '/api/cursor', 'POST', {'line': 12, 'share': 'halfway'})
        assert fetch_json(port, '/api/cursor')[1]['share'] == server.DEFAULT_SHARE
    finally:
        stop()


def test_a_held_page_is_not_told_a_file_moved_aside_and_back_is_gone():
    """A save that moves the old file aside is not a document being taken away.

    Written this way by vim and by plenty else, and for the moment between the
    move and the new file landing the name has nothing at it. A page told that
    draws the line saying the document is gone, throws away what it was showing,
    and comes back at the top of a document the reader was some way down.
    """
    root, port, reading, stop = start_reading()
    try:
        held = start_holding(port)
        first = heard_down(held)
        aside = root / 'start.md~'
        (root / 'start.md').rename(aside)
        time.sleep(server.TELL_TICK * 4)
        aside.rename(root / 'start.md')
        (root / 'start.md').write_text(START_MD + '\nA new paragraph.\n', encoding='utf-8')
        later = heard_down(held)
        assert later['mtime'] is not None, later
        assert later['mtime'] > first['mtime'], (later, first)
        held.close()
    finally:
        stop()


def test_a_held_page_is_told_a_file_taken_away_for_good_is_gone():
    """A document that stays away is still reported, a grace after it went."""
    root, port, reading, stop = start_reading()
    try:
        held = start_holding(port)
        assert isinstance(heard_down(held)['mtime'], int)
        (root / 'start.md').unlink()
        assert heard_down(held)['mtime'] is None
        held.close()
    finally:
        stop()


def test_a_held_page_is_told_nothing_while_nothing_moves():
    """A reading speaks as the page takes hold and then holds its tongue.

    Every line the page hears sends it to look at the document again, so a
    reading with nothing to report says nothing rather than repeating itself down
    a connection that stays open for the whole of a reading.
    """
    root, port, reading, stop = start_reading()
    try:
        held = start_holding(port)
        first = heard_down(held)
        assert isinstance(first['mtime'], int), first
        held.connection.settimeout(server.TELL_TICK * 20)
        try:
            said = held.connection.recv(1024)
        except TimeoutError:
            said = b''
        assert said == b'', said
        held.close()
    finally:
        stop()


def test_a_held_page_is_told_the_file_was_written():
    """A write reaches the page down the connection the page is already holding.

    Nothing is asked of the page's clock. A browser slows the timers of a window
    it is not showing, so a page that had to ask would sit there showing a file as
    it was a minute ago. The reading watches the file and says so instead.
    """
    root, port, reading, stop = start_reading()
    try:
        held = start_holding(port)
        first = heard_down(held)
        time.sleep(0.05)
        (root / 'start.md').write_text(START_MD + '\nA new paragraph.\n', encoding='utf-8')
        later = heard_down(held)
        assert later['mtime'] > first['mtime'], (later, first)
        held.close()
    finally:
        stop()


def test_a_held_page_is_told_whether_vim_is_up():
    """What the Edit toggle follows arrives the same way everything else does.

    The toggle has to follow the reading rather than lead it, so that a vim
    quitting of its own accord unticks it and a press the reading could not
    honour puts it back where it was.
    """
    root, port, reading, stop = start_reading(editable=True)
    try:
        held = start_holding(port)
        assert heard_down(held)['editing'] is False
        reading.editing = True
        assert heard_down(held)['editing'] is True
        reading.editing = False
        assert heard_down(held)['editing'] is False
        held.close()
    finally:
        stop()


def test_a_link_is_followed_in_vim_while_vim_is_up():
    """Following a link takes vim with it while vim is up, and speaks to nobody otherwise.

    Both halves of a reading have to be of the same file, or the sync marks a
    document vim does not have open. That holds for a vim still waiting out of
    sight as much as for one on the screen: it is the vim the next session will
    show, and it should already be on the document the page is on when it is
    shown. A reading with no vim at all has nobody to tell, and must not go
    looking for one.
    """
    root, port, reading, stop = start_reading()
    told = []
    was = vimlink.edit
    vimlink.edit = lambda servername, path: told.append((servername, Path(path).name))
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'notes/other.md'}))
        assert told == [], told
        reading.waiting = True
        fetch_json(port, '/doc?' + urlencode({'path': 'start.md'}))
        assert told == [(SERVERNAME, 'start.md')], told
        reading.waiting = False
        reading.editing = True
        fetch_json(port, '/doc?' + urlencode({'path': 'notes/other.md'}))
        assert told[-1] == (SERVERNAME, 'other.md'), told
    finally:
        vimlink.edit = was
        stop()


def test_a_page_letting_go_does_not_end_a_reading_vim_is_holding():
    """A reading with vim up is held by vim, whatever became of the page beside it.

    Closing the page of an editing reading is an asking for vim to quit, and vim
    refuses while anything in it is unwritten. So the page going has no say here
    until vim has gone too, or work vim is quite right to be holding on to would
    be taken away a moment after the page was closed.
    """
    root, port, reading, stop = start_reading(editable=True, editing=True)
    stopped, watching = start_watching(reading)
    try:
        held = start_holding(port)
        held.close()
        waited = server.RETURN_GRACE * 3
        assert not stopped.wait(waited), 'a page let go ended a reading vim was holding'
        reading.editing = False
        assert stopped.wait(TIMEOUT), 'the reading outlived both its page and vim'
    finally:
        stop()
        watching.join(timeout=TIMEOUT)


def test_a_page_letting_go_ends_the_reading_at_once():
    """A page holds the reading by its connection, so the reading ends with it.

    Nothing else is waited for. A reading whose window was closed leaves its
    command sitting in the terminal for as long as it takes to notice, and what
    the connection dropping gives is the shortest notice there is.
    """
    root, port, reading, stop = start_reading()
    stopped, watching = start_watching(reading)
    try:
        held = start_holding(port)
        assert not stopped.wait(server.RETURN_GRACE), 'a reading being read was ended'
        held.close()
        assert stopped.wait(TIMEOUT), 'a page let go left the reading running'
    finally:
        stop()
        watching.join(timeout=TIMEOUT)


def test_a_page_that_comes_straight_back_holds_the_reading():
    """A reload lets go on its way out, and the reading waits for the page coming back.

    The page takes hold again before it has drawn anything, so it is back well
    inside the wait. A reading ended the moment its page let go would leave
    every reload looking at a page with nothing behind it.
    """
    root, port, reading, stop = start_reading()
    stopped, watching = start_watching(reading)
    try:
        start_holding(port).close()
        held = start_holding(port)
        waited = server.RETURN_GRACE * 3
        assert not stopped.wait(waited), 'a reloaded page ended the reading behind it'
        held.close()
        assert stopped.wait(TIMEOUT), 'a page let go left the reading running'
    finally:
        stop()
        watching.join(timeout=TIMEOUT)


def test_a_page_that_goes_while_it_is_answered_leaves_the_terminal_alone():
    """A page that drops its connection mid answer is not news, and a real fault is.

    A browser closing a window drops whatever it had in flight, and the reading
    finds out by the write it was in the middle of failing. That is the page
    going, which the reading already knows how to carry, and printing a stack
    over the terminal for it would say something is wrong when nothing is: the
    terminal belongs to whoever started the reading.

    Anything else is still worth hearing about, since a fault the reading says
    nothing about is a fault nobody can act on.
    """
    root, port, reading, stop = start_reading()
    said = io.StringIO()
    try:
        with redirect_stderr(said):
            for _ in range(8):
                sock = socket.create_connection((server.HOST, port), timeout=TIMEOUT)
                sock.sendall(request_head(
                    port, 'POST', '/api/tick', 'Content-Length: 4096') + b'{"line"')
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, LINGER)
                sock.close()
            time.sleep(0.5)
        assert said.getvalue() == '', said.getvalue()[:400]

        was = server.load_state
        server.load_state = broken_state
        try:
            with redirect_stderr(said):
                fetch_raw(port, request_head(port, 'GET', '/doc'))
                time.sleep(0.5)
        finally:
            server.load_state = was
        assert 'the state file fell over' in said.getvalue(), said.getvalue()[:400]
    finally:
        stop()


def test_a_page_that_says_nothing_keeps_the_reading():
    """A page holding the reading keeps it, however long it goes without speaking.

    A page that had to speak on a timer to stay alive would lose the reading
    behind its own window: a browser slows the timers of a window that is not in
    front of you, and stops them outright while the machine is asleep. What is
    watched is the connection instead, which stays up through both.
    """
    root, port, reading, stop = start_reading()
    stopped, watching = start_watching(reading)
    try:
        held = start_holding(port)
        quiet = server.RETURN_GRACE * 5
        assert not stopped.wait(quiet), 'a silent page lost the reading behind it'
        held.close()
        assert stopped.wait(TIMEOUT), 'a page let go left the reading running'
    finally:
        stop()
        watching.join(timeout=TIMEOUT)


def test_absolute_and_parent_paths_are_not_served():
    """A file named by ../ or by an absolute path is not found, on either route."""
    root, port, reading, stop = start_reading()
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
        status, doc = fetch_json(port, '/doc')
        assert doc['name'] == 'start.md', doc['name']
    finally:
        stop()


def test_an_answer_is_not_held_back_by_the_network():
    """A reply goes out the moment it is written, rather than waiting to be asked for.

    A reading answers in two writes, the headers and then the body, and both of
    them are small. TCP holds a second small write back until the first has been
    answered for, and the other end has nothing to say and answers at its own
    leisure, so every reply a page waits for costs the best part of a twentieth
    of a second that no part of this program spent doing anything.

    Nothing on the far side of it is ever more than a hop away: the reading
    serves one page on this machine and nowhere else. So it is turned off, and a
    request costs what it costs to answer.

    The route asked here is the one that answers without doing anything at all,
    so what is left in the number is the waiting and nothing else. The margin is
    a wide one rather than a measurement: held back, one of these is forty
    milliseconds, and no faster machine makes it less, since it is a clock and
    not a cost.
    """
    root, port, reading, stop = start_reading()
    try:
        connection = HTTPConnection(server.HOST, port, timeout=TIMEOUT)
        took = []
        for _ in range(20):
            started = time.monotonic()
            connection.request('POST', '/api/drawn', b'{}',
                               {'Content-Type': 'application/json'})
            connection.getresponse().read()
            took.append(time.monotonic() - started)
        connection.close()
        middle = sorted(took)[len(took) // 2]
        assert middle < 0.02, f'{middle * 1000:.0f} ms to answer a request'
    finally:
        stop()


def test_asset_inside_the_tree_is_served():
    """GET /file/ sends a file from inside the tree, bytes and type intact."""
    root, port, reading, stop = start_reading()
    try:
        status, content_type, data = fetch(port, '/file/images/pixel.png')
        assert status == 200, status
        assert data == PIXEL_PNG, data
        assert content_type.startswith('image/png'), content_type
    finally:
        stop()


def test_blocks_carry_the_lines_render_gave_them():
    """GET /doc sends the blocks and the outline the renderer produced."""
    root, port, reading, stop = start_reading()
    try:
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        assert doc['name'] == 'start.md', doc['name']
        ranges = [(block['type'], block['line_start'], block['line_end'])
                  for block in doc['blocks']]
        assert ranges == START_BLOCKS, ranges
        assert doc['outline'] == START_OUTLINE, doc['outline']
        assert doc['blocks'] == served_blocks(START_MD), doc['blocks']
    finally:
        stop()


def test_document_image_is_reachable_where_the_page_is_told_to_look():
    """The address an image carries in the page is one this server answers with the file.

    The page is served at the root, so a document's own relative target would
    be read against that and reach nothing. What the page is handed has to be an
    address the reading answers, and the only way to say so is to follow it.
    """
    root, port, reading, stop = start_reading()
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


def test_edit_is_recorded_and_answered_with_the_state_as_it_stands():
    """POST /api/edit records what the page asked for and says what the reading is doing.

    Opening vim takes a second and closing it may be refused outright by a vim
    with unsaved work, so the answer cannot be the wish granted. It is the state
    as it stands, and the page learns the outcome from the poll it already runs.

    A reading waits in two ways, on an event between sessions and on its X
    connection inside one, so the asking has to reach both. The pipe is the
    second of those roads and a session that is not told down it goes on waiting
    for a quarter of a second after every press.
    """
    root, port, reading, stop = start_reading(editable=True)
    try:
        assert reading.wanted is False, reading.wanted
        assert not reading.asked.is_set(), 'nobody asked yet'
        assert not said_down(reading), 'nothing has been asked for yet'
        status, reply = fetch_json(port, '/api/edit', 'POST', {'editing': True})
        assert status == 200, status
        assert reading.wanted is True, reading.wanted
        assert reading.asked.is_set(), 'nobody was woken'
        assert said_down(reading), 'nothing was said down the pipe'
        assert reply == {'editing': False}, reply
        reading.editing = True
        status, reply = fetch_json(port, '/api/edit', 'POST', {'editing': False})
        assert reply == {'editing': True}, reply
        assert reading.wanted is False, reading.wanted
        assert fetch_json(port, '/api/edit', 'POST', {})[0] == 200
        assert reading.wanted is False, reading.wanted
    finally:
        stop()
    root, port, reading, stop = start_reading()
    try:
        assert fetch_json(port, '/api/edit', 'POST', {'editing': True})[1] == {
            'editing': False}
        assert reading.wanted is False, reading.wanted
        assert not reading.asked.is_set(), 'an ask nobody can honour woke the reading'
        assert not said_down(reading), 'an ask nobody can honour was passed on'
    finally:
        stop()


def test_each_document_keeps_its_own_look():
    """Settings belong to the document they were set on, not to every document.

    Two documents read one after the other have nothing in common but the file
    the settings live in, so the theme and the toggles one of them was left in
    have to be stored under its own name. A document nothing was ever set on
    opens the way the very first reading did, whatever was last set elsewhere.
    """
    root, port, reading, stop = start_reading()
    try:
        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'github', 'contents': False, 'middle': False})
        fetch_json(port, '/doc?' + urlencode({'path': 'notes/other.md'}))
        status, doc = fetch_json(port, '/doc')
        assert doc['state'] == {'contents': False, 'middle': False,
                                'theme': 'browser', 'wide': False}, doc['state']
        assert b'class="browser reader"' in fetch(port, '/')[2]

        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'report', 'contents': True, 'wide': False})
        fetch_json(port, '/doc?' + urlencode({'path': 'start.md'}))
        status, doc = fetch_json(port, '/doc')
        assert doc['state'] == {'contents': False, 'middle': False,
                                'theme': 'github', 'wide': False}, doc['state']
        assert b'class="github reader"' in fetch(port, '/')[2]
    finally:
        stop()


def test_editable_says_whether_the_edit_box_belongs_on_the_page():
    """The document reply carries whether the reading could open vim at all.

    The controls are built from the first reply, and a printed copy is answered
    by no server, so a copy carries no box without having to be told not to.
    """
    root, port, reading, stop = start_reading()
    try:
        assert fetch_json(port, '/doc')[1]['editable'] is False
    finally:
        stop()
    root, port, reading, stop = start_reading(editable=True)
    try:
        assert fetch_json(port, '/doc')[1]['editable'] is True
    finally:
        stop()


def test_every_box_pressed_at_once_lands_in_the_document():
    """Boxes pressed faster than they can be written all reach the document.

    A press is the file read, one line of it changed, and the whole of it
    written back. The page does not wait for one press to land before sending
    the next, and a reading serves each of them on a turn of its own, so two
    presses can read the same document and write it back over each other. What
    is lost that way is a box the page shows ticked, was told had landed, and
    the document does not carry.
    """
    root, port, reading, stop = start_reading()
    many = root / 'many.md'
    count = 60
    many.write_text(
        '# Many\n\n' + ''.join(f'- [ ] item {n}\n' for n in range(count)),
        encoding='utf-8',
    )
    landed = []
    try:
        fetch_json(port, '/doc?' + urlencode({'path': 'many.md'}))

        def press(line):
            """Press one box, as one page of a reading does.

            A connection refused is asked for again. Sixty pressed at once is
            more than a browser would ever open at one host, and a listening
            socket that turned some of them away is this test knocking too hard
            rather than anything the reading did with the presses it took.
            """
            for _ in range(10):
                try:
                    landed.append(fetch_json(port, '/api/tick', 'POST',
                                             {'done': True, 'line': line}))
                    return
                except AssertionError:
                    time.sleep(0.05)
            landed.append(('unanswered', line))

        pressing = [threading.Thread(target=press, args=(line + 3,))
                    for line in range(count)]
        for thread in pressing:
            thread.start()
        for thread in pressing:
            thread.join(timeout=TIMEOUT)
        assert landed == [(200, {'ticked': True})] * count, landed
        written = many.read_text(encoding='utf-8')
        assert written.count('- [x] item') == count, written.count('- [x] item')
        assert len(written.splitlines()) == count + 2, len(written.splitlines())
    finally:
        stop()


def test_every_theme_is_accepted_and_a_fifth_is_not():
    """All four theme keys are stored and served back, and a name outside them is not."""
    root, port, reading, stop = start_reading()
    try:
        for theme in THEMES:
            status, reply = fetch_json(
                port, '/api/state', 'POST', {'theme': theme, 'contents': False})
            assert status == 200, (theme, status)
            assert reply == {'contents': False, 'middle': False, 'theme': theme,
                             'wide': False}, reply
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


def test_export_boxes_cannot_be_pressed():
    """A printed copy draws its task list boxes as the document had them, and dead.

    There is nothing behind a copy to write a tick into, so a box that moved
    there would say the document had changed when nothing had.
    """
    root, stop = start_export()
    try:
        printed = export.write_export(root / 'tasks.md').read_text(encoding='utf-8')
        assert 'task-list-item-checkbox' in printed, printed[:200]
        assert 'disabled' in printed, printed[:200]
        assert 'data-line' not in printed, 'a copy carries a box that can be pressed'
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
        assert json.dumps(START_OUTLINE) in printed, 'the outline was not carried over'
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
        rest = re.sub(r'<style>.*</style>', '', printed, flags=re.DOTALL)
        sources = re.findall(r'src=\\?"([^"\\]*)', rest)
        assert len(sources) == 1, sources
        for value in sources:
            assert value.startswith('data:'), value
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


def test_icon_is_named_by_the_page_and_served():
    """The page names an icon and the server sends it, so the window has one to wear.

    A reading that is only the page lives in a window the browser puts up, and
    such a window wears whatever icon its page names. Nothing else names one for
    it, so without this a reading stands on the panel under whatever the browser
    gives a page that asked for nothing.
    """
    root, port, reading, stop = start_reading()
    try:
        page = fetch(port, '/')[2]
        assert b'rel="icon"' in page, page[:400]
        assert f'href="{server.ICON_ROUTE}"'.encode('utf-8') in page, page[:400]
        status, content_type, data = fetch(port, server.ICON_ROUTE)
        assert status == 200, status
        assert content_type.startswith('image/png'), content_type
        assert data.startswith(b'\x89PNG'), data[:16]
    finally:
        stop()


def test_linked_document_inside_the_tree_is_rendered():
    """GET /doc?path= renders another document in the tree and the reading moves to it."""
    root, port, reading, stop = start_reading()
    try:
        status, doc = fetch_json(
            port, '/doc?' + urlencode({'path': 'notes/other.md'}))
        assert status == 200, status
        assert doc['name'] == 'notes/other.md', doc['name']
        assert doc['blocks'] == served_blocks(OTHER_MD), doc['blocks']
        status, again = fetch_json(port, '/doc')
        assert again['name'] == 'notes/other.md', again['name']
    finally:
        stop()


def test_full_width_is_off_until_it_is_ticked_and_lands_on_the_first_paint():
    """The full width setting is stored, reported back, and already on the root element.

    The page could turn the class on itself once it has the document, but the
    lines would be drawn one way and rewrap the moment it did, so the setting
    has to arrive with the markup rather than after it.
    """
    root, port, reading, stop = start_reading()
    try:
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is False, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader"' in page, page[:200]

        status, reply = fetch_json(
            port, '/api/state', 'POST', {'theme': 'browser', 'contents': False,
                                         'wide': True})
        assert status == 200, status
        assert reply['wide'] is True, reply
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is True, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader wide"' in page, page[:200]

        state.STATE_PATH.write_text(
            json.dumps({'documents': {str(root / 'start.md'):
                                      {'theme': 'browser', 'contents': False}}}),
            encoding='utf-8')
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['wide'] is False, doc['state']
    finally:
        stop()


def test_middle_is_off_until_it_is_ticked_and_lands_on_the_first_paint():
    """The centring setting is stored, reported back, and already on the root element.

    It arrives with the markup for the same reason the full width setting does:
    the lines have to stand where the reader left them from the first paint,
    rather than down one edge and moved across the moment the script catches up.
    """
    root, port, reading, stop = start_reading()
    try:
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['middle'] is False, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader"' in page, page[:200]

        status, reply = fetch_json(
            port, '/api/state', 'POST', {'theme': 'browser', 'contents': False,
                                         'middle': True})
        assert status == 200, status
        assert reply['middle'] is True, reply
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['middle'] is True, doc['state']
        status, _, page = fetch(port, '/')
        assert b'class="browser reader middle"' in page, page[:200]

        state.STATE_PATH.write_text(
            json.dumps({'documents': {str(root / 'start.md'):
                                      {'theme': 'browser', 'contents': False}}}),
            encoding='utf-8')
        status, doc = fetch_json(port, '/doc')
        assert doc['state']['middle'] is False, doc['state']
    finally:
        stop()


def test_missing_or_broken_state_falls_back_to_browser():
    """A state file that is absent, malformed or naming no theme is not an error."""
    root, port, reading, stop = start_reading()
    try:
        default = {'contents': False, 'middle': False, 'theme': 'browser', 'wide': False}
        assert not state.STATE_PATH.exists(), state.STATE_PATH
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        assert doc['state'] == default, doc['state']
        broken = (
            '{not json at all',
            '[]',
            '{"documents": []}',
            '{"documents": {"' + str(root / 'start.md') + '": []}}',
            '{"documents": {"' + str(root / 'start.md') + '": {"theme": "puce"}}}',
            '{"theme": "github", "contents": true}',
        )
        for content in broken:
            state.STATE_PATH.write_text(content, encoding='utf-8')
            status, doc = fetch_json(port, '/doc')
            assert status == 200, (content, status)
            assert doc['state'] == default, (content, doc['state'])
    finally:
        stop()


def test_page_is_served_under_the_reading_s_own_name():
    """Every reading answers at its own name as well as at the root, and at no other name.

    The browser names the window it puts up after the address it was given, and
    that name is how a reading picks its own page's window out of the desktop
    when it comes to take it into a container. The name has to be settled before
    the page exists rather than when vim arrives, so a reading that is only
    viewing serves under one too.
    """
    root, port, reading, stop = start_reading()
    try:
        for path in ('/', f'/{SERVERNAME}'):
            status, content_type, page = fetch(port, path)
            assert status == 200, (path, status)
            assert content_type.startswith('text/html'), (path, content_type)
            assert b'<title>start.md</title>' in page, page[:200]
        assert fetch_json(port, '/MDEUSOTHER')[0] == 404, 'another reading was answered for'
    finally:
        stop()


def test_page_title_says_the_document_and_nothing_else():
    """The title is the document's name, and travels with the document.

    The tab, and the window on the panel while a reading is editing, both read
    it. The page writes its own title as it draws, so that following a link to
    another document takes the title along with it, and what it writes is the
    name the server sent rather than one put together again there.

    It reads the same in both states, since either way it is one reading of one
    document.
    """
    root, port, reading, stop = start_reading()
    try:
        assert b'<title>start.md</title>' in fetch(port, '/')[2]
        assert fetch_json(port, '/doc')[1]['name'] == 'start.md'
        moved = fetch_json(port, '/doc?' + urlencode({'path': 'notes/other.md'}))[1]
        assert moved['name'] == 'notes/other.md', moved
        reading.editing = True
        assert fetch_json(port, '/doc')[1]['name'] == 'notes/other.md'
    finally:
        stop()


def test_printing_a_document_that_is_not_text_is_refused():
    """A document that is not text is refused in a line, not in a stack.

    The printed copy is the whole document read at once, and a file that is not
    text cannot be read at all. Everything else the command will not do it says
    in one line and stops, and this one has to say it the same way: a stack over
    the terminal names the inside of the program to somebody who asked it to
    print a file.
    """
    tree = Path(tempfile.mkdtemp(prefix='mdeus-test-print-'))
    try:
        document = tree / 'binary.md'
        document.write_bytes(b'# Title\n\n\xff\xfe not text at all\n')
        done = subprocess.run(
            [sys.executable, str(COMMAND), '--print', str(document)],
            capture_output=True, text=True, timeout=TIMEOUT * 4,
        )
        assert done.returncode == 1, (done.returncode, done.stderr)
        assert 'Traceback' not in done.stderr, done.stderr
        assert f'not text: {document}' in done.stderr, done.stderr
        assert done.stdout == '', done.stdout
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def test_removed_file_gives_the_gone_reply_and_recovers():
    """A source file taken away gives the gone reply, and the reading survives it."""
    root, port, reading, stop = start_reading()
    try:
        gone = {'editable': False, 'editing': False, 'name': 'start.md',
                'gone': True,
                'state': {'contents': False, 'middle': False, 'theme': 'browser',
                          'wide': False}}
        source = root / 'start.md'
        source.unlink()
        status, doc = fetch_json(port, '/doc')
        assert status == 200, status
        assert doc == dict(gone, mtime=None), doc
        source.write_text(START_MD, encoding='utf-8')
        status, back = fetch_json(port, '/doc')
        assert 'gone' not in back, back
        assert back['blocks'] == served_blocks(START_MD), back['blocks']
        source.write_bytes(b'# Start\n\n\xff\xfe not text at all\n')
        status, invalid = fetch_json(port, '/doc')
        assert status == 200, status
        assert isinstance(invalid.pop('mtime'), int), invalid
        assert invalid == gone, invalid
    finally:
        stop()


def test_split_is_kept_beside_the_theme_and_falls_back():
    """The divider's share and the page's theme share a document's entry and neither puts the other out.

    The share belongs to the document it was dragged on, like everything else
    stored here, so one document's seam says nothing about another's.
    """
    root, port, reading, stop = start_reading()
    start = root / 'start.md'
    other = root / 'notes' / 'other.md'
    try:
        assert state.load_split(start) == state.DEFAULT_SPLIT, state.load_split(start)
        state.save_split(start, 0.62)
        assert state.load_split(start) == 0.62, state.load_split(start)
        assert state.load_split(other) == state.DEFAULT_SPLIT, state.load_split(other)
        state.save_split(other, 0.31)
        assert state.load_split(start) == 0.62, state.load_split(start)
        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'github', 'contents': True, 'wide': False})
        assert stored_settings(start) == {'contents': True, 'middle': False,
                                         'theme': 'github', 'wide': False,
                                         'split': 0.62}, stored_settings(start)
        state.save_split(start, 0.5)
        assert state.load_state(start) == {'contents': True, 'middle': False,
                                           'theme': 'github', 'wide': False}, (
            state.load_state(start)
        )
        assert state.load_state(other) == {'contents': False, 'middle': False,
                                          'theme': 'browser', 'wide': False}, (
            state.load_state(other)
        )
        for share in ('sideways', None, 0.02, 0.99):
            state.save_state(start, {'split': share})
            assert state.load_split(start) == state.DEFAULT_SPLIT, share
    finally:
        stop()


def test_state_file_is_never_read_half_written():
    """Somebody reading the state file only ever sees a whole and valid one."""
    root, port, reading, stop = start_reading()
    try:
        writes = 120
        last = {'contents': bool((writes - 1) % 2),
                'middle': bool((writes - 1) % 2),
                'theme': THEMES[(writes - 1) % len(THEMES)],
                'wide': not (writes - 1) % 2}

        def write_many():
            """Store a different state over and over, as the four controls would."""
            for index in range(writes):
                fetch_json(port, '/api/state', 'POST',
                           {'theme': THEMES[index % len(THEMES)],
                            'contents': bool(index % 2),
                            'middle': bool(index % 2),
                            'wide': not index % 2})

        fetch_json(port, '/api/state', 'POST',
                   {'theme': 'browser', 'contents': False, 'middle': True,
                    'wide': True})
        writer = threading.Thread(target=write_many)
        writer.start()
        seen = 0
        deadline = time.monotonic() + TIMEOUT
        while writer.is_alive() and time.monotonic() < deadline:
            try:
                stored = stored_settings(root / 'start.md')
            except (OSError, ValueError) as error:
                raise AssertionError(f'the state file was not whole: {error}')
            assert stored['theme'] in THEMES, stored
            assert isinstance(stored['contents'], bool), stored
            assert isinstance(stored['middle'], bool), stored
            assert isinstance(stored['wide'], bool), stored
            seen += 1
        writer.join(timeout=TIMEOUT)
        assert not writer.is_alive(), 'the writer never finished'
        assert seen > 10, f'only {seen} reads landed while the file was being written'
        final = stored_settings(root / 'start.md')
        assert final == last, final
    finally:
        stop()


def test_state_is_stored_and_reported_back():
    """POST /api/state writes the file, and the next /doc reports what it wrote."""
    root, port, reading, stop = start_reading()
    try:
        wanted = {'contents': True, 'middle': False, 'theme': 'report', 'wide': False}
        status, reply = fetch_json(port, '/api/state', 'POST', wanted)
        assert status == 200, status
        assert reply == wanted, reply
        assert stored_settings(root / 'start.md') == wanted, stored_settings(
            root / 'start.md')
        status, doc = fetch_json(port, '/doc')
        assert doc['state'] == wanted, doc['state']
    finally:
        stop()


def test_the_page_says_when_it_has_drawn():
    """The page says so once the document is on the screen.

    That is what the reading waits for before starting vim behind it. A reading
    that started vim earlier would have a browser and a gvim wanting the same
    machine at the moment somebody is watching the page draw. Taking hold of the
    reading is not the same thing and does not say it: a page takes hold before
    it has drawn anything, which is what carries a reload across.
    """
    root, port, reading, stop = start_reading()
    try:
        held = start_holding(port)
        assert not reading.drawn.is_set(), 'drawn before the page had drawn anything'
        assert fetch_json(port, '/api/drawn', 'POST') == (200, {'ok': True})
        assert reading.drawn.is_set(), 'a drawn page did not say so'
        fetch_json(port, '/api/drawn', 'POST')
        assert reading.drawn.is_set()
        held.close()
    finally:
        stop()


def test_the_vim_routes_answer_only_while_editing():
    """The cursor and the jump are there while vim is, and are not found otherwise.

    A reading that is viewing has no more of an API than a bare page needs. The
    two page scripts are loaded either way, since editing may begin at any
    moment, so the server is what keeps the sync from speaking into an empty
    room rather than the markup.
    """
    root, port, reading, stop = start_reading(editable=True)
    jumped = []
    was = vimlink.jump
    vimlink.jump = lambda servername, first, last: jumped.append((first, last))
    try:
        assert fetch_json(port, '/api/cursor')[0] == 404
        assert fetch_json(port, '/api/cursor', 'POST', {'line': 3})[0] == 404
        assert fetch_json(port, '/api/jump', 'POST', {'line': 3, 'last': 4})[0] == 404
        assert jumped == [], jumped
        reading.editing = True
        assert fetch_json(port, '/api/cursor')[0] == 200
        assert fetch_json(port, '/api/cursor', 'POST', {'line': 3})[0] == 200
        assert fetch_json(port, '/api/jump', 'POST', {'line': 3, 'last': 4})[0] == 200
        assert jumped == [(3, 4)], jumped
        reading.editing = False
        assert fetch_json(port, '/api/cursor')[0] == 404
    finally:
        vimlink.jump = was
        stop()


def test_vim_leaving_on_a_write_and_quit_ends_the_reading():
    """vim's goodbye is recorded, and only a vim the reading has open may say it.

    A reader who leaves vim on a write and quit means the whole reading to end
    rather than to fall back to the page alone, and the session cannot tell the
    two apart by watching vim go: both look like a process that has stopped. So
    vim says which it was on its way out, and this is where that is kept until
    the session comes to read it.

    It is nothing at all until vim says so, since every other way out of a
    session leaves the reading standing.
    """
    root, port, reading, stop = start_reading(editable=True)
    try:
        assert not reading.ends, 'a reading was ending before anything said so'
        assert fetch_json(port, '/api/ending', 'POST')[0] == 404
        assert not reading.ends, 'a reading with no vim up was told to end'
        reading.editing = True
        assert fetch_json(port, '/api/ending', 'POST')[0] == 200
        assert reading.ends, 'the reading did not hear vim say goodbye'
    finally:
        stop()


def test_symlink_out_of_the_tree_is_not_followed():
    """A name inside the tree pointing out of it is not found, on either route."""
    root, port, reading, stop = start_reading()
    try:
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
