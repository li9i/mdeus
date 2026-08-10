"""
The little a reading remembers between one opening and the next.

The theme, whether the contents list was open, whether a theme that will run its
lines the full width of the pane is left to, and where the divider between the
browser and vim was left. One file holds all four, and each thing that stores
into it writes only its own field, since a reading in a browser and a reading
with vim beside it know nothing of each other's settings.

This is kept apart from the server that serves a reading and from the window
that holds one, because both of them read it and neither is the other's
business.
"""

import json
import uuid
from pathlib import Path

# The share of the window the browser pane takes in a reading with vim beside
# it, before the divider between them has ever been dragged. It matches the
# split the same document read in a terminal already uses.
DEFAULT_SPLIT = 0.44
# How far the divider may be dragged either way. Far enough to read in either
# pane alone, and never so far that the other one has nothing left to draw in.
MAX_SPLIT = 0.85
MIN_SPLIT = 0.15
STATE_PATH = Path.home() / '.config' / 'mdview' / 'state.json'
THEMES = ('browser', 'report', 'github')


def load_split():
    """Return the share of the window the browser pane takes.

    A share the divider could not have left behind, whether it is missing,
    unreadable or outside what can be dragged to, means the reading opens at
    the split the very first one did.
    """
    try:
        share = float(stored_state()['split'])
    except (KeyError, TypeError, ValueError):
        return DEFAULT_SPLIT
    return share if MIN_SPLIT <= share <= MAX_SPLIT else DEFAULT_SPLIT


def load_state():
    """Return the stored page settings, or the ones a first reading gets.

    A missing, unreadable or malformed file is not an error, and neither is a
    theme naming something that does not exist. Any of them means the reading
    opens the way the very first one did.

    A file written before the full width setting existed has no field for it,
    and reads as the setting being on, since that is how a first reading opens.
    """
    stored = stored_state()
    if stored.get('theme') in THEMES:
        return {
            'contents': bool(stored.get('contents')),
            'theme': stored['theme'],
            'wide': bool(stored.get('wide', True)),
        }
    return {'contents': False, 'theme': 'browser', 'wide': True}


def save_split(share):
    """Store where the divider was left, for the next reading to open at."""
    save_state({'split': round(share, 4)})


def save_state(state):
    """Write the state file atomically, so a reading never reads half a file.

    What is written is merged into what is already there. Two things store into
    this file and neither knows the other's field: the page stores the theme,
    the contents setting and the full width setting, and a reading with vim
    beside it stores where the divider was left.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own for every write, beside the target so the rename stays
    # on one filesystem. Several readings may run at once, and one fixed
    # temporary name would let two of them fill the same file and each rename
    # the other's content into place.
    temp = STATE_PATH.with_name(f'{STATE_PATH.name}.{uuid.uuid4().hex}.tmp')
    merged = dict(stored_state(), **state)
    temp.write_text(json.dumps(merged, indent=2) + '\n', encoding='utf-8')
    temp.replace(STATE_PATH)


def stored_state():
    """Return what the state file holds, or nothing where it holds nothing usable."""
    try:
        stored = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}
