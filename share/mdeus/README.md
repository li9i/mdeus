# mdview

Two commands for reading a markdown document in a browser.

`bmv <document.md>` serves the document to your default browser, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. Several readings run at once, each on its own port. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt.

`bmv --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

`cvim <document.md>` is the same reading with vim beside it. The browser takes the left 44 percent of the screen and a terminal running vim takes the right. Clicking a block sends vim to the line that block came from, centred in the window and lit end to end for a moment, moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. Only one `cvim` reading runs at a time, and it needs a desktop session.

The page carries a dropdown of five themes and a `Contents` button, which is there only once the document has three or more headings. The choice is stored in `~/.config/mdview/state.json` and is the same in every reading. Every fence carries a `Copy` button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from. Also the heading outline, the images the document points at, and its links to other markdown documents. |
| `server.py` | Serves one reading: the page, the document, assets and links from inside the starting tree, and the routes vim talks to. |
| `export.py` | The self contained file `bmv --print` writes. |
| `vimlink.py` | Everything a reading with vim needs that is not the serving: the servername, jumps, window placement and the panel entry. |
| `themes.css` | The five themes, the two controls and the copy button on a fence. |
| `page.js` | The theme dropdown, the contents list, the copy button on every fence, the heading names, and the redraw. |
| `cvim.css`, `cvim.js` | The two marks and the sync. `bmv` never loads either. |
| `test_render.py`, `test_server.py` | The tests. |

The commands themselves are `bmv` and `cvim`, and they live in `~/.local/bin`.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. So anything writing `document.documentElement.className` has to write the marker with it, and `applyTheme()` in `page.js` is the one place that does. A printed copy carries the marker too, so `bmv --print` reads at the same size as a served reading.

## What it needs

`python3-markdown-it` for the parser, and `xdotool` with `python3-xlib` for placing the two windows and lending the reading the terminal's panel entry. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and both commands serve on `127.0.0.1` and nowhere else.

`cvim` also wants Chrome or Chromium, a vim built with `+clientserver`, and `mate-terminal` when it is started from the file manager. The vim half of `cvim` is `vim --servername`, and Ubuntu's plain `vim` package is built without `+clientserver`, so it cannot be reached that way at all. `vim-gtk3` has it, and that is what `install.sh` installs. `vim --version | grep clientserver` says which one is on the machine.

The two desktop entries call `bmv` and `cvim` by name, so `~/.local/bin` has to be on the session path for them to resolve. Ubuntu's stock `~/.profile` puts it there at login when the directory exists, and `install.sh` creates it before the log out it already asks for.

## Tests

```bash
python3 test_render.py
python3 test_server.py
```

Plain asserts in functions named `test_*`, no framework. They cover the renderer, the server and the printed copy. The browser, the windows and vim have no automated cover at all, which is what the list below is for.

## The manual check

Run all of it after touching anything to do with the browser, the windows or vim. Each item says what to do and what should happen.

### The two windows

1. `cvim doc.md` from a terminal. The browser takes the left of the screen and the terminal the right, 44 percent against 56. Neither sits under a panel, and the two meet without a gap and without overlapping. Both reach the top of the work area and the bottom of it, with no strip of desktop above either.
2. The browser window has no address bar, no tabs and no bookmarks. It is a Chrome `--app` window on a profile of its own.
3. The terminal's entry in the MATE window list reads `cvim` for as long as the reading lasts, and goes back to the terminal's own name when it ends.
4. `cvim doc.md` again from the file manager, through the `cvim` entry in the "Open With" menu. A terminal is opened for it and the same placement follows.

### The three way sync

5. Click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand.
6. The block vim landed on sits in the middle of the terminal, and the whole of it carries a pale blue ground, first line to last. Click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
7. Click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
8. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
9. Edit inside one block, moving the cursor about within it. The page does not scroll. It never scrolls to a block already in front of you either, wherever the cursor came from.
10. Scroll in vim rather than moving through it: the wheel, `ctrl-d`, `ctrl-f`. vim moves the cursor once it would leave the window, so the mark moves with it and the page stays where it is. Then jump a long way, with a search or a `G` or a `:42`, and the page comes along. The line between the two is one window height of the page, measured from the block the mark was on to the block it is going to, so anything landing nearer than that leaves the page alone. A cursor line arriving with no mark to measure from brings the page along, which is the first line of a reading and the first after a link is followed.
11. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
12. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. A clicked block flashes a light grey ground that fades after a second.
13. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
14. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file. The browser's back button returns. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone.

### Ending a reading

15. Quit vim. The server stops and the browser window closes.
16. Close the browser window instead. The server stops and vim is asked to quit, which it refuses while anything in it is unwritten.
17. Kill the terminal outright, with the window manager's close button or `kill`. The server stops and the browser window closes, the same as the other two.
18. After every one of the three: the panel entry is back to the terminal's own name, the temporary browser profile is gone, and no server is left behind. `pgrep -af mdview/server.py` should say nothing.

### The five themes

19. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Serif document`, `Man page`, `Mono headings` and `GitHub`.
20. The first four are black on white. Only `Browser default` has any colour and only on its links. `GitHub` is the exception and keeps GitHub's own palette.
21. Every theme caps the measure, so a maximised window does not throw lines across the whole screen. Code blocks scroll inside their own box rather than widening the page.
22. Changing the theme does not reload the page and does not lose your place in it.
23. Both `cvim` marks work in all five. `Man page` is the awkward one, since it indents every block, so check the margin rule there in particular.

### The copy button

24. Hover a fence in each of the five themes. A `Copy` button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover.
25. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
26. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again.
27. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
28. In a `cvim` reading, press a copy button. It copies and vim does not move. Click the fence beside it and vim moves as it always did.
29. `bmv --print doc.md`, then open the file it names over `file://`. The buttons work there too. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

30. `xdotool` missing, or a placement call that fails. Put a stub earlier on `PATH` that exits non zero, then start a reading. It says the windows are wherever the desktop put them, and carries on unplaced. Placement is a convenience, not the reading.
31. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib.py` that raises `ImportError`, then start a reading. The panel entry keeps the terminal's own name and nothing is said about it, which is how a reading in a terminal has always behaved. Placement degrades in the same breath: without Xlib the borders the window manager draws cannot be read, so the two windows are placed by the rough measure of the whole screen and overlap by the width of those borders, and the terminal is not maximised for its height, so it falls short of the work area by part of a row.
32. Neither Chrome nor Chromium on the machine. Take both off `PATH` and start a reading. The page opens in a plain tab of the default browser, both lines of the message are printed saying the window is neither placed nor closed for you, and the reading works.
33. No `DISPLAY`. `env -u DISPLAY cvim doc.md` says `cvim` needs a desktop session and suggests `bmv`, and exits 1.
34. The servername already taken. Start one reading, then start a second. The second names the document the first has open and exits 1.
35. The server killed mid-reading. `pkill -f mdview/server.py` while a reading is up. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.

### bmv on its own

36. Several `bmv` readings at once, on different documents. Each prints its own address on its own port and each redraws its own file.
37. No browser reachable. `env -u DISPLAY -u BROWSER bmv doc.md`. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
38. `bmv --print doc.md` on a document with an image in it. Open the file it names, move it somewhere else and open it again. It renders the same, and the theme dropdown works and stores nothing.

## Two things that look odd and are not

vim is started with `set notitle`, after the vimrc rather than before it. Left on, vim writes the name of the file onto the terminal every time the document changes, and the panel entry the reading has just borrowed is written over within the second.

Chrome is given `--no-first-run`. A profile that has never been used greets you on the way in, and every reading makes a fresh one, so without the flag the welcome window arrives instead of the document.
