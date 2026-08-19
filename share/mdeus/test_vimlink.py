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

    Asked what it has unwritten it answers the count it was made with, and a
    stand in with a question up answers nothing at all, which is what a vim
    holding a prompt does and what one that has gone does. Everything else is
    remembered rather than sent, which is how a test sees what reached a vim
    that should have been left alone.
    """

    def __init__(self, mode='n', answer='', unwritten='0'):
        self.answer = answer
        self.asked = []
        self.mode = mode
        self.sent = []
        self.unwritten = unwritten

    def __call__(self, servername, *args):
        """Answer the questions a vim answers, and remember everything said to it.

        A vim with a question up answers neither what it has unwritten nor a
        tick, the second because the tick is a function of its own that can see
        the state it is in. Every question is remembered as well as answered,
        because what one costs is the reason for asking as seldom as the link
        does.
        """
        if args[:2] == ('--remote-expr', vimlink.UNWRITTEN):
            self.asked.append(args)
            return None if self.waiting() else self.unwritten
        if args[0] == '--remote-expr' and args[1].startswith('MdeusTick('):
            self.asked.append(args)
            return '0' if self.waiting() else self.answer
        self.sent.append(args)
        return self.answer

    def waiting(self):
        """Say whether this vim has a question up and so hears nothing."""
        return bool(self.mode) and self.mode.startswith('r')


def spoken_to(vim, what):
    """Run one call against a stand in for vim, and return what it answered."""
    was = vimlink.remote
    vimlink.remote = vim
    try:
        return what()
    finally:
        vimlink.remote = was


def test_a_tick_names_the_line_and_the_document_it_belongs_to():
    """A tick tells vim which line, what it is to become, and which document.

    The document goes with it because vim answers no where it has another file
    open, so a reader who took vim off somewhere else cannot have a line of that
    file rewritten from a page that is not showing it. Whether the line was a
    task list item at all is vim's to say, since the buffer is the document as it
    stands while the file is the document as it was last saved.
    """
    vim = Vim(answer='1')
    landed = spoken_to(vim, lambda: vimlink.tick(SERVERNAME, 3, True, "/tmp/it's.md"))
    assert landed is True, landed
    assert vim.asked == [('--remote-expr', "MdeusTick(3, 1, '/tmp/it''s.md')")], vim.asked
    refused = Vim(answer='0')
    landed = spoken_to(refused, lambda: vimlink.tick(SERVERNAME, 8, False, '/tmp/a.md'))
    assert landed is False, landed
    assert refused.asked == [('--remote-expr', "MdeusTick(8, 0, '/tmp/a.md')")], (
        refused.asked
    )


def test_a_vim_that_answers_nothing_is_told_nothing():
    """A vim that is not there is not told to go, and the telling says so.

    The client answers nothing where there is no vim of that name, which is the
    same answer it gives for one held up in something that will not talk. Both
    say the word did not leave, so that whoever wanted vim to go says it again.
    """
    vim = Vim(None, answer=None)
    landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
    assert landed is False, landed


def test_a_vim_waiting_to_be_answered_is_told_and_says_nothing_of_its_work():
    """Telling vim to go is not a question, so the telling goes out either way.

    A vim with a question up is answering whoever is reading and nothing else.
    Keys sent to it then are neither acted on nor taken as the answer: they are
    dropped, and the sending looks exactly as it does for a vim that acted on
    them. So the word goes out first, since it costs a moment and the reader is
    waiting on it, and what vim has unwritten is a separate question asked
    afterwards by whoever minds.

    Such a vim answers that question with nothing, which is neither work to be
    kept nor an empty vim to be taken away, and whoever asked is left to say the
    word again.

    All three of the states vim waits to be answered in are read the same way:
    the hit enter prompt, the more prompt, and a question with choices in it.
    """
    for mode in ('r', 'rm', 'r?'):
        vim = Vim(mode, unwritten='1')
        landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
        assert landed is True, (mode, landed)
        assert vim.sent[0][0] == '--remote-send', (mode, vim.sent)
        assert spoken_to(vim, lambda: vimlink.unwritten(SERVERNAME)) is None, mode


def test_a_vim_holding_unwritten_work_says_so_and_an_empty_one_says_that():
    """The one question a session asks vim has three answers, and all three matter.

    A vim with something unwritten in it has heard the word to go and is
    refusing on the work, and is left alone until the reader saves. A vim with
    nothing unwritten has not heard it, since it would have gone, and is told
    again. A vim that answers nothing says only that it cannot be seen, and
    nothing is taken away on that.
    """
    holding = Vim(unwritten='2')
    assert spoken_to(holding, lambda: vimlink.unwritten(SERVERNAME)) is True
    assert holding.asked == [('--remote-expr', vimlink.UNWRITTEN)], holding.asked
    empty = Vim()
    assert spoken_to(empty, lambda: vimlink.unwritten(SERVERNAME)) is False
    gone = Vim(None, unwritten=None)
    assert spoken_to(gone, lambda: vimlink.unwritten(SERVERNAME)) is None


def test_a_vim_waiting_to_be_answered_is_not_ticked():
    """A vim with a question up refuses a tick, and the refusal reaches the page.

    A vim answering whoever is reading is in no state to have a line of the
    document rewritten under it, and it can see that about itself, so it is the
    one asked rather than being tested for first and then asked. One question
    where there were two, and the same answer.

    What the page does with the refusal is put its own box back, rather than be
    left showing one the document does not carry.
    """
    for mode in ('r', 'rm', 'r?'):
        vim = Vim(mode, answer='1')
        landed = spoken_to(vim, lambda: vimlink.tick(SERVERNAME, 3, True, '/tmp/a.md'))
        assert landed is False, (mode, landed)
        assert len(vim.asked) == 1, (mode, vim.asked)
        assert vim.sent == [], (mode, vim.sent)


def test_a_vim_with_nothing_up_is_told_to_go_and_asked_nothing():
    """Telling vim to go asks vim nothing, since a question is what costs the time.

    The word is one call and no more. A session that wanted to know whether vim
    had it asks afterwards, and only where the answer changes anything.
    """
    vim = Vim()
    landed = spoken_to(vim, lambda: vimlink.quit_vim(SERVERNAME))
    assert landed is True, landed
    assert vim.asked == [], vim.asked
    assert len(vim.sent) == 1, vim.sent
    assert vim.sent[0][0] == '--remote-send', vim.sent


def test_a_write_the_reading_makes_itself_is_claimed_and_given_back():
    """vim is told which change is the reading's own, and told when it is not coming.

    A vim holding the document asks whether to load a file written under it, and
    a box pressed while the page is alone is the reading writing that file. The
    claim is what keeps that press from leaving a question standing in a pane
    nobody is looking at. A claim nothing was written against is given back,
    since the next write is as likely to be somebody else's.
    """
    vim = Vim()
    spoken_to(vim, lambda: vimlink.mine(SERVERNAME, True))
    assert vim.sent == [
        ('--remote-send', f'{vimlink.NORMAL_MODE}:call MdeusMine(1)<CR>')
    ], vim.sent
    given_back = Vim()
    spoken_to(given_back, lambda: vimlink.mine(SERVERNAME, False))
    assert given_back.sent == [
        ('--remote-send', f'{vimlink.NORMAL_MODE}:call MdeusMine(0)<CR>')
    ], given_back.sent
    assert vim.asked == [] and given_back.asked == [], (vim.asked, given_back.asked)


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
