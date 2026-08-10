# mdview

Two commands for reading a markdown document in a browser.

`bmv <document.md>` serves the document to your default browser, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. Several readings run at once, each on its own port. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt.

`bmv --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

`bmvim <document.md>` is the same reading with vim beside it, in one window. The browser takes the left of that window and gvim takes the right, 44 percent against 56 until you drag the seam between them somewhere else. One gesture works in both halves: double click a block in the page and vim goes to the line that block came from, centred in its window and lit end to end for a moment, and double click a line in vim and the page comes the other way, to the block the pointer landed in. Those two are the whole of what scrolls either half: the page marks the block the vim cursor is in but is never dragged about by it, so scrolling and typing in one window leave the other where its reader left it. A single click belongs to the half it happened in, so you can select a paragraph, follow a link or put the vim cursor somewhere without the other half moving at all. Moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. The reading opens a gvim of its own, so the shell `bmvim` was run from stays yours and waits. The page opens in the browser you already have running, which is what makes a reading open in well under a second, and the reading borrows that one window and leaves the rest of the browser alone: it takes the window into its own, asks it to close when the reading ends, and closing it by hand ends the reading. Where no browser is running the reading starts yours, and then it opens as slowly as a browser starts. Only one `bmvim` reading runs at a time, and it needs a desktop session.

The page carries a dropdown of three themes and a `Contents` button, which is there only once the document has three or more headings. Those two, and where the seam between the panes was last dragged to, are kept in `~/.config/mdview/state.json`, so a reading opens the way the last one was left. Every fence carries a copy button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard. Two of the themes say `Copy` on it and `GitHub` draws GitHub's own copy icon instead, which turns into a green tick once the fence is on the clipboard. Neither half folds a section away at the moment. Double click used to fold one in the page and space used to fold one in vim, and double click now belongs to the sync in both halves. The code behind the page's fold is still in `page.js` with nothing calling it, and vim is left with whatever folding your own `.vimrc` gives it.

The ground a jump lights in vim is the `BmvimJump` highlight group. It is set as a default, so a `.vimrc` naming it wins.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from, plus the heading outline. Where an image beside the document is written as is the caller's to say. |
| `server.py` | Serves one reading: the page, the document, files from inside the starting tree, and the routes vim talks to. Imported by whoever is serving, and run by nobody. |
| `state.py` | The one file a reading remembers itself in, read by the server and by the window alike. |
| `export.py` | The self contained file `bmv --print` writes. |
| `vimlink.py` | The link to vim: the servername, jumps, following a link on both sides, and the cursor line coming back. |
| `cursor.vim` | What vim does for as long as a reading is up: the cursor reports, the double click that brings the page over, and the ground a jump lights. |
| `bmvim_serve.py` | Runs the server for a `bmvim` reading and says which port it landed on, since the command that starts one is a shell script. `bmv` serves in process and needs no such thing. |
| `bmvim_window.py` | The one window a reading with vim is drawn in, the browser and gvim inside it, and the seam between the two. |
| `themes.css` | The three themes, the two controls and the copy button on a fence. |
| `page.js` | The theme dropdown, the contents list, the copy button on every fence, the heading names, the folding of a section, which nothing calls for the moment, and the redraw. |
| `bmvim.css`, `bmvim.js` | The two marks and the sync. `bmv` never loads either. |
| `test_render.py`, `test_server.py` | The tests. |

The commands themselves are `bmv` and `bmvim`, and they live in `~/.local/bin`.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. The server writes it once, when it sends the page, and a theme change in `page.js` turns the theme keys on and off one at a time rather than writing the whole class name over, so nothing else on the root is this page's to lose. A printed copy carries the marker too, so `bmv --print` reads at the same size as a served reading.

## What it needs

`python3-markdown-it` for the parser, and `python3-xlib` for the one window a `bmvim` reading is drawn in. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and both commands serve on `127.0.0.1` and nowhere else.

`bmvim` also wants Chrome or Chromium, and a vim built with `+clientserver` and a GUI. The vim half of `bmvim` is a `gvim --servername`, reached by `vim --servername` from the outside, and Ubuntu's plain `vim` package has neither the GUI nor `+clientserver`. `vim-gtk3` has both, and that is what `install.sh` installs. `vim --version | grep clientserver` says which one is on the machine.

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

1. `bmvim doc.md` from a terminal. One window on the desktop and one entry on the panel, both reading `bmvim`. The browser takes the left of that window and vim the right, and the two meet without a gap and without overlapping. The window fills the work area, so nothing in the reading sits under a panel. It comes up white and stays white: nothing black is shown while either half is on its way. Neither half stands on the desktop as a window of its own on the way in, whichever of the two is up first. Both are up within about two thirds of a second of the command, close enough together that the reading arrives whole rather than a half at a time. A reading opened where no browser was running is the one exception, and there the page follows the vim pane by a second or two. The vim pane fills its half from the first moment, top row to bottom, and the seam sits where the last reading left it rather than wherever vim first asked to be. Open several readings in a row and check that the seam lands in the same place every time.
2. The browser pane has no address bar, no tabs and no bookmarks, and the vim pane has no menu bar and no scrollbar. Neither pane has a title bar or a close button of its own. The window has one of each for the pair.
3. The shell you typed the command into stays yours. It says where the reading is and then waits, and the vim you are reading with is a gvim the reading opened for itself.
4. Click the browser pane, then the vim pane, then the browser again. The pane you clicked last takes the keyboard every time, so typing goes to the pane you are looking at. Click the title bar instead and the keyboard stays where it was.
5. Leave the reading on the screen, click into a window of another program beside it, and type there for a while. What you type goes to that window and goes on going there, and the reading never takes the keyboard back from it. Scroll and click about in vim first, so that both panes have had the keyboard, and check the same again. A reading takes the keyboard only for its own panes, and only while it is the window the desktop has in front.
6. Unmaximise the window and resize it, larger and smaller. The two panes keep their proportion and go on meeting exactly at every size. A band of the window may be left showing below vim, up to one character row deep and white like the panes beside it, since vim settles on whole rows however tall it is asked to be. The vim pane holds the whole document at every size, both while you resize and once you stop.
7. `bmvim doc.md` again from the file manager, through the `bmvim` entry in the "Open With" menu. The same one window opens, and no spare window is opened beside it.

### The divider

8. Put the pointer on the join between the two panes. It becomes an arrow pointing both ways, which is the whole of what says the join can be moved. Take the pointer a few pixels off the join and the arrow goes again.
9. Drag the join left and right. Both panes follow the pointer and go on meeting exactly at every moment of the drag, and the seam lands on a whole character column of vim rather than exactly where you let go.
10. Drag as far as it will go each way. It stops while there is still a pane worth reading in on both sides, at 15 percent of the window one way and 85 percent the other.
11. Drag the join somewhere else, quit, and start another reading. It opens where you left it. Change the theme in the page as well, and neither setting has put the other out of `~/.config/mdview/state.json`.

### The three way sync

12. Double click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand, and the word the two clicks took as a selection is dropped rather than left highlighted.
13. The block vim landed on sits in the middle of the vim pane, and the whole of it carries a pale blue ground, first line to last. Double click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
14. Double click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
15. A single click in the page never moves vim: click about, drag a selection across a paragraph, press a copy button. A single click in vim never moves the page either, wherever in the document you click.
16. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
17. Double click a line in the vim pane. The page comes to the block the pointer landed in and puts it a quarter of the way down the window, wherever the page was left and however near or far that block is, and the rule moves onto it with it. Double click again inside the same block and the page stays where the first one put it. vim selects no word on the way, and the cursor sits where you pointed.
18. Move about vim every way there is and watch the page: edit inside one block, step through the document a line at a time, scroll with the wheel and with `ctrl-d` and `ctrl-f`, jump with a search and a `G` and a `:42`, go to the end of a long document and come back. The mark follows the cursor throughout and the page never moves an inch of its own accord, wherever the cursor goes and whether the block it lands in is on the screen or nowhere near it.
19. Bring the page over to a cursor it has been left behind by: double click that line in vim. It comes at once, as item 17 says. That double click is the only thing on the vim side that scrolls the page.
20. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
21. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. The block you double clicked flashes a light grey ground that fades after a second.
22. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
23. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file. The browser's back button returns. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone. A double click on a link follows it as the first of the two clicks, so a block with a link in it is pointed at by double clicking the words around the link.

### Ending a reading

24. Quit vim. The whole window goes and the server stops.
25. Close the browser pane instead, with `ctrl-w` in it. vim is asked to quit, which it refuses while anything in it is unwritten, and the reading ends as soon as vim goes.
26. Press the window's close button, and separately press `ctrl-c` in the shell the command was run from. Both ask the same question the browser pane closing asks, and both are refused the same way while anything in vim is unwritten. Nothing is ever taken away from under unsaved work.
27. Kill vim outright, with `pkill -f 'gvim -f --servername BMVIM'`. The window goes and the server stops, the same as quitting vim.
28. After every one of the four: the page's window is gone and every other window of that browser is still open, on the same pages and in the same places. No server is left behind either, and no gvim. `pgrep -af mdview/bmvim_serve.py` should say nothing.
29. With no browser running at all, start a reading and end it. The reading starts one, and the browser it started goes when the reading does, since the page's window was the only window in it.

### The three themes

30. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Mono headings` and `GitHub`.
31. The first two are black on white, and only `Browser default` has any colour at all, on its links. `GitHub` is the exception and keeps GitHub's own palette. Put the same document beside github.com and the two should agree: the heading scale and the underline under the first two levels, a fence a step smaller than the prose around it, inline code on a faint grey, every second row of a table shaded with the header row on the page's own ground, a rule 4px thick, and the copy icon in the corner of each fence.
32. `Mono headings` and `GitHub` cap the measure, so a maximised window does not throw their lines across the whole screen. `Browser default` caps nothing and runs its lines to the edge of the pane, which is what a browser with no stylesheet does. Drag the seam in that theme and the lines rewrap at every position of it, not only once the pane is narrow. Code blocks scroll inside their own box in all three rather than widening the page. In `Browser default` that box is a hairline of the same weight as the contents list and the tables, and the copy button sits inside it without covering the first line of the fence.
33. Changing the theme does not reload the page and does not lose your place in it.
34. Both `bmvim` marks work in all three. Each theme leaves the margin rule its own offset, so check that the rule stands clear of the text in every one of them.

### The copy button

35. Hover a fence in each of the three themes. A copy button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover. In `Browser default` and `Mono headings` the button says `Copy`. In `GitHub` it says nothing and carries GitHub's own copy icon, two squares overlapping, in a 28px square 8px in from the corner of the fence.
36. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
37. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again. In `GitHub` there are no words to change: the icon becomes a green tick inside a green ring for that second and a half, and goes back to the two squares.
38. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
39. In a `bmvim` reading, press a copy button. It copies and vim does not move. Double click the fence beside it and vim moves.
40. `bmv --print doc.md`, then open the file it names over `file://`. The buttons work there too. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

41. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib/__init__.py` that raises `ImportError`, then start a reading. There is no window to make one out of, so the browser and vim open as two ordinary windows wherever the desktop puts them. It says so in one line and the reading works, sync and all. Closing the page is the one thing that does not end it: watching that window needs the X connection the reading has just been refused, so the reading ends when vim quits and not before, and the page's window is left where it is.
42. Neither Chrome nor Chromium on the machine. Take both off `PATH` and start a reading. The page opens in a plain tab of the default browser, both lines of the message are printed saying the window is neither placed nor closed for you, and the reading works.
43. No `DISPLAY`. `env -u DISPLAY bmvim doc.md` says `bmvim` needs a desktop session and suggests `bmv`, and exits 1.
44. The servername already taken. Start one reading, then start a second. The second names the document the first has open and exits 1.
45. The server killed mid-reading. `pkill -f mdview/bmvim_serve.py` while a reading is up. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.

### bmv on its own

46. Several `bmv` readings at once, on different documents. Each prints its own address on its own port and each redraws its own file.
47. No browser reachable. `env -u DISPLAY -u BROWSER bmv doc.md`. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
48. `bmv doc.md` on a document with an image in it, one beside the document and one named by an absolute path. The first is drawn, served out of the tree the reading started in. The second is left to the browser, which is right to find nothing for it.
49. `bmv --print doc.md` on the same document. Open the file it names, move it somewhere else and open it again. The image beside the document is drawn wherever the file has been taken, since it travels inside it, and the theme dropdown works and stores nothing.
50. Close the page in the browser rather than pressing ctrl-c. Within about ten seconds the command ends by itself and the shell comes back. Nothing else may be speaking to that port while you check: a page left open from an earlier reading goes on saying it is there, and a reading is kept up by any page that does.

## Four things that look odd and are not

vim is started with three settings of the reading's own. The headroom gvim keeps clear goes before the vimrc, since it is read once as the window is made and not again: gvim leaves fifty pixels for a window manager to draw a border in, and inside the reading's window nothing is drawn round the pane, so those pixels are two rows the document could have had. The other two go after the vimrc, so that a vimrc asking for either does not win: the menu bar and the scrollbar are dropped, and gvim is told to keep its window while they go, because it otherwise takes the room they were using out of the window rather than giving it to the document.

The page's window is asked to close, in the way a close button asks, rather than being killed or destroyed. It belongs to the browser you already had running, not to the reading, so ending the process behind it would take every other window in that browser with it, and destroying the window would take it away from under a browser still holding it. For the same reason the reading knows that window by sight rather than by owning it: it notes what the desktop is showing before it asks for the page, and the window that appears named after the host the page came from is the one it takes in. Two things follow from borrowing. The page reads under whatever extensions and theme that browser is set up with, and a browser told to continue where it left off may put the reading's window back the next time it starts.

The reading waits for vim to have stopped changing size before it lays the two panes out, in `bmvim_window.py`. gvim asks for a size of its own as it starts, and whether that asking lands before the reading has placed the pane or after it is a matter of a few hundredths of a second. The reading gives the page whatever width vim settles on, so an asking that landed late moved the seam: one reading would open at the split the last was left at and the next at something else entirely. Anything in a vimrc that sets `lines` or `columns` in the GUI does the same thing on top of it, and the vimrc here leaves both alone while `$MDVIEW_URL` says vim is a pane of a reading.

The two panes are taken off the window manager before they are put in the window, by unmapping each one and telling the root window it is withdrawn. Reparenting a window the manager is still managing does not work: the manager reads its client leaving the frame as the window having gone, and the tidying up it does for a window that has gone hands the client back to the root. The withdrawal is what makes the manager let go first, and everything the reading does with its panes afterwards rests on it.
