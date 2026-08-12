"""
The link between a reading in the browser and the vim beside it.

Sending vim to a line or to another document, asking it to quit, and carrying
the cursor line back the other way.

The server imports this to reach vim, and the window imports it to ask vim to
quit. The cursor report is reached from the command line instead, because vim
reports its cursor by starting a process rather than by waiting on one.

The windows an editing session is drawn in are window.py's, not this file's.
"""

import json
import subprocess
import sys
import urllib.request

ASKING = 'r'
NORMAL_MODE = r'<C-\><C-n>'
TIMEOUT = 2


def edit(servername, path):
    """Send vim to another document, so that both halves of a reading show the same file.

    The file travels as an argument rather than as typed keys, so a name with a
    space or a per cent sign in it arrives as itself. vim takes this in any
    mode and is left in normal mode by it.
    """
    remote(servername, '--remote-silent', str(path))


def jump(servername, first, last):
    """Send vim to a block of the document it has open, and light the whole of it.

    What vim does on arrival is a function of vim's own, sourced when the
    reading started, since centring the block and marking it for a moment is
    more than a line of typed keys can carry.
    """
    remote(
        servername,
        '--remote-send',
        f'{NORMAL_MODE}:call MdeusJumpTo({int(first)}, {int(last)})<CR>',
    )


def listening(servername):
    """Say whether keys sent to vim would be acted on.

    A vim with a question up is answering whoever is reading and nothing else.
    Keys sent to it then are neither acted on nor kept: they are dropped, and
    the sending looks as though it worked. The document having been written by
    another program is the question this happens with, and an ask to quit
    arriving while it stands is the press that appears to have been ignored.

    A vim that answers nothing at all is read the same way. Either it has gone,
    and there is nothing to send to, or it is held up in something that does not
    listen, and there the sending waits out its own timeout for nothing.

    Nothing here changes what vim does. It is how the reading knows an asking
    landed, so that one that did not can be made again.
    """
    return not (remote(servername, '--remote-expr', 'mode(1)') or ASKING).startswith(
        ASKING
    )


def main(argv):
    """Run the small job the reading asks for from the command line."""
    what = argv[0]
    if what == 'cursor':
        report_cursor(argv[1], argv[2], argv[3:4] == ['click'])
    return 0


def quit_vim(servername):
    """Ask vim to quit, which it refuses to do while anything in it is unwritten.

    What comes back says whether the asking was acted on at all, which is not the
    same as vim agreeing to go: a vim that heard and refused because something in
    it is unwritten has heard. Only a vim that would have dropped the asking says
    False, and whoever wanted it to go asks again.
    """
    if not listening(servername):
        return False
    return remote(servername, '--remote-send', f'{NORMAL_MODE}:qa<CR>') is not None


def remote(servername, *args):
    """Return what one vim client command said, or None if it did not answer."""
    try:
        return run(['vim', '--servername', servername, *args])
    except (OSError, subprocess.SubprocessError):
        return None


def report_cursor(url, line, clicked=False):
    """Tell the reading where the vim cursor is now.

    vim starts this and leaves it to itself, so a server that has stopped
    listening costs a moment of a process nobody is waiting for and no more.

    A line the pointer was clicked on says so, because the page follows a click
    to wherever it lands and follows an ordinary move only when it is far
    enough to be worth following.
    """
    request = urllib.request.Request(
        f'{url}/api/cursor',
        data=json.dumps({'clicked': clicked, 'line': int(line)}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    try:
        urllib.request.urlopen(request, timeout=TIMEOUT).close()
    except OSError:
        pass


def run(command):
    """Return what a command printed, raising if it is missing, fails or hangs."""
    done = subprocess.run(
        command, capture_output=True, check=True, text=True, timeout=TIMEOUT
    )
    return done.stdout.strip()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
