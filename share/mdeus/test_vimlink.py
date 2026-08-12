"""
Behaviour tests for vimlink.py. Run with: python3 test_vimlink.py

No vim is opened. What is tested is what the link decides before it sends
anything: whether the vim on the other end is in a state to be sent keys, and
what it says afterwards about whether the sending landed. The vim client command
is stood in for, since what it does is talk to a vim that a test has none of.
"""

import sys

import vimlink

SERVERNAME = 'MDEUSTEST'


class Vim:
    """A stand in for the vim client command, answering as one vim would.

    Asked what vim is doing it answers the mode it was made with, and a stand in
    made with nothing answers nothing at all, which is what a vim that has gone
    or is held up in something does. Everything else is remembered rather than
    sent, which is how a test sees what reached a vim that should have been left
    alone.
    """

    def __init__(self, mode='n'):
        self.mode = mode
        self.sent = []

    def __call__(self, servername, *args):
        """Answer the one question asked of a vim, and remember the rest."""
        if args[0] == '--remote-expr':
            return self.mode
        self.sent.append(args)
        return ''


def spoken_to(vim, what):
    """Run one call against a stand in for vim, and return what it answered."""
    was = vimlink.remote
    vimlink.remote = vim
    try:
        return what()
    finally:
        vimlink.remote = was


def test_a_vim_that_answers_nothing_is_sent_nothing():
    """A vim that will not say what it is doing is not sent keys either.

    Either it has gone, and there is nothing there to send to, or it is held up
    in something that is not listening, and the sending would wait out its own
    timeout to no purpose. Both are answered the same way, by saying the asking
    did not land, so that whoever wants vim to go asks again.
    """
    vim = Vim(None)
    landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
    assert landed is False, landed
    assert vim.sent == [], vim.sent


def test_a_vim_waiting_to_be_answered_is_not_asked_to_quit():
    """An ask to quit is not counted as landing on a vim that would drop it.

    A vim with a question up is answering whoever is reading and nothing else,
    and keys sent to it then are dropped rather than kept, while the sending
    itself looks as though it worked. A session that took that for vim having
    heard would wait for a vim that was never told, and the press that asked for
    the reading to end would be gone for good.

    All three of the states vim waits to be answered in are read the same way:
    the hit enter prompt, the more prompt, and a question with choices in it.
    """
    for mode in ('r', 'rm', 'r?'):
        vim = Vim(mode)
        landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
        assert landed is False, (mode, landed)
        assert vim.sent == [], (mode, vim.sent)


def test_a_vim_with_nothing_up_is_asked_and_says_it_heard():
    """A vim that is listening is sent the asking, and the asking is said to have landed.

    Landing is not the same as agreeing. A vim that heard and refused because
    something in it is unwritten has heard, and a session that hears otherwise
    would ask again every second for as long as the reader takes to save.
    """
    vim = Vim()
    landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
    assert landed is True, landed
    assert len(vim.sent) == 1, vim.sent
    assert vim.sent[0][0] == '--remote-send', vim.sent


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
