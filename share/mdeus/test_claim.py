"""
Behaviour tests for claim.py. Run with: python3 test_claim.py

No window is made and no browser is opened. A reading holding a document is
stood in for by a process that does nothing but hold the claim, and the one
test that runs the command runs it without a desktop, so the reading it finds
has no window to bring forward and the command only says what it found.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import claim

COMMAND = Path(__file__).resolve().parents[2] / 'bin' / 'mdeus'
ENDS_WITHIN = 5
HERE = Path(__file__).resolve().parent
HOLDER = """\
import sys
from pathlib import Path

import claim

held = claim.claim(Path(sys.argv[1]))
print('held', flush=True)
sys.stdin.read()
"""


@contextmanager
def a_document():
    """Give a document in a tree of its own, and take the tree away after."""
    tree = Path(tempfile.mkdtemp(prefix='mdeus-test-claim-'))
    document = tree / 'notes.md'
    document.write_text('# Notes\n', encoding='utf-8')
    try:
        yield document
    finally:
        shutil.rmtree(tree, ignore_errors=True)


@contextmanager
def held_elsewhere(document):
    """Hold a document's claim in a process of its own while the block runs."""
    holding = subprocess.Popen(
        [sys.executable, '-c', HOLDER, str(document)],
        cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        holding.stdout.readline()
        yield holding
    finally:
        holding.kill()
        holding.wait()
        holding.stdin.close()
        holding.stdout.close()


def test_a_claim_goes_with_a_reading_that_was_killed():
    """A reading killed outright leaves its document free to be opened again.

    A reading that crashed or was killed has no chance to give anything back,
    and a claim that outlived it would refuse the document for good.
    """
    with a_document() as document:
        with held_elsewhere(document) as holding:
            holding.kill()
            holding.wait()
            again = claim.claim(document)
            assert again is not None, 'a killed reading kept its document'
            again.close()


def test_a_document_already_claimed_is_refused():
    """A document claimed by one reading cannot be claimed by a second."""
    with a_document() as document:
        first = claim.claim(document)
        try:
            assert first is not None, 'a free document was refused'
            again = claim.claim(document)
            assert again is None, 'one document was claimed twice'
        finally:
            first.close()


def test_a_document_already_open_is_not_opened_again():
    """The command run on a document already open ends at once, and says so.

    No desktop is given to it, so there is no window to bring forward and no
    browser to open one, and a command that read the document a second time
    would serve it until it was killed.
    """
    with a_document() as document:
        env = dict(os.environ, HOME=str(document.parent))
        env.pop('DISPLAY', None)
        env.pop('BROWSER', None)
        held = claim.claim(document)
        try:
            second = subprocess.Popen(
                [sys.executable, str(COMMAND), str(document)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            try:
                out, err = second.communicate(timeout=ENDS_WITHIN)
            except subprocess.TimeoutExpired:
                second.kill()
                out, err = second.communicate()
        finally:
            held.close()
        assert second.returncode == 0, (second.returncode, out, err)
        assert 'notes.md is already open' in out, out
        assert 'reading notes.md' not in out, out
        assert err == '', err


def test_a_document_named_another_way_is_the_same_document():
    """A document reached by another path is still the document claimed.

    A relative path and a link to the file both name the file itself, so
    neither opens a second reading of it.
    """
    with a_document() as document:
        link = document.parent / 'link.md'
        link.symlink_to(document)
        relative = Path(os.path.relpath(document))
        first = claim.claim(document)
        try:
            assert claim.claim(link) is None, 'a link opened a second reading'
            assert claim.claim(relative) is None, 'a relative path did'
        finally:
            first.close()


def test_another_document_is_left_free():
    """A claim on one document leaves every other document free."""
    with a_document() as document, a_document() as other:
        first = claim.claim(document)
        try:
            second = claim.claim(other)
            assert second is not None, 'another document was refused'
            second.close()
        finally:
            first.close()


def test_the_holder_is_the_process_holding_the_claim():
    """A second reading learns which process holds the document it wanted."""
    with a_document() as document:
        with held_elsewhere(document) as holding:
            found = claim.holder(document)
            assert found == holding.pid, (found, holding.pid)


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
