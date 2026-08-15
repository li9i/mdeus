"""
The link between a reading in the browser and the vim beside it.

Sending vim to a line or to another document, asking it to quit, and carrying
the cursor line and vim's own goodbye back the other way.

The server imports this to reach vim, and the window imports it to ask vim to
quit. The cursor report is reached from the command line instead, because vim
reports its cursor by starting a process rather than by waiting on one.

The windows an editing session is drawn in are window.py's, not this file's.
"""

import json
import subprocess
import sys
import urllib.request

import vimwire

ASKING = 'r'
NORMAL_MODE = r'<C-\><C-n>'
TICKED = '1'
TIMEOUT = 2


def ask(servername, expression):
    """Return what vim says an expression comes to, or None where it did not answer.

    Over the desktop where that can be done, since vim listens on a property of
    its own window and answering takes about as long as anything else the two of
    them do. Through vim's own client command where it cannot, which is a second
    vim started for one sentence and half a second spent waiting on it, and
    which is what this ran on before and still runs on where the shorter road is
    shut.
    """
    try:
        return vimwire.ask(servername, expression)
    except vimwire.Unheard:
        return remote(servername, '--remote-expr', expression)


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
    tell(servername, f'{NORMAL_MODE}:call MdeusJumpTo({int(first)}, {int(last)})<CR>')


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

    It is the dear one. Every question put to vim waits half a second on the
    client that carries it, whatever the question, so this is asked where the
    answer changes what happens next and not on the way to anything a reader is
    waiting for.
    """
    return not (ask(servername, 'mode(1)') or ASKING).startswith(ASKING)


def main(argv):
    """Run the small job the reading asks for from the command line."""
    what = argv[0]
    if what == 'cursor':
        report_cursor(argv[1], argv[2], argv[3:4] == ['click'])
    elif what == 'ending':
        report_ending(argv[1])
    return 0


def mine(servername, writing):
    """Tell vim whether the change about to reach the document is the reading's own.

    A box pressed while the page is alone is written into the file by the
    reading, and a vim holding that document finds the change the way it finds
    anybody else's: by asking whether to load it. Behind a page that is being
    read alone, that question stands in a pane nobody is looking at, and the
    session opened later opens on it. So vim is told first and takes that one
    change without asking.

    Said the other way where the tick was refused and nothing was written. A
    claim left standing would be spent on whatever wrote the document next, and
    that one is as likely to be a formatter as the reading.

    Told rather than asked, since nothing here wants an answer and a question
    put to vim costs half a second of the press somebody just made. What that
    gives up is knowing when vim took it, so the claim is good for a moment
    rather than until it is spent: vim looks at the document once a second, and
    a claim that outlives that look by a margin is a claim that cannot arrive
    late. It cannot linger either, which the one it replaces could, having no
    hour of its own to run out at.
    """
    tell(servername, f'{NORMAL_MODE}:call MdeusMine({int(bool(writing))})<CR>')


def quit_vim(servername):
    """Tell vim to go, and say whether the telling went out.

    Told rather than asked. Telling vim something costs the moment it takes to
    start the client that carries the word. Asking vim something and waiting for
    the answer costs half a second whatever the question, because the client
    that carries it looks for the answer twice a second and so sleeps through a
    whole turn of its own clock before noticing one that arrived at once. This
    is the press somebody is waiting on, so it says its piece and stops there.

    What comes back is therefore only that the word left, which is not the same
    as vim having it: a vim with a question up hears nothing until it has been
    answered, and the word is dropped. Whether that happened is worth a
    question, and listening() is that question, asked afterwards by whoever
    minds and only where the answer changes anything. It does not change
    anything in the ordinary case, where vim has gone by then.

    What is sent is a function of vim's own rather than the quit itself, because
    a quit vim refuses leaves a message standing that has to be dismissed before
    vim will hear anything else, and a session that tells vim to go once a
    press would be sending into that. The function looks first and says its
    piece where it will not go, so vim is left listening either way and the next
    telling lands as cleanly as the first. It is also the same to send twice as
    once, which is what lets one be sent again where it may not have arrived.

    Nothing is sent to a vim that is not there, since the client answers nothing
    and says so at once.
    """
    return tell(servername, f'{NORMAL_MODE}:call MdeusGo()<CR>')


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


def report_ending(url):
    """Tell the reading that the vim now leaving is to take the whole reading with it.

    Sent for a write and quit and for nothing else. Quitting vim any other way
    hands the page back to the desktop as it always did, and so does the Edit
    toggle, which asks vim to quit in the same breath.

    vim waits for this rather than starting it and walking away, which is the
    one place in the link where that is true. It is sent as vim is leaving, and
    a message the reading heard a moment after the process it was about is gone
    arrives too late to be acted on: the session would already have put the
    window away and handed the page back.
    """
    request = urllib.request.Request(f'{url}/api/ending', data=b'', method='POST')
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


def tell(servername, keys):
    """Put keys in vim's mouth, and say whether they went.

    The same two roads the questions take, and the shorter one for the same
    reason: it is a property written on vim's own window rather than a second
    vim started to write it.

    What comes back is only that the keys left. Whether vim acted on them is
    another matter, and one nothing here can see: a vim with a question up takes
    keys and holds them until it has been answered.
    """
    try:
        vimwire.tell(servername, keys)
        return True
    except vimwire.Unheard:
        return remote(servername, '--remote-send', keys) is not None


def tick(servername, line, done, path):
    """Write a task list item in vim as ticked or unticked, and say whether it was.

    The change lands in the buffer and the file is not written, so a tick joins
    whatever else the reader has unwritten and goes to the disk when they save.
    Writing the file instead would be the document changing under the vim
    holding it, which vim puts a question up about.

    vim is asked rather than told: it is the one that can see whether the line is
    a task list item at all, since the buffer is the document as it stands while
    the file is the document as it was last saved. It is given the document the
    page is showing as well, and answers no where it has something else open,
    so a reader who took vim off to another file cannot have a line of that one
    rewritten from a page that is not showing it.

    A vim with a question up answers no. It is asked rather than tested for
    first, because it can see that about itself as easily as it can see the
    line, and one question put to vim costs half a second where two cost a
    whole one. Either way the page hears that the tick did not land, rather
    than being left showing one the document does not carry.
    """
    said = ask(
        servername,
        f"MdeusTick({int(line)}, {int(bool(done))}, '{vim_string(path)}')",
    )
    return said == TICKED


def vim_string(text):
    """Return text as a vim single quoted string, without the quotes.

    A single quote inside one of those is written twice. A path is the only
    thing sent this way, and nothing else in it means anything to vim.
    """
    return str(text).replace("'", "''")


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
