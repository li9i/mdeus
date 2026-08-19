"""
Behaviour tests for vimwire.py. Run with: python3 test_vimwire.py

No vim is opened and nothing is said to the desktop. What is tested is what the
wire settles on either side of the desktop: the answer it takes out of a message
vim sent, and the window it picks out of the list of every vim that ever said it
was listening. The desktop is stood in for, since a test has none of its own.

That the wire reaches a real vim at all is not testable here and is in the
manual list instead, along with everything else about vim.
"""

import sys

import vimlink
import vimwire
from Xlib import X

SERVERNAME = 'MDEUSTEST'


class Desktop:
    """A stand in for the desktop, holding one list of vims and some windows."""

    def __init__(self, registry, windows):
        self.atoms = []
        self.registry = registry
        self.windows = windows

    def create_resource_object(self, kind, xid):
        """Answer for the window of one number, or for one that is not there."""
        return self.windows.get(xid, Gone())

    def intern_atom(self, name):
        """Return a number for an atom, and remember which name it stands for."""
        if name not in self.atoms:
            self.atoms.append(name)
        return self.atoms.index(name) + 1

    def screen(self):
        """Answer for the screen, whose root window carries the list of vims."""
        return SimpleScreen(SimpleRoot(Property(self.registry)))


class Gone:
    """A stand in for a window the desktop no longer has."""

    def get_attributes(self):
        """Refuse, the way the desktop refuses a question about a window that has gone."""
        raise vimwire.error.BadWindow.__new__(vimwire.error.BadWindow)

    def get_full_property(self, atom, kind):
        """Refuse for the same reason."""
        raise vimwire.error.BadWindow.__new__(vimwire.error.BadWindow)


class Property:
    """A stand in for what one property holds."""

    def __init__(self, value):
        self.value = value


class SimpleRoot:
    """A stand in for the root window, which carries the list of vims."""

    def __init__(self, listed):
        self.listed = listed

    def get_full_property(self, atom, kind):
        """Return the list, or nothing where there is none."""
        return self.listed if self.listed.value is not None else None


class Window:
    """A stand in for a window that may or may not be a vim the desktop is showing."""

    def __init__(self, shown=True, marked=True):
        self.marked = marked
        self.shown = shown

    def get_attributes(self):
        """Say whether the desktop is showing this window."""
        return SimpleState(X.IsViewable if self.shown else X.IsUnmapped)

    def get_full_property(self, atom, kind):
        """Say whether this window carries the mark vim puts on one it listens on."""
        return Property(b'9.1\0') if self.marked else None


class SimpleScreen:
    """A stand in for the screen, which is asked for its root window."""

    def __init__(self, root):
        self.root = root


class SimpleState:
    """A stand in for what the desktop says about a window."""

    def __init__(self, map_state):
        self.map_state = map_state


def reply(serial, result, failed=False):
    """Return the message vim sends back for one question."""
    parts = [b'', b'r', b'-E utf-8', f'-s {serial}'.encode('ascii'),
             b'-r ' + result.encode('utf-8')]
    if failed:
        parts.append(b'-c 1')
    return b'\0'.join(parts + [b''])


def test_a_stale_vim_in_the_list_is_passed_over():
    """The list of vims holds every one that ever listened, so the live one is looked for.

    A vim that has gone leaves its name and its window on the desktop's list,
    and a reading started later takes a name of its own while the old ones stay.
    Two things say a window is really a vim listening under that name: it is
    still there, and it carries the mark vim puts on a window it listens on. A
    window that has gone answers nothing at all, and a number since handed to
    some other program answers without the mark.

    Nothing is asked about how the window looks. The one vim registers is not
    the one it draws in: it is made for being spoken to and never shown, so a
    reading that asked whether the desktop was showing it would turn away every
    vim there is, including its own.
    """
    live = Window()
    registry = (
        b'11 ' + SERVERNAME.encode() + b'\0'
        b'22 ' + SERVERNAME.encode() + b'\0'
        b'33 ' + SERVERNAME.encode() + b'\0'
    )
    desktop = Desktop(registry, {0x22: Window(marked=False), 0x33: live})
    assert vimwire.vim_window(desktop, SERVERNAME) is live
    hidden = Window(shown=False)
    assert vimwire.vim_window(
        Desktop(b'11 ' + SERVERNAME.encode() + b'\0', {0x11: hidden}), SERVERNAME
    ) is hidden


def test_a_vim_of_another_name_is_not_taken_for_this_one():
    """A name is matched whole, so one reading never speaks to another's vim.

    Every reading names its vim after itself and several run at once, so a name
    that merely begins or ends another must not answer for it.
    """
    wanted = Window()
    registry = (
        b'11 MDEUSTESTING\0'
        b'22 NOTMDEUSTEST\0'
        b'33 ' + SERVERNAME.encode() + b'\0'
    )
    desktop = Desktop(registry, {0x11: Window(), 0x22: Window(), 0x33: wanted})
    assert vimwire.vim_window(desktop, SERVERNAME) is wanted
    for missing in ('MDEUSTES', 'MDEUSTESTS', ''):
        try:
            vimwire.vim_window(desktop, missing)
            raise AssertionError(f'{missing} was taken for {SERVERNAME}')
        except vimwire.Unheard:
            pass


def test_an_answer_to_another_question_is_not_taken_for_this_one():
    """An answer carries the number of the question it is for, and only that one is read.

    A reading asks vim things from several turns at once, and an answer left
    over from a question already given up on would otherwise be read as this
    one's. What that costs is a tick reported against the wrong line.
    """
    assert vimwire.reply_to(reply(7, 'yes'), 7) == 'yes'
    assert vimwire.reply_to(reply(6, 'no'), 7) is None
    assert vimwire.reply_to(reply(70, 'no'), 7) is None
    assert vimwire.reply_to(b'\0k\0-s 7\0', 7) is None
    assert vimwire.reply_to(b'', 7) is None


def test_an_answer_says_what_vim_said_and_nothing_else():
    """What comes back is the whole of vim's answer, whatever is in it.

    Anything vim can put in a string can come back: nothing at all, spaces at
    either end, and words in any writing, since the document being read may be
    in any of them.
    """
    for said in ('', 'n', 'r?', '1', 'a b  c', ' padded ', 'ένα δύο', 'l/r|s'):
        assert vimwire.reply_to(reply(3, said), 3) == said, said


def test_an_expression_vim_could_not_read_is_not_an_answer():
    """An expression vim refuses is no answer, and reads here as none.

    That is what the client command says about the same expression, by failing
    rather than by printing something, so the two roads agree.
    """
    try:
        vimwire.reply_to(reply(4, 'E449: Invalid expression received', failed=True), 4)
        raise AssertionError('a refusal was taken for an answer')
    except vimwire.Unheard:
        pass


def test_the_link_falls_back_to_the_vim_client():
    """Where the wire cannot be used the link speaks through vim's own command.

    That is the whole of what makes this safe to add: a desktop without the
    library to talk to it, a vim that is not listening, or anything else going
    wrong leaves a reading exactly as it was before, reading at the old speed.
    """
    asked, told = [], []
    was_ask, was_tell, was_remote = vimwire.ask, vimwire.tell, vimlink.remote

    def unheard(*args):
        """Stand in for a wire that cannot be used."""
        raise vimwire.Unheard('nothing to talk to the desktop with')

    def client(servername, *args):
        """Stand in for the vim client command."""
        (asked if args[0] == '--remote-expr' else told).append(args)
        return '1' if args[1] == vimlink.UNWRITTEN else 'n'

    vimwire.ask = vimwire.tell = unheard
    vimlink.remote = client
    try:
        assert vimlink.ask(SERVERNAME, 'mode(1)') == 'n'
        assert asked[0] == ('--remote-expr', 'mode(1)'), asked
        assert vimlink.tell(SERVERNAME, 'keys') is True
        assert told == [('--remote-send', 'keys')], told
        assert vimlink.unwritten(SERVERNAME) is True
    finally:
        vimwire.ask, vimwire.tell = was_ask, was_tell
        vimlink.remote = was_remote


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
