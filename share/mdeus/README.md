# mdview

Two commands for reading a markdown document in a browser.

`bmv <document.md>` serves the document to your default browser, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. Several readings run at once, each on its own port. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt.

`bmv --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

`cvim <document.md>` is the same reading with vim beside it, in one window. The browser takes the left 44 percent of that window and a terminal running vim takes the right. Clicking a block sends vim to the line that block came from, centred in the window and lit end to end for a moment, moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. The reading opens a terminal of its own, so the shell `cvim` was run from stays yours and waits. Only one `cvim` reading runs at a time, and it needs a desktop session.

The page carries a dropdown of five themes and a `Contents` button, which is there only once the document has three or more headings. The choice is stored in `~/.config/mdview/state.json` and is the same in every reading. Every fence carries a `Copy` button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from. Also the heading outline, the images the document points at, and its links to other markdown documents. |
| `server.py` | Serves one reading: the page, the document, assets and links from inside the starting tree, and the routes vim talks to. |
| `export.py` | The self contained file `bmv --print` writes. |
| `vimlink.py` | The link to vim: the servername, jumps, following a link on both sides, and the cursor line coming back. |
| `container.py` | The one window a reading with vim is drawn in, and the browser and terminal inside it. |
| `themes.css` | The five themes, the two controls and the copy button on a fence. |
| `page.js` | The theme dropdown, the contents list, the copy button on every fence, the heading names, and the redraw. |
| `cvim.css`, `cvim.js` | The two marks and the sync. `bmv` never loads either. |
| `test_render.py`, `test_server.py` | The tests. |

The commands themselves are `bmv` and `cvim`, and they live in `~/.local/bin`.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. So anything writing `document.documentElement.className` has to write the marker with it, and `applyTheme()` in `page.js` is the one place that does. A printed copy carries the marker too, so `bmv --print` reads at the same size as a served reading.

## What it needs

`python3-markdown-it` for the parser, and `python3-xlib` for the one window a `cvim` reading is drawn in. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and both commands serve on `127.0.0.1` and nowhere else.

`cvim` also wants Chrome or Chromium, `mate-terminal`, and a vim built with `+clientserver`. The vim half of `cvim` is `vim --servername`, and Ubuntu's plain `vim` package is built without `+clientserver`, so it cannot be reached that way at all. `vim-gtk3` has it, and that is what `install.sh` installs. `vim --version | grep clientserver` says which one is on the machine.

The two desktop entries call `bmv` and `cvim` by name, so `~/.local/bin` has to be on the session path for them to resolve. Ubuntu's stock `~/.profile` puts it there at login when the directory exists, and `install.sh` creates it before the log out it already asks for.

## Tests

```bash
python3 test_render.py
python3 test_server.py
```

Plain asserts in functions named `test_*`, no framework. They cover the renderer, the server and the printed copy. The browser, the windows and vim have no automated cover at all, which is what the list below is for.

## The manual check

Run all of it after touching anything to do with the browser, the windows or vim. Each item says what to do and what should happen.

### The one window

1. `cvim doc.md` from a terminal. One window on the desktop and one entry on the panel, both reading `cvim`. The browser takes the left of that window and the terminal the right, 44 percent against 56, and the two meet without a gap and without overlapping. The window fills the work area, so nothing in the reading sits under a panel.
2. The browser pane has no address bar, no tabs and no bookmarks, and the terminal pane has no menu bar. Neither pane has a title bar or a close button of its own. The window has one of each for the pair.
3. The shell you typed the command into stays yours. It says where the reading is and then waits, and the vim you are reading with is in a terminal the reading opened for itself.
4. Click the browser pane, then the terminal pane, then the browser again. The pane you clicked last takes the keyboard every time, so typing goes to the pane you are looking at. Click the title bar instead and the keyboard stays where it was.
5. Unmaximise the window and resize it, larger and smaller. The split stays at 44 against 56 and the two panes go on meeting exactly at every size. A band of the window is left showing below the terminal, up to one character row deep. That is the terminal rounding its height to whole rows, and inside a window there is no desktop left to maximise it against, so the band stays.
6. `cvim doc.md` again from the file manager, through the `cvim` entry in the "Open With" menu. The same one window opens, and no spare terminal is opened beside it.

### The three way sync

7. Click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand.
8. The block vim landed on sits in the middle of the terminal, and the whole of it carries a pale blue ground, first line to last. Click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
9. Click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
10. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
11. Edit inside one block, moving the cursor about within it. The page does not scroll. It never scrolls to a block already in front of you either, wherever the cursor came from.
12. Scroll in vim rather than moving through it: the wheel, `ctrl-d`, `ctrl-f`. vim moves the cursor once it would leave the window, so the mark moves with it and the page stays where it is. Then jump a long way, with a search or a `G` or a `:42`, and the page comes along. The line between the two is one window height of the page, measured from the block the mark was on to the block it is going to, so anything landing nearer than that leaves the page alone. A cursor line arriving with no mark to measure from brings the page along, which is the first line of a reading and the first after a link is followed.
13. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
14. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. A clicked block flashes a light grey ground that fades after a second.
15. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
16. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file. The browser's back button returns. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone.

### Ending a reading

17. Quit vim. The whole window goes and the server stops.
18. Close the browser pane instead, with `ctrl-w` in it. vim is asked to quit, which it refuses while anything in it is unwritten, and the reading ends as soon as vim goes.
19. Press the window's close button, and separately press `ctrl-c` in the shell the command was run from. Both ask the same question the browser pane closing asks, and both are refused the same way while anything in vim is unwritten. Nothing is ever taken away from under unsaved work.
20. Kill the terminal outright, with `pkill -f 'mate-terminal --disable-factory'`. The window goes and the server stops, the same as quitting vim.
21. After every one of the four: the temporary browser profile is gone, no server is left behind, and no terminal or browser is left running. `pgrep -af mdview/server.py` should say nothing.

### The five themes

22. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Serif document`, `Man page`, `Mono headings` and `GitHub`.
23. The first four are black on white. Only `Browser default` has any colour and only on its links. `GitHub` is the exception and keeps GitHub's own palette.
24. Every theme caps the measure, so a maximised window does not throw lines across the whole screen. Code blocks scroll inside their own box rather than widening the page.
25. Changing the theme does not reload the page and does not lose your place in it.
26. Both `cvim` marks work in all five. `Man page` is the awkward one, since it indents every block, so check the margin rule there in particular.

### The copy button

27. Hover a fence in each of the five themes. A `Copy` button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover.
28. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
29. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again.
30. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
31. In a `cvim` reading, press a copy button. It copies and vim does not move. Click the fence beside it and vim moves as it always did.
32. `bmv --print doc.md`, then open the file it names over `file://`. The buttons work there too. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

33. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib/__init__.py` that raises `ImportError`, then start a reading. There is no window to make one out of, so the browser and the terminal open as two ordinary windows wherever the desktop puts them. It says so in one line and the reading works, sync and endings and all.
34. Neither Chrome nor Chromium on the machine. Take both off `PATH` and start a reading. The page opens in a plain tab of the default browser, both lines of the message are printed saying the window is neither placed nor closed for you, and the reading works.
35. No `DISPLAY`. `env -u DISPLAY cvim doc.md` says `cvim` needs a desktop session and suggests `bmv`, and exits 1.
36. The servername already taken. Start one reading, then start a second. The second names the document the first has open and exits 1.
37. The server killed mid-reading. `pkill -f mdview/server.py` while a reading is up. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.

### bmv on its own

38. Several `bmv` readings at once, on different documents. Each prints its own address on its own port and each redraws its own file.
39. No browser reachable. `env -u DISPLAY -u BROWSER bmv doc.md`. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
40. `bmv --print doc.md` on a document with an image in it. Open the file it names, move it somewhere else and open it again. It renders the same, and the theme dropdown works and stores nothing.

## Three things that look odd and are not

vim is started with `set notitle`, after the vimrc rather than before it. Left on, vim writes the name of the file onto the terminal every time the document changes, and the terminal passes it on to the window it is inside, so the window the reading named `cvim` would be renamed within the second.

Chrome is given `--no-first-run`. A profile that has never been used greets you on the way in, and every reading makes a fresh one, so without the flag the welcome window arrives instead of the document.

The two panes are taken off the window manager before they are put in the window, by unmapping each one and telling the root window it is withdrawn. Reparenting a window the manager is still managing does not work: the manager reads its client leaving the frame as the window having gone, and the tidying up it does for a window that has gone hands the client back to the root. The withdrawal is what makes the manager let go first, and everything the reading does with its panes afterwards rests on it.
