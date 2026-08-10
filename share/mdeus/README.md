# mdview

Two commands for reading a markdown document in a browser.

`bmv <document.md>` serves the document to your default browser, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. Several readings run at once, each on its own port. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt.

`bmv --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

`bmvim <document.md>` is the same reading with vim beside it, in one window. The browser takes the left of that window and gvim takes the right, 44 percent against 56 until you drag the seam between them somewhere else. One gesture works in both halves: double click a block in the page and vim goes to the line that block came from, centred in its window and lit end to end for a moment, and double click a line in vim and the page comes the other way, to the block the pointer landed in. Those two are the whole of what scrolls either half: the page marks the block the vim cursor is in but is never dragged about by it, so scrolling and typing in one window leave the other where its reader left it. A single click belongs to the half it happened in, so you can select a paragraph, follow a link or put the vim cursor somewhere without the other half moving at all. Moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. The reading opens a gvim of its own, so the shell `bmvim` was run from stays yours and waits. The page opens in the browser you already have running, which is what makes a reading open in well under a second, and the reading borrows that one window and leaves the rest of the browser alone: it takes the window into its own, asks it to close when the reading ends, and closing it by hand ends the reading. Where no browser is running the reading starts yours, and then it opens as slowly as a browser starts. Several readings run at once, each in a window of its own with a vim of its own, and a reading needs a desktop session.

The page carries a dropdown of three themes, a `Full width` box beside it, and a `Contents` button, which is there only once the document has three or more headings. The box governs `Browser default` and `Mono headings`: ticked, which is how both open, they run their lines to the edge of the pane and rewrap them wherever the seam is dragged to, and unticked they hold them to 46em and 38em. `GitHub` holds its 1012px whichever way the box is set, since that measure is github.com's rather than the theme's to choose. Those three settings, and where the seam between the panes was last dragged to, are kept in `~/.config/mdview/state.json`, so a reading opens the way the last one was left. Every fence carries a copy button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard. Two of the themes say `Copy` on it and `GitHub` draws GitHub's own copy icon instead, which turns into a green tick once the fence is on the clipboard. Neither half folds a section away at the moment. Double click used to fold one in the page and space used to fold one in vim, and double click now belongs to the sync in both halves. The code behind the page's fold is still in `page.js` with nothing calling it, and vim is left with whatever folding your own `.vimrc` gives it.

A reading says which command it is and which file it is showing: the tab reads `bmv: notes.md`, and a `bmvim` reading carries `bmvim: notes.md` on its title bar and on the panel as well. Follow a link to another document and the name follows it. The page writes its own title as it draws, and a `bmvim` reading takes its window's title from the page inside it, so the two can never say different things.

The ground a jump lights in vim is the `BmvimJump` highlight group. It is set as a default, so a `.vimrc` naming it wins.

## What it renders

The markdown GitHub renders, so a document reads here the way it reads there. On top of CommonMark that means tables, strikethrough, task lists, footnotes, bare web and mail addresses turned into links, emoji shortcodes such as `:tada:`, and the five callouts written as `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]` and `> [!CAUTION]`. A marker that is not one of the five, and a marker with words after it on the same line, are both left as the quote they were written as. A shortcode nothing answers to is left as the words it was, and neither shortcodes nor addresses are touched inside a code span or a fence.

Two things GitHub draws are not here, both because they would need something fetched from the network and nothing in a reading is: mathematics and mermaid diagrams. Fences are not syntax highlighted either.

The three themes draw all of it. `GitHub` reproduces GitHub's own colours, icons and spacing for the callouts and the notes. The other two have no palette to spend, so they frame a callout in their own vocabulary and its name is what says which of the five it is.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from, plus the heading outline. GitHub's dialect, the five callouts included, since no plugin draws those. Where an image beside the document is written as is the caller's to say. |
| `server.py` | Serves one reading: the page, the document, files from inside the starting tree, and the routes vim talks to. Imported by whoever is serving, and run by nobody. |
| `state.py` | The one file a reading remembers itself in, read by the server and by the window alike. |
| `export.py` | The self contained file `bmv --print` writes. |
| `vimlink.py` | The link to vim: jumps, following a link on both sides, asking vim to quit, and the cursor line coming back. |
| `cursor.vim` | What vim does for as long as a reading is up: the cursor reports, the double click that brings the page over, and the ground a jump lights. |
| `bmvim_serve.py` | Runs the server for a `bmvim` reading and says which port it landed on, since the command that starts one is a shell script. `bmv` serves in process and needs no such thing. |
| `bmvim_window.py` | The one window a reading with vim is drawn in, the browser and gvim inside it, the seam between the two, and the title it takes from the page. |
| `themes.css` | The three themes, the control row above the document, the copy button on a fence, and the look of the callouts, the task lists and the notes in each theme. |
| `page.js` | The theme dropdown, the full width box, the contents list, the copy button on every fence, the heading names, the folding of a section, which nothing calls for the moment, and the redraw. |
| `bmvim.css`, `bmvim.js` | The two marks and the sync. `bmv` never loads either. |
| `test_render.py`, `test_server.py` | The tests. |
| `../icons/hicolor/*/apps/bmvim.png` | What a `bmvim` reading looks like on the panel and in the "Open With" menu. |

The commands themselves are `bmv` and `bmvim`, and they live in `~/.local/bin`.

The desktop entry of each is in the `caja` package, and the two are drawn differently. `bmv` opens a page and nothing else, so its entry names `google-chrome` and takes whatever the icon theme of the moment draws for the browser. `bmvim` opens a browser and a terminal, and an entry carries one icon, so its icon is one image of the two: the terminal behind at the top left and the browser in front at the bottom right, the pair overlapping inside one square. No theme has such an image, so it ships here, and the window a reading opens wears it as well. It was cut from Buuf 3.46 at 128 pixels, `gnome/128x128/apps/utilities-terminal.png` behind `miscellaneous/128x128/apps/google-chrome.png`, each trimmed to what it draws and scaled to seven tenths of the square. The square is what matters more than the pair: everything else on the panel is square, and an icon wider than it is tall stands out for the wrong reason. Change the icon theme and `bmv` follows it while `bmvim` keeps this image, so cut it again from the new theme if the pair stops matching.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. The server writes it once, when it sends the page, and a theme change in `page.js` turns the theme keys on and off one at a time rather than writing the whole class name over, so nothing else on the root is this page's to lose. A printed copy carries the marker too, so `bmv --print` reads at the same size as a served reading.

`wide` sits on the root as well while the `Full width` box is ticked, and the server writes it with the markup for the same reason it writes the theme there: the first paint has to be the page the reader left, rather than lines drawn one way and rewrapped the moment the script catches up. `page.js` turns that one class on and off as the box is ticked, and the `browser` and `report` themes are the two that read it.

## What it needs

`python3-markdown-it` for the parser, `python3-mdit-py-plugins` for the task lists and the footnotes, `python3-linkify-it` for the bare addresses, `python3-emoji` for the shortcodes, `python3-xlib` for the one window a `bmvim` reading is drawn in, and `python3-pil` to read that window's icon off the disk. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and both commands serve on `127.0.0.1` and nowhere else.

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

1. `bmvim doc.md` from a terminal. One window on the desktop and one entry on the panel, both reading `bmvim: doc.md`, and both carrying the reading's own icon, a terminal with a browser in front of it. The browser takes the left of that window and vim the right, and the two meet without a gap and without overlapping. The window fills the work area, so nothing in the reading sits under a panel. It comes up white and stays white: nothing black is shown while either half is on its way. Neither half stands on the desktop as a window of its own on the way in, whichever of the two is up first. Both are up within about two thirds of a second of the command, close enough together that the reading arrives whole rather than a half at a time. A reading opened where no browser was running is the one exception, and there the page follows the vim pane by a second or two. The vim pane fills its half from the first moment, top row to bottom, and the seam sits where the last reading left it rather than wherever vim first asked to be. Open several readings in a row and check that the seam lands in the same place every time.
2. The browser pane has no address bar, no tabs and no bookmarks, and the vim pane has no menu bar and no scrollbar. Neither pane has a title bar or a close button of its own. The window has one of each for the pair.
3. The shell you typed the command into stays yours. It says where the reading is and then waits, and the vim you are reading with is a gvim the reading opened for itself.
4. Click the browser pane, then the vim pane, then the browser again. The pane you clicked last takes the keyboard every time, so typing goes to the pane you are looking at. Click the title bar instead and the keyboard stays where it was.
5. Leave the reading on the screen, click into a window of another program beside it, and type there for a while. What you type goes to that window and goes on going there, and the reading never takes the keyboard back from it. Scroll and click about in vim first, so that both panes have had the keyboard, and check the same again. A reading takes the keyboard only for its own panes, and only while it is the window the desktop has in front.
6. Unmaximise the window and resize it, larger and smaller. The two panes keep their proportion and go on meeting exactly at every size. A band of the window may be left showing below vim, up to one character row deep and white like the panes beside it, since vim settles on whole rows however tall it is asked to be. The vim pane holds the whole document at every size, both while you resize and once you stop.
7. Two readings at once. `bmvim one.md`, then `bmvim two.md` from another shell. Two windows, two entries on the panel, each named after its own document, and each holding its own browser pane and its own vim. Type in one and the other stays where it was, and follow a link in one and only that one's name changes. Quit one and the other carries on whole, page and vim alike. Start a third and a fourth if you like.
8. `bmvim doc.md` again from the file manager, through the `bmvim` entry in the "Open With" menu. The same one window opens, and no spare window is opened beside it.

### The divider

9. Put the pointer on the join between the two panes. It becomes an arrow pointing both ways, which is the whole of what says the join can be moved. Take the pointer a few pixels off the join and the arrow goes again.
10. Drag the join left and right. Both panes follow the pointer and go on meeting exactly at every moment of the drag, and the seam lands on a whole character column of vim rather than exactly where you let go.
11. Drag as far as it will go each way. It stops while there is still a pane worth reading in on both sides, at 15 percent of the window one way and 85 percent the other.
12. Drag the join somewhere else, quit, and start another reading. It opens where you left it. Change the theme in the page as well, and neither setting has put the other out of `~/.config/mdview/state.json`.

### The three way sync

13. Double click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand, and the word the two clicks took as a selection is dropped rather than left highlighted.
14. The block vim landed on sits in the middle of the vim pane, and the whole of it carries a pale blue ground, first line to last. Double click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
15. Double click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
16. A single click in the page never moves vim: click about, drag a selection across a paragraph, press a copy button. A single click in vim never moves the page either, wherever in the document you click.
17. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
18. Double click a line in the vim pane. The page comes to the block the pointer landed in and puts it a quarter of the way down the window, wherever the page was left and however near or far that block is, and the rule moves onto it with it. Double click again inside the same block and the page stays where the first one put it. vim selects no word on the way, and the cursor sits where you pointed.
19. Move about vim every way there is and watch the page: edit inside one block, step through the document a line at a time, scroll with the wheel and with `ctrl-d` and `ctrl-f`, jump with a search and a `G` and a `:42`, go to the end of a long document and come back. The mark follows the cursor throughout and the page never moves an inch of its own accord, wherever the cursor goes and whether the block it lands in is on the screen or nowhere near it.
20. Bring the page over to a cursor it has been left behind by: double click that line in vim. It comes at once, as item 18 says. That double click is the only thing on the vim side that scrolls the page.
21. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
22. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. The block you double clicked flashes a light grey ground that fades after a second.
23. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
24. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file, and the title bar and the panel entry both take the new file's name. The browser's back button returns, and the name comes back with it. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone. A double click on a link follows it as the first of the two clicks, so a block with a link in it is pointed at by double clicking the words around the link.

### Ending a reading

25. Quit vim. The whole window goes and the server stops.
26. Close the browser pane instead, with `ctrl-w` in it. vim is asked to quit, which it refuses while anything in it is unwritten, and the reading ends as soon as vim goes.
27. Press the window's close button, and separately press `ctrl-c` in the shell the command was run from. Both ask the same question the browser pane closing asks, and both are refused the same way while anything in vim is unwritten. Nothing is ever taken away from under unsaved work.
28. Kill vim outright, with `pkill -f 'gvim -f --servername BMVIM'`. The window goes and the server stops, the same as quitting vim. That pattern names every reading that is up, so end the others first if you have several.
29. After every one of the four: the page's window is gone and every other window of that browser is still open, on the same pages and in the same places. No server is left behind either, and no gvim. `pgrep -af mdview/bmvim_serve.py` should say nothing.
30. With no browser running at all, start a reading and end it. The reading starts one, and the browser it started goes when the reading does, since the page's window was the only window in it.

### The three themes

31. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Mono headings` and `GitHub`.
32. The first two are black on white, and only `Browser default` has any colour at all, on its links. `GitHub` is the exception and keeps GitHub's own palette. Put the same document beside github.com and the two should agree: the heading scale and the underline under the first two levels, a fence a step smaller than the prose around it, inline code on a faint grey, every second row of a table shaded with the header row on the page's own ground, a rule 4px thick, and the copy icon in the corner of each fence.
33. `Browser default` and `Mono headings` open with `Full width` ticked and run their lines to the edge of the pane, which is what a browser with no stylesheet does. `GitHub` caps its measure at 1012px, so a maximised window does not throw its lines across the whole screen. Drag the seam in each of the first two and the lines rewrap at every position of it, not only once the pane is narrow. Code blocks scroll inside their own box in all three rather than widening the page. In `Browser default` that box is a hairline of the same weight as the contents list and the tables, and the copy button sits inside it without covering the first line of the fence.
34. Untick `Full width`. `Browser default` holds its lines to 46em and `Mono headings` to 38em, and dragging the seam wider than that leaves them where they are. In `Mono headings` the lines still stand clear of the pane edge either way, since the padding down its sides is not the cap. Tick the box again and both follow the seam once more. It changes nothing in `GitHub`, which holds its own measure either way, and it does not reload the page or lose your place in it.
35. Quit and start another reading. It opens with the box the way you left it, and with the lines already drawn that way rather than drawn one way and rewrapping a moment later.
36. Changing the theme does not reload the page and does not lose your place in it.
37. Both `bmvim` marks work in all three. Each theme leaves the margin rule its own offset, so check that the rule stands clear of the text in every one of them.

### The copy button

38. Hover a fence in each of the three themes. A copy button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover. In `Browser default` and `Mono headings` the button says `Copy`. In `GitHub` it says nothing and carries GitHub's own copy icon, two squares overlapping, in a 28px square 8px in from the corner of the fence.
39. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
40. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again. In `GitHub` there are no words to change: the icon becomes a green tick inside a green ring for that second and a half, and goes back to the two squares.
41. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
42. In a `bmvim` reading, press a copy button. It copies and vim does not move. Double click the fence beside it and vim moves.
43. `bmv --print doc.md`, then open the file it names over `file://`. The buttons work there too. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

44. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib/__init__.py` that raises `ImportError`, then start a reading. There is no window to make one out of, so the browser and vim open as two ordinary windows wherever the desktop puts them. It says so in one line and the reading works, sync and all. Closing the page is the one thing that does not end it: watching that window needs the X connection the reading has just been refused, so the reading ends when vim quits and not before, and the page's window is left where it is.
45. Neither Chrome nor Chromium on the machine. Take both off `PATH` and start a reading. The page opens in a plain tab of the default browser, both lines of the message are printed saying the window is neither placed nor closed for you, and the reading works.
46. No `DISPLAY`. `env -u DISPLAY bmvim doc.md` says `bmvim` needs a desktop session and suggests `bmv`, and exits 1.
47. The server killed mid-reading. `pkill -f mdview/bmvim_serve.py` while a reading is up. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.
48. `python3-pil` missing. Put a directory on `PYTHONPATH` holding a `PIL/__init__.py` that raises `ImportError`, then start a reading. The window opens and the reading works as ever. The one thing lost is the reading's own image on the panel and on the title bar, and the desktop draws whatever it gives a window carrying no image of its own.

### bmv on its own

49. Several `bmv` readings at once, on different documents. Each prints its own address on its own port and each redraws its own file, and each tab is named after the file it is showing.
50. No browser reachable. `env -u DISPLAY -u BROWSER bmv doc.md`. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
51. `bmv doc.md` on a document with an image in it, one beside the document and one named by an absolute path. The first is drawn, served out of the tree the reading started in. The second is left to the browser, which is right to find nothing for it.
52. `bmv --print doc.md` on the same document. Open the file it names, move it somewhere else and open it again. The image beside the document is drawn wherever the file has been taken, since it travels inside it, and the theme dropdown and the `Full width` box both work and store nothing.
53. Close the page in the browser rather than pressing ctrl-c. Within about ten seconds the command ends by itself and the shell comes back. Nothing else may be speaking to that port while you check: a page left open from an earlier reading goes on saying it is there, and a reading is kept up by any page that does.

### Everything the markdown carries

54. Open a document holding a task list, the five callouts, two footnotes, a bare address and a shortcode, and put it beside the same file on github.com under the `GitHub` theme. The two should agree throughout.
55. The task list carries a box per item and no bullet or number beside it, ticked where the source says `[x]` and empty where it says `[ ]`. A box cannot be clicked. An ordinary item in the same list keeps its bullet. Brackets in a paragraph stay brackets.
56. Each of the five callouts carries GitHub's colour, GitHub's icon and its name at the top, and the marker line itself is nowhere in the body. `> [!NOTHING]` stays an ordinary quote and so does `> [!NOTE] with words after it`, marker and all. Under the other two themes a callout is framed in that theme's own hairline and its name is what tells one from another.
57. The notes sit at the foot of the document under a hairline, numbered, each ending in an arrow back to where it was cited. Click a number and the page goes to the note, click the arrow and it comes back.
58. The notes are the one block drawn somewhere other than where it was written, so check the `bmvim` sync around them. Double click the notes and vim goes to the first definition. Put the vim cursor on a definition and the notes are marked. Put it on the last paragraph of the document, below the definitions, and that paragraph is marked and not the notes.
59. A bare `https://` address, a `www.` address and a mail address are all links, and `:tada:` is drawn as the character. Neither happens inside a code span or a fence, and a shortcode nothing answers to stays as the words it was.
60. `bmv --print` on the same document. All of it survives into the one file, icons included, since the icons are drawings in the stylesheet rather than anything fetched.

## Four things that look odd and are not

vim is started with three settings of the reading's own. The headroom gvim keeps clear goes before the vimrc, since it is read once as the window is made and not again: gvim leaves fifty pixels for a window manager to draw a border in, and inside the reading's window nothing is drawn round the pane, so those pixels are two rows the document could have had. The other two go after the vimrc, so that a vimrc asking for either does not win: the menu bar and the scrollbar are dropped, and gvim is told to keep its window while they go, because it otherwise takes the room they were using out of the window rather than giving it to the document.

The page's window is asked to close, in the way a close button asks, rather than being killed or destroyed. It belongs to the browser you already had running, not to the reading, so ending the process behind it would take every other window in that browser with it, and destroying the window would take it away from under a browser still holding it. For the same reason the reading knows that window by name rather than by owning it. A browser names a window opened with `--app` after the address the page came from, so every reading serves its page under a name of its own, `BMVIM` and its process id, and the window carrying that name is the one it takes in. The host alone would not do it, since every reading serves on `127.0.0.1` and the port never reaches the name the browser writes. Two things follow from borrowing. The page reads under whatever extensions and theme that browser is set up with, and a browser told to continue where it left off may put the reading's window back the next time it starts.

The reading waits for vim to have stopped changing size before it lays the two panes out, in `bmvim_window.py`. gvim asks for a size of its own as it starts, and whether that asking lands before the reading has placed the pane or after it is a matter of a few hundredths of a second. The reading gives the page whatever width vim settles on, so an asking that landed late moved the seam: one reading would open at the split the last was left at and the next at something else entirely. Anything in a vimrc that sets `lines` or `columns` in the GUI does the same thing on top of it, and the vimrc here leaves both alone while `$MDVIEW_URL` says vim is a pane of a reading.

The two panes are taken off the window manager before they are put in the window, by unmapping each one and telling the root window it is withdrawn. Reparenting a window the manager is still managing does not work: the manager reads its client leaving the frame as the window having gone, and the tidying up it does for a window that has gone hands the client back to the root. The withdrawal is what makes the manager let go first, and everything the reading does with its panes afterwards rests on it.
