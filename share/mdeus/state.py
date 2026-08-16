"""
The little a reading remembers between one opening and the next.

Settings belong to the document they were set on. One file holds them for every
document that has any, each under its own path: the theme, whether the contents
list was open, whether a theme that will run its lines the full width of the
pane is left to, whether a theme that will stand its lines in the middle of the
pane is left to, and where the divider between the browser and vim was left. A
document nothing was ever set on opens the way the very first reading did, so
what one document is left in never reaches another.

Each thing that stores into the file writes only its own fields of its own
document, since a reading in a browser and a reading with vim beside it know
nothing of each other's settings.

This is kept apart from the server that serves a reading and from the window
that holds one, because both of them read it and neither is the other's
business.
"""

import json
import uuid
from pathlib import Path

DEFAULT_SPLIT = 0.44
MAX_SPLIT = 0.85
MIN_SPLIT = 0.15
STATE_PATH = Path.home() / '.config' / 'mdeus' / 'state.json'
THEMES = ('browser', 'report', 'github')


def document_state(document):
    """Return what the file holds for one document, or nothing usable.

    A file written before settings were kept per document has its fields at the
    top rather than under any name, and holds nothing for any document. Those
    fields belong to no document that can be named now, so they are read as
    nothing at all.
    """
    stored = stored_documents().get(str(document))
    return stored if isinstance(stored, dict) else {}


def load_split(document):
    """Return the share of the window the browser pane takes for one document.

    A share the divider could not have left behind, whether it is missing,
    unreadable or outside what can be dragged to, means the reading opens at
    the split the very first one did.
    """
    try:
        share = float(document_state(document)['split'])
    except (KeyError, TypeError, ValueError):
        return DEFAULT_SPLIT
    return share if MIN_SPLIT <= share <= MAX_SPLIT else DEFAULT_SPLIT


def load_state(document):
    """Return one document's stored page settings, or the ones a first reading gets.

    A missing, unreadable or malformed file is not an error, and neither is a
    theme naming something that does not exist, and neither is a document the
    file holds nothing for. Any of them means the reading opens the way the very
    first one did.

    A document stored before the full width setting or the centring setting
    existed has no field for either, and both read as being off, since that is
    how a first reading opens.
    """
    stored = document_state(document)
    if stored.get('theme') in THEMES:
        return {
            'contents': bool(stored.get('contents')),
            'middle': bool(stored.get('middle')),
            'theme': stored['theme'],
            'wide': bool(stored.get('wide')),
        }
    return {'contents': False, 'middle': False, 'theme': 'browser', 'wide': False}


def save_split(document, share):
    """Store where a document's divider was left, for its next reading to open at."""
    save_state(document, {'split': round(share, 4)})


def save_state(document, state):
    """Write the state file atomically, so a reading never reads half a file.

    What is written is merged into what is already there for that document, and
    every other document is left exactly as it was. Two things store into this
    file and neither knows the other's field: the page stores the theme, the
    contents setting, the full width setting and the centring setting, and a
    reading with vim beside it stores where the divider was left.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_name(f'{STATE_PATH.name}.{uuid.uuid4().hex}.tmp')
    documents = dict(stored_documents())
    documents[str(document)] = dict(document_state(document), **state)
    temp.write_text(
        json.dumps({'documents': documents}, indent=2) + '\n', encoding='utf-8'
    )
    temp.replace(STATE_PATH)


def stored_documents():
    """Return what the state file holds for every document it names."""
    documents = stored_state().get('documents')
    return documents if isinstance(documents, dict) else {}


def stored_state():
    """Return what the state file holds, or nothing where it holds nothing usable."""
    try:
        stored = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}
