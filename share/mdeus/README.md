# mdview

Two commands for reading a markdown document in a browser.

`bmv <document.md>` serves the document to your default browser, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. Several readings run at once, each on its own port. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt.

`bmv --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

`bmvim <document.md>` is the same reading with vim beside it, in one window. The browser takes the left of that window and a terminal running vim takes the right, 44 percent against 56 until you drag the seam between them somewhere else. Clicking a block sends vim to the line that block came from, centred in the window and lit end to end for a moment, and clicking in vim brings the page the other way, to the block the pointer landed in. Moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. Space in vim folds the section the cursor is in and opens it again, section for section with the page. The two halves fold on their own and neither follows the other. The reading opens a terminal of its own, so the shell `bmvim` was run from stays yours and waits. Only one `bmvim` reading runs at a time, and it needs a desktop session.

The page carries a dropdown of three themes and a `Contents` button, which is there only once the document has three or more headings. Those two, and where the seam between the panes was last dragged to, are kept in `~/.config/mdview/state.json`, so a reading opens the way the last one was left. Every fence carries a `Copy` button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard. A double click on a top level heading folds its section away and another brings it back, and a heading with a section behind it carries three dots. Nothing below the top level folds, and a fold lasts as long as the document is on the screen rather than being written down anywhere.

The ground a jump lights in vim is the `BmvimJump` highlight group. It is set as a default, so a `.vimrc` naming it wins.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from. Also the heading outline, the images the document points at, and its links to other markdown documents. |
| `server.py` | Serves one reading: the page, the document, assets and links from inside the starting tree, and the routes vim talks to. |
| `export.py` | The self contained file `bmv --print` writes. |
| `vimlink.py` | The link to vim: the servername, jumps, following a link on both sides, and the cursor line coming back. |
| `container.py` | The one window a reading with vim is drawn in, the browser and terminal inside it, and the seam between the two. |
| `themes.css` | The three themes, the two controls and the copy button on a fence. |
| `page.js` | The theme dropdown, the contents list, the copy button on every fence, the heading names, the sections a double click folds away, and the redraw. |
| `bmvim.css`, `bmvim.js` | The two marks and the sync. `bmv` never loads either. |
| `test_render.py`, `test_server.py` | The tests. |

The commands themselves are `bmv` and `bmvim`, and they live in `~/.local/bin`.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. So anything writing `document.documentElement.className` has to write the marker with it, and `applyTheme()` in `page.js` is the one place that does. A printed copy carries the marker too, so `bmv --print` reads at the same size as a served reading.

## What it needs

`python3-markdown-it` for the parser, and `python3-xlib` for the one window a `bmvim` reading is drawn in. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and both commands serve on `127.0.0.1` and nowhere else.

`bmvim` also wants Chrome or Chromium, `mate-terminal`, and a vim built with `+clientserver`. The vim half of `bmvim` is `vim --servername`, and Ubuntu's plain `vim` package is built without `+clientserver`, so it cannot be reached that way at all. `vim-gtk3` has it, and that is what `install.sh` installs. `vim --version | grep clientserver` says which one is on the machine.

The two desktop entries call `bmv` and `bmvim` by name, so `~/.local/bin` has to be on the session path for them to resolve. Ubuntu's stock `~/.profile` puts it there at login when the directory exists, and `install.sh` creates it before the log out it already asks for.

## Tests

```bash
python3 test_render.py
python3 test_server.py
```

Plain asserts in functions named `test_*`, no framework. They cover the renderer, the server and the printed copy. The browser, the windows and vim have no automated cover at all, which is what the list below is for.

## The manual check

Run all of it after touching anything to do with the browser, the windows or vim. Each item says what to do and what should happen.

### The one window

1. `bmvim doc.md` from a terminal. One window on the desktop and one entry on the panel, both reading `bmvim`. The browser takes the left of that window and the terminal the right, and the two meet without a gap and without overlapping. The window fills the work area, so nothing in the reading sits under a panel. It comes up white and stays white: a browser takes a moment to start, and nothing black is shown while it does. Neither half stands on the desktop as a window of its own on the way in, whichever of the two is up first, and the browser is commonly seconds behind the terminal.
2. The browser pane has no address bar, no tabs and no bookmarks, and the terminal pane has no menu bar. Neither pane has a title bar or a close button of its own. The window has one of each for the pair.
3. The shell you typed the command into stays yours. It says where the reading is and then waits, and the vim you are reading with is in a terminal the reading opened for itself.
4. Click the browser pane, then the terminal pane, then the browser again. The pane you clicked last takes the keyboard every time, so typing goes to the pane you are looking at. Click the title bar instead and the keyboard stays where it was.
5. Leave the reading on the screen, click into a window of another program beside it, and type there for a while. What you type goes to that window and goes on going there, and the reading never takes the keyboard back from it. Scroll and click about in vim first, so that both panes have had the keyboard, and check the same again. A reading takes the keyboard only for its own panes, and only while it is the window the desktop has in front.
6. Unmaximise the window and resize it, larger and smaller. The two panes keep their proportion and go on meeting exactly at every size. A band of the window is left showing below the terminal, up to one character row deep and white like the panes beside it. That is the terminal rounding its height to whole rows, and inside a window there is no desktop left to maximise it against, so the band stays.
7. `bmvim doc.md` again from the file manager, through the `bmvim` entry in the "Open With" menu. The same one window opens, and no spare terminal is opened beside it.

### The divider

8. Put the pointer on the join between the two panes. It becomes an arrow pointing both ways, which is the whole of what says the join can be moved. Take the pointer a few pixels off the join and the arrow goes again.
9. Drag the join left and right. Both panes follow the pointer and go on meeting exactly at every moment of the drag, and the seam lands on a whole character column of the terminal rather than exactly where you let go.
10. Drag as far as it will go each way. It stops while there is still a pane worth reading in on both sides, at 15 percent of the window one way and 85 percent the other.
11. Drag the join somewhere else, quit, and start another reading. It opens where you left it. Change the theme in the page as well, and neither setting has put the other out of `~/.config/mdview/state.json`.

### The three way sync

12. Click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand.
13. The block vim landed on sits in the middle of the terminal, and the whole of it carries a pale blue ground, first line to last. Click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
14. Click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
15. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
16. Click in the vim pane. The page comes to the block the pointer landed in and puts it a quarter of the way down the window, wherever the page was left and however near or far that block is, and the rule moves onto it with it. Click again inside the same block and the page stays where the first click put it.
17. Edit inside one block, moving the cursor about within it. The page does not scroll. It never scrolls to a block already in front of you either, wherever the cursor came from.
18. Scroll in vim rather than moving through it: the wheel, `ctrl-d`, `ctrl-f`. vim moves the cursor once it would leave the window, so the mark moves with it and the page stays where it is. Then jump a long way, with a search or a `G` or a `:42`, and the page comes along. The line between the two is one window height of the page, measured from the block the mark was on to the block it is going to, so anything landing nearer than that leaves the page alone. A cursor line arriving with no mark to measure from brings the page along, which is the first line of a reading and the first after a link is followed.
19. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
20. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. A clicked block flashes a light grey ground that fades after a second.
21. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
22. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file. The browser's back button returns. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone.

### The folds

23. Open a document with two or more top level headings and press space in vim, first on a heading and then on a line inside the section under it. Both fold the whole section away, from the heading to the line before the next one, and pressing space again brings it back. A heading below the top level does not fold on its own and goes with the section holding it.
24. Follow a link to another document in the page, then press space there. It folds the same way, on a file vim opened after the reading started.
25. Double click a top level heading in the page. Its section goes and the heading is left with three dots after it. Double click again and it comes back. The first of the two clicks is still a click, so in a reading with vim beside it vim goes to that heading on the way.
26. Fold a section in the page and write the file in vim. The page redraws and the section is still folded, with anything added to it folded away with it. Fold one and follow a link instead, and the document that opens has every section open.
27. Fold a section in the page and move the vim cursor into it. The rule goes on the heading of the folded section, since that is all the page is showing of it, and the page does not jump. The two halves are otherwise nothing to do with each other: a section folded in vim is open in the page, and one folded in the page is open in vim.

### Ending a reading

28. Quit vim. The whole window goes and the server stops.
29. Close the browser pane instead, with `ctrl-w` in it. vim is asked to quit, which it refuses while anything in it is unwritten, and the reading ends as soon as vim goes.
30. Press the window's close button, and separately press `ctrl-c` in the shell the command was run from. Both ask the same question the browser pane closing asks, and both are refused the same way while anything in vim is unwritten. Nothing is ever taken away from under unsaved work.
31. Kill the terminal outright, with `pkill -f 'mate-terminal --disable-factory'`. The window goes and the server stops, the same as quitting vim.
32. After every one of the four: the temporary browser profile is gone, no server is left behind, and no terminal or browser is left running. `pgrep -af mdview/server.py` should say nothing.

### The three themes

33. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Mono headings` and `GitHub`.
34. The first two are black on white, and only `Browser default` has any colour at all, on its links. `GitHub` is the exception and keeps GitHub's own palette.
35. Every theme caps the measure, so a maximised window does not throw lines across the whole screen. Code blocks scroll inside their own box rather than widening the page.
36. Changing the theme does not reload the page and does not lose your place in it.
37. Both `bmvim` marks work in all three. Each theme leaves the margin rule its own offset, so check that the rule stands clear of the text in every one of them.

### The copy button

38. Hover a fence in each of the three themes. A `Copy` button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover.
39. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
40. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again.
41. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
42. In a `bmvim` reading, press a copy button. It copies and vim does not move. Click the fence beside it and vim moves as it always did.
43. `bmv --print doc.md`, then open the file it names over `file://`. The buttons work there too. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

44. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib/__init__.py` that raises `ImportError`, then start a reading. There is no window to make one out of, so the browser and the terminal open as two ordinary windows wherever the desktop puts them. It says so in one line and the reading works, sync and endings and all.
45. Neither Chrome nor Chromium on the machine. Take both off `PATH` and start a reading. The page opens in a plain tab of the default browser, both lines of the message are printed saying the window is neither placed nor closed for you, and the reading works.
46. No `DISPLAY`. `env -u DISPLAY bmvim doc.md` says `bmvim` needs a desktop session and suggests `bmv`, and exits 1.
47. The servername already taken. Start one reading, then start a second. The second names the document the first has open and exits 1.
48. The server killed mid-reading. `pkill -f mdview/server.py` while a reading is up. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.

### bmv on its own

49. Several `bmv` readings at once, on different documents. Each prints its own address on its own port and each redraws its own file.
50. No browser reachable. `env -u DISPLAY -u BROWSER bmv doc.md`. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
51. `bmv --print doc.md` on a document with an image in it. Open the file it names, move it somewhere else and open it again. It renders the same, and the theme dropdown works and stores nothing.
52. Close the page in the browser rather than pressing ctrl-c. Within about ten seconds the command ends by itself and the shell comes back. Nothing else may be speaking to that port while you check: a page left open from an earlier reading goes on saying it is there, and a reading is kept up by any page that does.

## Three things that look odd and are not

vim is started with `set notitle`, after the vimrc rather than before it. Left on, vim writes the name of the file onto the terminal every time the document changes, and the terminal passes it on to the window it is inside, so the window the reading named `bmvim` would be renamed within the second.

Chrome is given `--no-first-run`. A profile that has never been used greets you on the way in, and every reading makes a fresh one, so without the flag the welcome window arrives instead of the document.

The two panes are taken off the window manager before they are put in the window, by unmapping each one and telling the root window it is withdrawn. Reparenting a window the manager is still managing does not work: the manager reads its client leaving the frame as the window having gone, and the tidying up it does for a window that has gone hands the client back to the root. The withdrawal is what makes the manager let go first, and everything the reading does with its panes afterwards rests on it.
