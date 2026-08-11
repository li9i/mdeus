# mdview

One command for reading a markdown document in a browser, and for editing it there when you want to.

`mdeus <document.md>` serves the document to a window of its own, redraws the page whenever the file changes, and follows relative links to other markdown documents inside the same tree. That window carries the page and nothing else: no address bar, no tabs, no bookmarks. It comes out of the Chrome or Chromium you already have running, which is what makes it open as quickly as it does, and where neither is on the machine the reading opens in an ordinary tab instead. `mdeus --tab <document.md>` asks for that tab whichever browsers are about. Several readings run at once, each on its own port and each under a name of its own. A reading ends on ctrl-c, or once the page has stopped saying it is still open, which is what ends one started from the file manager where there is no terminal to interrupt, and closing the window or the tab is one way of stopping.

`mdeus --print <document.md>` writes one self contained HTML file under `~/.cache/mdview/` and prints its path. Images are embedded, every theme is inlined, and nothing is served or opened. The file survives being moved or sent to somebody.

## The Edit toggle

The page carries an `Edit` toggle at the top of it, and pressing it brings vim in beside the page, in one window. The browser takes the left of that window and gvim takes the right, 44 percent against 56 until you drag the seam between them somewhere else. The window fills the work area, so the page moves and grows as it goes in, and vim opens on the document the page is showing rather than the one the reading started at: follow a link and then press it, and vim opens where you are looking.

Press it again and vim goes, the window goes with it, and the page is handed back to the desktop at the size and in the place it had before, still open on the same document and still where you had scrolled it to. It never reloads. A reading opened with `--edit` had no window of its own to go back to, so that one is left filling the work area. Quitting vim does the same thing, and the toggle comes back up within half a second of vim going. The toggle follows the reading rather than leading it, so a press a vim with unsaved work refuses shows as the toggle going back down.

`mdeus --edit <document.md>` is that toggle already down before you see the page, for when you knew from the start. The reading then opens whole rather than a half at a time: the window is made first and both halves are asked for together.

The toggle is on the page only where there is a desktop session to open vim into. A printed copy never carries it.

## What the two halves do to each other

One gesture works in both halves: double click a block in the page and vim goes to the line that block came from, centred in its window and lit end to end for a moment, and double click a line in vim and the page comes the other way, to the block the pointer landed in. Those two are the whole of what scrolls either half: the page marks the block the vim cursor is in but is never dragged about by it, so scrolling and typing in one window leave the other where its reader left it. A single click belongs to the half it happened in, so you can select a paragraph, follow a link or put the vim cursor somewhere without the other half moving at all. Moving the vim cursor marks the block the cursor is in, and writing the file redraws the page. Follow a link in the page and vim follows it too, so both halves always show the same file.

The reading opens a gvim of its own, so the shell `mdeus` was run from stays yours and waits. The page's window is the browser's rather than the reading's: the reading takes it into its own window while vim is up, and hands it straight back afterwards. The rest of the browser is left alone throughout.

The ground a jump lights in vim is the `MdeusJump` highlight group. It is set as a default, so a `.vimrc` naming it wins.

## Ending a reading

While a reading is only the page, ctrl-c ends it, and so does closing the page, which the server notices within ten seconds of the page going quiet.

While vim is up, vim is what holds the reading. Ctrl-c, the window's close button and the page's window being closed all ask vim to quit, and vim refuses while anything in it is unwritten, so nothing is ever taken away from under unsaved work. Those three end the whole reading once vim goes. Pressing `Edit` again and quitting vim yourself are the two that leave the page behind.

## The rest of the page

The page carries a dropdown of three themes and then three toggles: `Contents`, which is there only once the document has three or more headings, `Full width`, and `Edit`. The theme is a choice between three, so it is a dropdown. The other three are each one view state that is on or off, so each is a button that stands down while it is on and keeps its label wherever it stands, rather than a box that reads as a form waiting to be submitted or a label that flips between saying what is and saying what a click would do.

`Full width` governs `Browser default` and `Mono headings`: on, which is how both open, they run their lines to the edge of the pane and rewrap them wherever the seam is dragged to, and off they hold them to 46em and 38em. `GitHub` holds its 1012px whichever way it is set, since that measure is github.com's rather than the theme's to choose. The theme, the contents setting, the full width setting, and where the seam between the panes was last dragged to, are kept in `~/.config/mdview/state.json`, so a reading opens the way the last one was left. `Edit` is not among them: it says what the reading in front of you is doing rather than what you prefer, so it is stored nowhere and every reading opens with the page alone.

Every fence carries a copy button in its corner as well, which shows on hover or on focus and puts the fence on the clipboard. Two of the themes say `Copy` on it and `GitHub` draws GitHub's own copy icon instead, which turns into a green tick once the fence is on the clipboard. Neither half folds a section away at the moment. Double click used to fold one in the page and space used to fold one in vim, and double click now belongs to the sync in both halves. The code behind the page's fold is still in `page.js` with nothing calling it, and vim is left with whatever folding your own `.vimrc` gives it.

A reading says what it is and which file it is showing: `mdeus: notes.md` on the window or the tab, and the same on the title bar and the panel entry while vim is up. Follow a link to another document and the name follows it. The page writes its own title as it draws, and the window a reading is edited in takes its title from the page inside it, so the two can never say different things.

## What it renders

The markdown GitHub renders, so a document reads here the way it reads there. On top of CommonMark that means tables, strikethrough, task lists, footnotes, bare web and mail addresses turned into links, emoji shortcodes such as `:tada:`, and the five callouts written as `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]` and `> [!CAUTION]`. A marker that is not one of the five, and a marker with words after it on the same line, are both left as the quote they were written as. A shortcode nothing answers to is left as the words it was, and neither shortcodes nor addresses are touched inside a code span or a fence.

Two things GitHub draws are not here, both because they would need something fetched from the network and nothing in a reading is: mathematics and mermaid diagrams. Fences are not syntax highlighted either.

The three themes draw all of it. `GitHub` reproduces GitHub's own colours, icons and spacing for the callouts and the notes. The other two have no palette to spend, so they frame a callout in their own vocabulary and its name is what says which of the five it is.

## What is here

| File | What it is |
| --- | --- |
| `render.py` | Markdown in, blocks out, each carrying the source lines it was built from, plus the heading outline. GitHub's dialect, the five callouts included, since no plugin draws those. Where an image beside the document is written as is the caller's to say. |
| `server.py` | Serves one reading: the page, the document, files from inside the starting tree, and the routes vim talks to. It records the page asking for vim and says what the reading is doing, and no more than that: opening vim and putting it away is the session's work. Imported by whoever is serving, and run by nobody. |
| `state.py` | The one file a reading remembers itself in, read by the server and by the window alike. |
| `browser.py` | Which browser can give a reading a window of its own, and the command that asks it for one. |
| `export.py` | The self contained file `mdeus --print` writes. |
| `vimlink.py` | The link to vim: jumps, following a link on both sides, asking vim to quit, and the cursor line coming back. |
| `cursor.vim` | What vim does for as long as vim is up: the cursor reports, the double click that brings the page over, and the ground a jump lights. |
| `window.py` | One editing session: the window it is drawn in, the browser and gvim inside it, the seam between the two, the title it takes from the page, and handing the page's window back to the desktop at the end. |
| `themes.css` | The three themes, the control row above the document, the copy button on a fence, and the look of the callouts, the task lists and the notes in each theme. |
| `page.js` | The theme dropdown, the three toggles beside it, the contents list, the copy button on every fence, the heading names, the folding of a section, which nothing calls for the moment, and the redraw. |
| `sync.css`, `sync.js` | The two marks and the sync with vim. Loaded by every reading, and asleep until vim is up. |
| `test_render.py`, `test_server.py` | The tests. |
| `../icons/hicolor/*/apps/mdeus.png` | What a reading looks like on the panel while vim is up, and in the "Open With" menu. |

The command itself is `mdeus`, and it lives in `~/.local/bin`.

Its desktop entry is in the `caja` package. A reading is a browser, and a browser with vim beside it as soon as you ask, and an entry carries one icon, so its icon is one image of the two: the terminal behind at the top left and the browser in front at the bottom right, the pair overlapping inside one square. No theme has such an image, so it ships here, and the window an editing session opens wears it as well. It was cut from Buuf 3.46 at 128 pixels, `gnome/128x128/apps/utilities-terminal.png` behind `miscellaneous/128x128/apps/google-chrome.png`, each trimmed to what it draws and scaled to seven tenths of the square. The square is what matters more than the pair: everything else on the panel is square, and an icon wider than it is tall stands out for the wrong reason.

That icon is worn only while vim is up. A reading that is only the page is a window of the browser's, so it wears whatever the browser wears, and there is no way round that short of giving up the borrowed window.

`render.py` and `themes.css` are read by the spec review tool in `~/.claude/scripts/spec_review` as well, so that tool will not start unless this package is stowed.

A page for reading carries `reader` on the root element beside the theme name, and the spec review tool does not. That marker is what sizes the `github` theme at 14px for reading while the review tool keeps 16px. The server writes it once, when it sends the page, and a theme change in `page.js` turns the theme keys on and off one at a time rather than writing the whole class name over, so nothing else on the root is this page's to lose. A printed copy carries the marker too, so `mdeus --print` reads at the same size as a served reading.

`wide` sits on the root as well while `Full width` is on, and the server writes it with the markup for the same reason it writes the theme there: the first paint has to be the page the reader left, rather than lines drawn one way and rewrapped the moment the script catches up. `page.js` turns that one class on and off as the toggle is pressed, and the `browser` and `report` themes are the two that read it.

Each of the three toggles carries `aria-pressed`, and the word in it is written out both ways rather than the attribute being added and taken away: a button with no `aria-pressed` at all is a plain button carrying no state, and each theme draws its pressed face off the same word. `browser` takes the face a machine with no stylesheet gives a button held down, `report` swaps the ink and the paper of its stamp, and `github` drops the face a shade and throws a line of shadow in under the top edge.

## What it needs

`python3-markdown-it` for the parser, `python3-mdit-py-plugins` for the task lists and the footnotes, `python3-linkify-it` for the bare addresses, `python3-emoji` for the shortcodes, `python3-xlib` for the one window an editing session is drawn in, and `python3-pil` to read that window's icon off the disk. Nothing else beyond the standard library. Nothing is fetched at runtime, no page loads an external font, script or stylesheet, and the server listens on `127.0.0.1` and nowhere else.

Chrome or Chromium is what gives a reading a window with nothing in it but the page, and a reading reads in a plain tab where neither is on the machine. Editing also wants a vim built with `+clientserver` and a GUI. The vim half of a reading is a `gvim --servername`, reached by `vim --servername` from the outside, and Ubuntu's plain `vim` package has neither the GUI nor `+clientserver`. `vim-gtk3` has both, and that is what `install.sh` installs. `vim --version | grep clientserver` says which one is on the machine.

The desktop entry calls `mdeus` by name, so `~/.local/bin` has to be on the session path for it to resolve. Ubuntu's stock `~/.profile` puts it there at login when the directory exists, and `install.sh` creates it before the log out it already asks for.

## Tests

```bash
python3 test_render.py
python3 test_server.py
```

Plain asserts in functions named `test_*`, no framework. They cover the renderer, the server and the printed copy. The browser, the windows and vim have no automated cover at all, which is what the list below is for.

## The manual check

Run all of it after touching anything to do with the browser, the windows or vim. Each item says what to do and what should happen.

### The page on its own

1. `mdeus doc.md` from a terminal, with a browser already running. One window on the desktop and one entry on the panel, both reading `mdeus: doc.md`, and the window carries the page and nothing else: no address bar, no tabs, no bookmarks. It is up within a moment of the command, since the browser you already had is the one that put it there. Every other window of that browser is left where it was.
2. `mdeus --tab doc.md`, and then `mdeus doc.md` with Chrome and Chromium both off `PATH`. Both open an ordinary tab of your default browser, address bar and all, and the reading works the same in it.
3. Several readings at once, on different documents. Each prints its own address on its own port and each redraws its own file, and each window is named after the file it is showing.
4. No browser reachable. `env -u DISPLAY -u BROWSER mdeus doc.md`. Nothing opens and nothing is said about it, since a browser asked for a window without a desktop to draw it on fails quietly. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
5. `mdeus doc.md` on a document with an image in it, one beside the document and one named by an absolute path. The first is drawn, served out of the tree the reading started in. The second is left to the browser, which is right to find nothing for it.
6. Close the page rather than pressing ctrl-c, with its close button or with `ctrl-w` in it. Within about ten seconds the command ends by itself and the shell comes back. Nothing else may be speaking to that port while you check: a page left open from an earlier reading goes on saying it is there, and a reading is kept up by any page that does.
7. `env -u DISPLAY mdeus doc.md`. The page carries no `Edit` toggle, since there is no desktop to open vim into. `env -u DISPLAY mdeus --edit doc.md` says so in one line and exits 1.

### Pressing Edit

8. Press `Edit` in a reading. Within about a second the page's window is taken into a window of the reading's own, filling the work area, with gvim on the right of it. The page keeps its place in the document and does not reload. The seam sits where the last session left it. One entry on the panel, reading `mdeus: doc.md`, carrying the reading's own icon.
9. The page keeps whatever you had set: the theme, the full width setting, and where you had scrolled to. `Edit` stands down and stays down.
10. Press `Edit` again. vim goes, the window goes, and the page comes back as a window of its own at the size and in the place it had before it was pressed, still on the same document, still scrolled where it was, and still not reloaded. It has a title bar and a close button of its own again, and it can be clicked in, scrolled and dragged like any other window.
11. Do it from a window that is not maximised. Unmaximise the page, put it somewhere out of the way and make it small, then press `Edit` on and off several times in a row. It fills the work area every time it goes in and comes back to that same small window every time it comes out, rather than keeping the big size or walking a title bar's depth down the screen on each round. Nothing accumulates on the desktop, and the page never reloads.
12. Press `Edit` with unsaved work in vim. vim refuses, and the toggle goes back down within half a second rather than lying about what the reading is doing. Save, press it again, and vim goes.
13. Quit vim with `:qa`. The toggle comes up within half a second and the reading is back to the page alone, exactly as pressing it leaves it.
14. Follow a link to another document, then press `Edit`. vim opens that document, not the one the reading started at.
15. Kill vim outright, with `pkill -f 'gvim -f --servername MDEUS'`. The same as quitting it: the window goes and the page comes back. That pattern names every reading that is editing, so end the others first if you have several.

### Ending it from the editing side

16. Press the window's close button while editing. The whole reading ends: vim goes, the page's window goes, and the shell comes back. It is refused while anything in vim is unwritten, and nothing is taken away from under it.
17. Press ctrl-c in the shell the command was run from, while editing. The same, and refused the same way.
18. Close the page's window while editing, with `ctrl-w` in it. vim is asked to quit and the whole reading ends when it goes, since there is no page left to come back to.
19. After every one of those: every other window of that browser is still open, on the same pages and in the same places, and no server and no gvim is left behind. `pgrep -af mdview` should say nothing.
20. With no browser running at all, press `Edit`. The reading starts one, and the browser it started goes when the reading does, since the page's window was the only window in it.

### The one window

21. `mdeus --edit doc.md` from a terminal. The window is up whole rather than a half at a time: both panes arrive within about two thirds of a second of the command, close enough together that the reading arrives as one thing. It comes up white and stays white: nothing black is shown while either half is on its way. Neither half stands on the desktop as a window of its own on the way in, whichever of the two is up first. A reading opened where no browser was running is the one exception, and there the page follows the vim pane by a second or two. The vim pane fills its half from the first moment, top row to bottom.
22. The browser pane has no address bar, no tabs and no bookmarks, and the vim pane has no menu bar and no scrollbar. Neither pane has a title bar or a close button of its own. The window has one of each for the pair.
23. The shell you typed the command into stays yours. It says where the reading is and then waits, and the vim you are reading with is a gvim the reading opened for itself.
24. Click the browser pane, then the vim pane, then the browser again. The pane you clicked last takes the keyboard every time, so typing goes to the pane you are looking at. Click the title bar instead and the keyboard stays where it was.
25. Leave the reading on the screen, click into a window of another program beside it, and type there for a while. What you type goes to that window and goes on going there, and the reading never takes the keyboard back from it. Scroll and click about in vim first, so that both panes have had the keyboard, and check the same again. A reading takes the keyboard only for its own panes, and only while it is the window the desktop has in front.
26. Unmaximise the window and resize it, larger and smaller. The two panes keep their proportion and go on meeting exactly at every size. A band of the window may be left showing below vim, up to one character row deep and white like the panes beside it, since vim settles on whole rows however tall it is asked to be. The vim pane holds the whole document at every size, both while you resize and once you stop.
27. Two readings editing at once. `mdeus --edit one.md`, then `mdeus --edit two.md` from another shell. Two windows, two entries on the panel, each named after its own document, and each holding its own browser pane and its own vim. Neither takes the other's page window. Type in one and the other stays where it was, and follow a link in one and only that one's name changes. End one and the other carries on whole, page and vim alike.
28. `mdeus doc.md` again from the file manager, through the `mdeus` entry in the "Open With" menu, then press `Edit`. The same one window opens, and no spare window is opened beside it.

### The divider

29. Put the pointer on the join between the two panes. It becomes an arrow pointing both ways, which is the whole of what says the join can be moved. Take the pointer a few pixels off the join and the arrow goes again.
30. Drag the join left and right. Both panes follow the pointer and go on meeting exactly at every moment of the drag, and the seam lands on a whole character column of vim rather than exactly where you let go.
31. Drag as far as it will go each way. It stops while there is still a pane worth reading in on both sides, at 15 percent of the window one way and 85 percent the other.
32. Drag the join somewhere else, press `Edit` off, and press it on again. It opens where you left it. Change the theme in the page as well, and neither setting has put the other out of `~/.config/mdview/state.json`.

### The three way sync

33. Double click a block in the page. vim moves to the first line of that block, whatever mode vim was in beforehand, and the word the two clicks took as a selection is dropped rather than left highlighted.
34. The block vim landed on sits in the middle of the vim pane, and the whole of it carries a pale blue ground, first line to last. Double click a block spanning several lines and check that every line of it is marked rather than only the one vim landed on. The ground goes by itself after a second and a half.
35. Double click a second block while the first is still lit. The first ground goes at once and the second keeps its full second and a half, rather than being put out early by the moment still counting down for the first.
36. A single click in the page never moves vim: click about, drag a selection across a paragraph, press a copy button. A single click in vim never moves the page either, wherever in the document you click.
37. Move the vim cursor. The block holding it takes a solid rule down its left margin, and the rule follows the cursor from block to block.
38. Double click a line in the vim pane. The page comes to the block the pointer landed in and puts it a quarter of the way down the window, wherever the page was left and however near or far that block is, and the rule moves onto it with it. Double click again inside the same block and the page stays where the first one put it. vim selects no word on the way, and the cursor sits where you pointed.
39. Move about vim every way there is and watch the page: edit inside one block, step through the document a line at a time, scroll with the wheel and with `ctrl-d` and `ctrl-f`, jump with a search and a `G` and a `:42`, go to the end of a long document and come back. The mark follows the cursor throughout and the page never moves an inch of its own accord, wherever the cursor goes and whether the block it lands in is on the screen or nowhere near it.
40. Bring the page over to a cursor it has been left behind by: double click that line in vim. It comes at once, as item 38 says. That double click is the only thing on the vim side that scrolls the page.
41. Hold a movement key down and let the cursor run. The reports are throttled in vim to one every 150ms, so the mark keeps up without the page flickering and without vim stuttering. Watch the server's cursor route or the mark itself: nothing arrives closer together than 150ms.
42. The two marks are never confusable. The cursor block carries a rule in the margin and stays marked. The block you double clicked flashes a light grey ground that fades after a second.
43. Write the file in vim. The page redraws. Change the file from somewhere else, with `git checkout` or a formatter, and the page redraws the same way.
44. Click a relative link to another markdown document. The page renders it and vim opens it too, so both halves show the same file, and the title bar and the panel entry both take the new file's name. The browser's back button returns, and the name comes back with it. An absolute path, a path leading out of the starting tree, and an `http` link are all left alone. A double click on a link follows it as the first of the two clicks, so a block with a link in it is pointed at by double clicking the words around the link.
45. Press `Edit` off while a block carries the cursor rule. The rule goes with vim rather than being left standing on a page with nothing behind it. Double click a block afterwards: nothing happens, no grey ground and no jump, since there is no vim to send to. Press it on again and the sync starts from where the new vim's cursor is rather than from where the last one left off.

### The three themes

46. Open a document with headings at three levels, a fence, a quote, a list, a table, a link and a rule, and go through the dropdown. `Browser default`, `Mono headings` and `GitHub`.
47. The first two are black on white, and only `Browser default` has any colour at all, on its links. `GitHub` is the exception and keeps GitHub's own palette. Put the same document beside github.com and the two should agree: the heading scale and the underline under the first two levels, a fence a step smaller than the prose around it, inline code on a faint grey, every second row of a table shaded with the header row on the page's own ground, a rule 4px thick, and the copy icon in the corner of each fence.
48. `Browser default` and `Mono headings` open with `Full width` down and run their lines to the edge of the pane, which is what a browser with no stylesheet does. `GitHub` caps its measure at 1012px, so a maximised window does not throw its lines across the whole screen. Drag the seam in each of the first two and the lines rewrap at every position of it, not only once the pane is narrow. Code blocks scroll inside their own box in all three rather than widening the page. In `Browser default` that box is a hairline of the same weight as the contents list and the tables, and the copy button sits inside it without covering the first line of the fence.
49. Press `Full width` off. `Browser default` holds its lines to 46em and `Mono headings` to 38em, and dragging the seam wider than that leaves them where they are. In `Mono headings` the lines still stand clear of the pane edge either way, since the padding down its sides is not the cap. Press it on again and both follow the seam once more. It changes nothing in `GitHub`, which holds its own measure either way, and it does not reload the page or lose your place in it.
50. Quit and start another reading. It opens with the toggle the way you left it, and with the lines already drawn that way rather than drawn one way and rewrapping a moment later.
51. Changing the theme does not reload the page and does not lose your place in it.
52. Both marks work in all three. Each theme leaves the margin rule its own offset, so check that the rule stands clear of the text in every one of them.
53. The row reads `Theme`, `Contents`, `Full width`, `Edit` in all three themes, and `Contents` keeps that place between the dropdown and `Full width` whether the document has headings enough for it or not. Every toggle takes the same face and the same focus ring the other controls take, and stands down while it is on: a grey face with the edge turned in under `Browser default`, white on black under `Mono headings`, and a shade below its neighbours under `GitHub`. No label moves as a toggle is pressed.

### The copy button

54. Hover a fence in each of the three themes. A copy button appears in the top right corner of it, in that theme's own face, and goes again when the pointer leaves. Nothing shows until you hover. In `Browser default` and `Mono headings` the button says `Copy`. In `GitHub` it says nothing and carries GitHub's own copy icon, two squares overlapping, in a 28px square 8px in from the corner of the fence.
55. Tab to it instead of hovering. It appears on focus and takes the same focus ring the theme's other controls take, and pressing it with the keyboard copies.
56. Press it and paste somewhere. You get the fence exactly as it reads, trailing newline and all. The button says `Copied` for a second and a half, then says `Copy` again. In `GitHub` there are no words to change: the icon becomes a green tick inside a green ring for that second and a half, and goes back to the two squares.
57. Change the theme, then write the file from an editor. The buttons survive both, one per fence and no more.
58. While editing, press a copy button. It copies and vim does not move. Double click the fence beside it and vim moves.
59. `mdeus --print doc.md`, then open the file it names over `file://`. The buttons work there too, and there is no `Edit` toggle on that page. That is the reading where the browser may refuse the clipboard outright, and the button falls back to the old selection copy without saying so.

### When something is missing

60. `python3-xlib` missing. Put a directory on `PYTHONPATH` holding an `Xlib/__init__.py` that raises `ImportError`, then press `Edit`. There is no window to make one out of, so vim opens as an ordinary window of its own wherever the desktop puts it and the page stays where it is. It says so in one line and the sync works. Press it again and vim goes and the page is untouched, since it was never taken anywhere.
61. Neither Chrome nor Chromium on the machine, or `--tab` asked for. The page is in a tab, so pressing `Edit` opens vim as a window of its own beside it and says so in one line. The sync works.
62. The server killed mid-reading. `pkill -f mdeus` while a reading is editing. vim stays usable. Nothing it sends waits on an answer, so nothing it does can hang on a server that has stopped listening.
63. `python3-pil` missing. Put a directory on `PYTHONPATH` holding a `PIL/__init__.py` that raises `ImportError`, then press `Edit`. The window opens and the reading works as ever. The one thing lost is the reading's own image on the panel and on the title bar, and the desktop draws whatever it gives a window carrying no image of its own.

### Everything the markdown carries

64. Open a document holding a task list, the five callouts, two footnotes, a bare address and a shortcode, and put it beside the same file on github.com under the `GitHub` theme. The two should agree throughout.
65. The task list carries a box per item and no bullet or number beside it, ticked where the source says `[x]` and empty where it says `[ ]`. A box cannot be clicked. An ordinary item in the same list keeps its bullet. Brackets in a paragraph stay brackets.
66. Each of the five callouts carries GitHub's colour, GitHub's icon and its name at the top, and the marker line itself is nowhere in the body. `> [!NOTHING]` stays an ordinary quote and so does `> [!NOTE] with words after it`, marker and all. Under the other two themes a callout is framed in that theme's own hairline and its name is what tells one from another.
67. The notes sit at the foot of the document under a hairline, numbered, each ending in an arrow back to where it was cited. Click a number and the page goes to the note, click the arrow and it comes back.
68. The notes are the one block drawn somewhere other than where it was written, so check the sync around them. Double click the notes and vim goes to the first definition. Put the vim cursor on a definition and the notes are marked. Put it on the last paragraph of the document, below the definitions, and that paragraph is marked and not the notes.
69. A bare `https://` address, a `www.` address and a mail address are all links, and `:tada:` is drawn as the character. Neither happens inside a code span or a fence, and a shortcode nothing answers to stays as the words it was.
70. `mdeus --print` on the same document. All of it survives into the one file, icons included, since the icons are drawings in the stylesheet rather than anything fetched.

## Seven things that look odd and are not

Every reading serves its page at a name of its own, `MDEUS` and the process id, rather than at the root. The name has to be settled before the page exists and not when vim arrives, because a browser names a window opened with `--app` after the address the page came from, and that name is the whole of how a reading finds its own page's window when it comes to take it in. The host alone would not do it, since every reading serves on `127.0.0.1` and the port never reaches the name the browser writes. The printed address carries the name for that reason, and a page opened at the bare root instead is one no session can find.

The page's window is asked to close, in the way a close button asks, rather than being killed or destroyed, and only when the whole reading is ending. It belongs to the browser you already had running, not to the reading, so ending the process behind it would take every other window in that browser with it, and destroying the window would take it away from under a browser still holding it. Two things follow from borrowing. The page reads under whatever extensions and theme that browser is set up with, and a browser told to continue where it left off may put the reading's window back the next time it starts.

Handing that window back is the only thing here the older tools never did. Taking a managed window off the window manager and into a container happened on every reading before, so entering an editing session is old ground. Leaving one asks the manager to take charge of a client it has already let go of once, and the grabs taken on the window while it was a pane have to be let go first, or the window comes back to the desktop unable to be clicked in.

Where it comes back to is noted before it is taken, and asked for twice on the way out. The container fills the work area, so a page read in a small window grows as it goes in and has to shrink again as it comes out, or the reader puts it back by hand after every visit to vim. The second asking is a `_NET_MOVERESIZE_WINDOW` message naming static gravity, and the gravity is the whole point of it: an ordinary configure request names where the frame goes rather than where the window does, so a window put back that way walks down and to the right by the depth of its own title bar every time it makes the journey. A session opened with `--edit` had no window of its own before it started, so there is nowhere to put that one back to and it is left filling the work area.

The reading waits for vim to have stopped changing size before it lays the two panes out, in `window.py`. gvim asks for a size of its own as it starts, and whether that asking lands before the reading has placed the pane or after it is a matter of a few hundredths of a second. The reading gives the page whatever width vim settles on, so an asking that landed late moved the seam: one session would open at the split the last was left at and the next at something else entirely. Anything in a vimrc that sets `lines` or `columns` in the GUI does the same thing on top of it, and the vimrc here leaves both alone while `$MDVIEW_URL` says vim is a pane of a reading.

The two panes are taken off the window manager before they are put in the window, by unmapping each one and telling the root window it is withdrawn. Reparenting a window the manager is still managing does not work: the manager reads its client leaving the frame as the window having gone, and the tidying up it does for a window that has gone hands the client back to the root. The withdrawal is what makes the manager let go first, and everything the reading does with its panes afterwards rests on it.

vim is started with three settings of the reading's own. The headroom gvim keeps clear goes before the vimrc, since it is read once as the window is made and not again: gvim leaves fifty pixels for a window manager to draw a border in, and inside the reading's window nothing is drawn round the pane, so those pixels are two rows the document could have had. The other two go after the vimrc, so that a vimrc asking for either does not win: the menu bar and the scrollbar are dropped, and gvim is told to keep its window while they go, because it otherwise takes the room they were using out of the window rather than giving it to the document.
