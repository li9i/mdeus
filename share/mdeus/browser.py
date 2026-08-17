"""
The browser a reading opens its page in.

Both commands want a window with nothing in it but the page, and both want it
out of the browser you already have running, which is what makes a reading open
as quickly as it does. A browser built on Chromium is one that can be asked for
such a window, and asked in the same words whichever it is, so the list below is
those browsers under the names their packages install them as: Chrome, Chromium,
Brave, Vivaldi and Edge. Firefox and the rest have no way of being asked for a
bare window at all, so they are read here as no browser. Opera is built on
Chromium and is left off all the same, since it is reported to answer the asking
with an ordinary window: an address bar over the page would be the smaller half
of it, the larger being a window named after the browser rather than after the
address, which is the one name an editing session has to find its page by. So
the list is the browsers that leave Chromium's own handling of windows where it
is, and a tab, which is asked for in an altogether different way and works, is
the better answer for any browser that does not.

The first name on the list that is on the machine is the one asked, and Chrome
and Chromium lead it, so a machine carrying more than one opens its readings
where it always did. Where none of them is on the machine the page goes to an
ordinary tab of whatever browser is set as the default, and the reading is no
different for it beyond what the tab is wrapped in.
"""

import shutil

BROWSERS = (
    'google-chrome',
    'google-chrome-stable',
    'chromium',
    'chromium-browser',
    'brave-browser',
    'brave',
    'vivaldi',
    'vivaldi-stable',
    'microsoft-edge',
    'microsoft-edge-stable',
)


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
