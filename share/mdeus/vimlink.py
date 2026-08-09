"""
The link between a reading in the browser and the vim beside it.

Finding out whether a reading is already up, sending vim to a line or to
another document, asking it to quit, and carrying the cursor line back the
other way.

The server imports this to reach vim, and the container imports it to ask vim to
quit. The rest is reached from the command line, because the command that starts
a reading is a shell script, and because vim reports its cursor by starting a
process rather than by waiting on one.

The windows a reading is drawn in are container.py's, not this file's.
"""

import json
import subprocess
import sys
import urllib.request

# Leaves whatever mode vim is in, and unlike Escape cannot be read as the
# opening of the line that follows it.
NORMAL_MODE = r'<C-\><C-n>'
# Nothing here is worth waiting on. A vim busy enough not to answer, or a
# server that has stopped listening, must not hold up whoever asked.
TIMEOUT = 2


def document_open(servername):
    """Return the file the reading under this name has open, or nothing if it will not say."""
    return remote(servername, '--remote-expr', 'expand("%:p")') or ''


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
        f'{NORMAL_MODE}:call CvimJumpTo({int(first)}, {int(last)})<CR>',
    )


def main(argv):
    """Run one of the small jobs the reading asks for from the command line."""
    what = argv[0]
    if what == 'cursor':
        report_cursor(argv[1], argv[2])
    elif what == 'holder':
        if argv[1].upper() not in servers():
            return 1
        print(document_open(argv[1]))
    return 0


def quit_vim(servername):
    """Ask vim to quit, which it refuses to do while anything in it is unwritten."""
    remote(servername, '--remote-send', f'{NORMAL_MODE}:qa<CR>')


def remote(servername, *args):
    """Return what one vim client command said, or None if it did not answer."""
    try:
        return run(['vim', '--servername', servername, *args])
    except (OSError, subprocess.SubprocessError):
        return None


def report_cursor(url, line):
    """Tell the reading where the vim cursor is now.

    vim starts this and leaves it to itself, so a server that has stopped
    listening costs a moment of a process nobody is waiting for and no more.
    """
    request = urllib.request.Request(
        f'{url}/api/cursor',
        data=json.dumps({'line': int(line)}).encode('utf-8'),
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


def servers():
    """Return the names vim answers to on this display, upper cased as vim keeps them."""
    try:
        return run(['vim', '--serverlist']).split()
    except (OSError, subprocess.SubprocessError):
        return []


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
