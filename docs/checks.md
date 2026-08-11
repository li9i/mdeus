# Checks

What to run after touching anything, and the manual list for the parts no test reaches: the browser, the windows and vim.

## Tests

```bash
cd share/mdeus
python3 test_render.py
python3 test_server.py
```

Plain asserts in functions named `test_*`, no framework. They cover the renderer, the server and the printed copy. The browser, the windows and vim have no automated cover at all, which is what the list below is for.

## The manual check

Run all of it after touching anything to do with the browser, the windows or vim. Each item says what to do and what should happen.

### The page on its own

1. `mdeus doc.md` from a terminal, with a browser already running. One window on the desktop and one entry on the panel, both reading `doc.md` and carrying the reading's own icon, and the window carries the page and nothing else: no address bar, no tabs, no bookmarks. It is up within a moment of the command, since the browser you already had is the one that put it there. Every other window of that browser is left where it was.
2. `mdeus --tab doc.md`, and then `mdeus doc.md` with Chrome and Chromium both off `PATH`. Both open an ordinary tab of your default browser, address bar and all, and the reading works the same in it.
3. Several readings at once, on different documents. Each prints its own address on its own port and each redraws its own file, and each window is named after the file it is showing.
4. No browser reachable. `env -u DISPLAY -u BROWSER mdeus doc.md`. Nothing opens and nothing is said about it, since a browser asked for a window without a desktop to draw it on fails quietly. The address is printed anyway and the reading serves, so it can still be opened by hand. Fetch it with `curl` or paste it into a browser started later.
5. `mdeus doc.md` on a document with an image in it, one beside the document and one named by an absolute path. The first is drawn, served out of the tree the reading started in. The second is left to the browser, which is right to find nothing for it.
6. Close the page rather than pressing ctrl-c, with its close button or with `ctrl-w` in it. Within a second the command ends by itself and the shell comes back. Reload a page with `ctrl-r` first and leave it a moment: the reading is still up afterwards, since a reload says goodbye on its way out like a close does and the page that comes back takes it straight back. Nothing else may be speaking to that port while you check: a page left open from an earlier reading goes on saying it is there, and a reading is kept up by any page that does.
7. `env -u DISPLAY mdeus doc.md`. The page carries no `Edit` toggle, since there is no desktop to open vim into. `env -u DISPLAY mdeus --edit doc.md` says so in one line and exits 1.

### Pressing Edit

8. Press `Edit` in a reading. Within about a sixth of a second the page's window is taken into a window of the reading's own, filling the work area, with gvim on the right of it. gvim is up before you press it, waiting out of sight, so what the press costs is the page's window moving and nothing else. Leave the reading a couple of seconds after it opens before pressing, since a press that beats the warming pays the old half second for gvim. The page keeps its place in the document and does not reload. The seam sits where the last session left it. One entry on the panel, reading `doc.md`, carrying the reading's own icon.
9. The page keeps whatever you had set: the theme, the full width setting, and where you had scrolled to. `Edit` stands down and stays down.
10. Press `Edit` again. vim goes, the window goes, and the page comes back as a window of its own at the size and in the place it had before it was pressed, still on the same document, still scrolled where it was, and still not reloaded. It has a title bar and a close button of its own again, and it can be clicked in, scrolled and dragged like any other window.
11. Do it from a window that is not maximised. Unmaximise the page, put it somewhere out of the way and make it small, then press `Edit` on and off several times in a row. It fills the work area every time it goes in and comes back to that same small window every time it comes out, rather than keeping the big size or walking a title bar's depth down the screen on each round. Nothing accumulates on the desktop, and the page never reloads.
12. Press `Edit` with unsaved work in vim. vim refuses, and the toggle goes back down within half a second rather than lying about what the reading is doing. Save, press it again, and vim goes.
13. Quit vim with `:qa`. The toggle comes up within half a second and the reading is back to the page alone, exactly as pressing it leaves it.
14. Follow a link to another document, then press `Edit`. vim opens that document, not the one the reading started at.
15. Kill vim outright, with `pkill -x gvim`. The same as quitting it: the window goes and the page comes back. Then do it the other way round, on a vim that was only ever waiting: start a reading, leave it a couple of seconds, `pkill -x gvim`, and press `Edit`. It opens as it always did, in about half a second rather than a sixth, since the toggle has to start a vim of its own. Press it off and on again and the second press is quick once more. That command kills every gvim on the machine, so close your own before you try either.

### Ending it from the editing side

16. Press the window's close button while editing. The whole reading ends: vim goes, the page's window goes, and the shell comes back. It is refused while anything in vim is unwritten, and nothing is taken away from under it.
17. Press ctrl-c in the shell the command was run from, while editing. The same, and refused the same way.
18. Close the page's window while editing, with `ctrl-w` in it. vim is asked to quit and the whole reading ends when it goes, since there is no page left to come back to.
19. After every one of those: every other window of that browser is still open, on the same pages and in the same places, and no server and no gvim is left behind. `pgrep -af mdeus` should say nothing, and `pgrep -x gvim` should say nothing either, since a reading that ended while its vim was still waiting has to take that one with it as well.
20. With no browser running at all, press `Edit`. The reading starts one, and the browser it started goes when the reading does, since the page's window was the only window in it.

### The one window

21. `mdeus --edit doc.md` from a terminal. Nothing is warmed here, since the reading edits from the first moment and there is no page to wait behind. The window is up whole rather than a half at a time: both panes arrive within about a second of the command, close enough together that the reading arrives as one thing. It comes up white and stays white: nothing black is shown while either half is on its way. Neither half stands on the desktop as a window of its own on the way in, whichever of the two is up first. A reading opened where no browser was running is the one exception, and there the page follows the vim pane by a second or two. The vim pane fills its half from the first moment, top row to bottom.
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
32. Drag the join somewhere else, press `Edit` off, and press it on again. It opens where you left it. Change the theme in the page as well, and neither setting has put the other out of `~/.config/mdeus/state.json`.

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
63. `python3-pil` missing. Put a directory on `PYTHONPATH` holding a `PIL/__init__.py` that raises `ImportError`, then press `Edit`. The window opens and the reading works as ever. The one thing lost is the reading's own image on the panel and on the title bar, and the desktop draws whatever it gives a window carrying no image of its own. A reading that is only the page keeps its icon throughout, since that one comes off the page rather than off the disk.

### Everything the markdown carries

64. Open a document holding a task list, the five callouts, two footnotes, a bare address and a shortcode, and put it beside the same file on github.com under the `GitHub` theme. The two should agree throughout.
65. The task list carries a box per item and no bullet or number beside it, ticked where the source says `[x]` and empty where it says `[ ]`. A box cannot be clicked. An ordinary item in the same list keeps its bullet. Brackets in a paragraph stay brackets.
66. Each of the five callouts carries GitHub's colour, GitHub's icon and its name at the top, and the marker line itself is nowhere in the body. `> [!NOTHING]` stays an ordinary quote and so does `> [!NOTE] with words after it`, marker and all. Under the other two themes a callout is framed in that theme's own hairline and its name is what tells one from another.
67. The notes sit at the foot of the document under a hairline, numbered, each ending in an arrow back to where it was cited. Click a number and the page goes to the note, click the arrow and it comes back.
68. The notes are the one block drawn somewhere other than where it was written, so check the sync around them. Double click the notes and vim goes to the first definition. Put the vim cursor on a definition and the notes are marked. Put it on the last paragraph of the document, below the definitions, and that paragraph is marked and not the notes.
69. A bare `https://` address, a `www.` address and a mail address are all links, and `:tada:` is drawn as the character. Neither happens inside a code span or a fence, and a shortcode nothing answers to stays as the words it was.
70. `mdeus --print` on the same document. All of it survives into the one file, icons included, since the icons are drawings in the stylesheet rather than anything fetched.

