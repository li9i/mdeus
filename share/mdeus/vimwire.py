"""Speak to vim the way vim's own client does, over the desktop rather than through it.

vim listens for other programs on a property of its own window, and answers on
a property of theirs. That is the whole of the protocol, and the command that
usually carries it, `vim --servername X --remote-expr`, is a second vim started
for the length of one sentence.

Starting it is not what costs. What costs is that the client looks for the
answer twice a second, so it nearly always sleeps through a whole turn of its
own clock before noticing one that arrived at once: half a second for a
question, on any machine, however small the question. Everything a reading asks
vim is asked while somebody waits, so the reading writes on the property itself
and reads the answer as it lands, which takes about as long as anything else
the two of them do.

Nothing here is required. Every road through it ends at the client command
where the desktop is missing, where the library to talk to it is missing, or
where anything at all goes wrong, so a machine this does not suit is a machine
that reads at the old speed and no worse.
"""

import select
import threading
import time

try:
    from Xlib import X, Xatom, display, error
except ImportError:
    X = Xatom = display = error = None

COMM = 'Comm'
ENCODING = 'utf-8'
EXPRESSION = b'c'
KEYS = b'k'
REGISTRY = 'VimRegistry'
SERIALS = threading.Lock()
TIMEOUT = 2
VERSION = 'Vim'

serials = 0


class Unheard(Exception):
    """Raised where vim could not be reached this way, so the old way is tried."""


def ask(servername, expression):
    """Return what vim says an expression comes to, or raise where it will not answer."""
    return speak(servername, EXPRESSION, expression)


def next_serial():
    """Return a number no other question of this reading's is using.

    Every question carries one and every answer gives it back, which is what
    tells an answer meant for this question from one meant for the last. Handed
    out under a lock, since a reading answers its page on a thread for each
    request and any of them may be asking vim something.
    """
    global serials
    with SERIALS:
        serials += 1
        return serials


def parcel(fields):
    """Return the parts of a message, each as its letter and what follows it."""
    said = {}
    for field in fields:
        if len(field) >= 2 and field[:1] == b'-':
            said[field[1:2]] = field[3:] if field[2:3] == b' ' else b''
    return said


def reply_to(raw, serial):
    """Return the answer in a message where it answers this question, or None.

    An answer carries the number of the question it is for, so one arriving for
    a question that has already been given up on is passed over rather than
    taken for this one's. An expression vim could not make sense of is marked as
    such, and reads here as no answer at all, which is what the client command
    says about the same expression by failing.
    """
    parts = raw.split(b'\0')
    if len(parts) < 2 or parts[1:2] != [b'r']:
        return None
    said = parcel(parts[2:])
    if said.get(b's', b'').decode(ENCODING, 'replace') != str(serial):
        return None
    if said.get(b'c'):
        raise Unheard('vim could not make sense of it')
    return said.get(b'r', b'').decode(ENCODING, 'replace')


def speak(servername, kind, what):
    """Say one thing to vim on its own property, and bring back what it says.

    The message is appended rather than written, since vim reads its property by
    taking it away and another program may be halfway through saying something
    of its own.

    Keys are told and not asked, so nothing is waited for and the answer is
    empty. An expression is a question, and the answer lands on a window of this
    reading's that exists for the length of the asking.
    """
    if display is None:
        raise Unheard('there is nothing here to talk to the desktop with')
    try:
        d = display.Display()
    except Exception as problem:
        raise Unheard('no desktop') from problem
    try:
        comm = d.intern_atom(COMM)
        server = vim_window(d, servername)
        mine = d.screen().root.create_window(
            0, 0, 1, 1, 0, X.CopyFromParent, X.InputOutput, X.CopyFromParent,
            event_mask=X.PropertyChangeMask,
        )
        serial = next_serial()
        try:
            message = b'\0'.join([
                b'', kind,
                b'-n ' + servername.encode(ENCODING),
                b'-E ' + ENCODING.encode('ascii'),
                b'-s ' + what.encode(ENCODING),
                f'-r {mine.id:x} {serial}'.encode('ascii'),
                b'',
            ])
            server.change_property(comm, Xatom.STRING, 8, message, mode=X.PropModeAppend)
            d.sync()
            if kind == KEYS:
                return ''
            return waited_for(d, mine, comm, serial)
        finally:
            mine.destroy()
            d.sync()
    except Unheard:
        raise
    except Exception as problem:
        raise Unheard(str(problem)) from problem
    finally:
        d.close()


def tell(servername, keys):
    """Put keys in vim's mouth, and raise where they could not be put there."""
    speak(servername, KEYS, keys)


def vim_window(d, servername):
    """Return the window the vim of one name listens on.

    The desktop carries a list of every vim that ever said it was listening, and
    the ones that have since gone are still on it, so a name is looked for among
    all of them and the first that is really there is taken.

    The window named is not the one vim draws in. It is one vim makes for being
    spoken to and never shows, so nothing about how it looks says whether it is
    live, and asking that would turn away every vim there is. What says so is
    that the window is still there at all and that it carries the mark vim puts
    on a window it listens on. A window that has gone answers nothing, and a
    number since given to some other program answers without the mark.
    """
    listed = d.screen().root.get_full_property(
        d.intern_atom(REGISTRY), X.AnyPropertyType
    )
    if listed is None:
        raise Unheard('no vim has ever listened here')
    wanted = servername.casefold()
    for entry in bytes(listed.value).split(b'\0'):
        where, _, called = entry.partition(b' ')
        if not where or called.decode(ENCODING, 'replace').casefold() != wanted:
            continue
        window = d.create_resource_object('window', int(where, 16))
        try:
            if window.get_full_property(d.intern_atom(VERSION), X.AnyPropertyType):
                return window
        except (error.BadWindow, error.BadDrawable, error.BadMatch):
            continue
    raise Unheard(f'no vim is listening as {servername}')


def waited_for(d, mine, comm, serial):
    """Wait for vim's answer to one question, or give up on it.

    The property is read and taken away as it is read, since anything left there
    would be read again as the answer to the next question. Whatever is waited
    on here is waited on with the connection watched rather than with a clock,
    so an answer that comes at once is taken at once, which is the whole of why
    this exists.
    """
    deadline = time.monotonic() + TIMEOUT
    while True:
        said = mine.get_full_property(comm, X.AnyPropertyType)
        if said is not None and said.value:
            mine.delete_property(comm)
            answer = reply_to(bytes(said.value), serial)
            if answer is not None:
                return answer
        left = deadline - time.monotonic()
        if left <= 0:
            raise Unheard('vim did not answer')
        select.select([d.fileno()], [], [], left)
        while d.pending_events():
            d.next_event()
