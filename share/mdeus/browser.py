"""
The browser a reading opens its page in.

Both commands want a window with nothing in it but the page, and both want it
out of the browser you already have running, which is what makes a reading open
as quickly as it does. Chrome and Chromium are the two that can be asked for
such a window. Where neither is on the machine the page goes to an ordinary tab
of whatever browser is set as the default, and the reading is no different for
it beyond what the tab is wrapped in.
"""

import shutil

BROWSERS = ('google-chrome', 'chromium', 'chromium-browser')


def app_command(browser, url):
    """Return the command that asks for the page in a window of its own.

    --app gives a window carrying the page and nothing else: no address bar, no
    tabs, no bookmarks. The command that carries the asking is answered and gone
    within a moment, so what it leaves behind is a window rather than a process,
    and a browser of its own is started only where none was running, which is the
    one case where a reading opens as slowly as a browser starts.
    """
    return [browser, f'--app={url}']


def browser_path():
    """Return the browser a reading can own a window of, or nothing where there is none."""
    for candidate in BROWSERS:
        found = shutil.which(candidate)
        if found:
            return found
    return None
