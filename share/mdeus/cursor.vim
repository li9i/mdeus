" What vim does for as long as a reading is up.
"
" Sourced by the vim a reading opens, and reached from nowhere else. It reports
" where the cursor is for the page to mark, folds the document a section at a
" time, lights the block the page sends it to, and keeps the whole document
" drawn when the reading is resized.
"
" The two names it needs come from the environment the reading sets: MDVIEW_LINK
" is the script that carries a line to the server, and MDVIEW_URL is where that
" server is listening.

" Say where the cursor is, for the page to mark the block holding it.
"
" A timer holds this to one report every 150ms. A document scrolled through
" with a key held down moves the cursor far oftener than a page can draw it,
" and the timer reads the line when it comes round rather than when it was set,
" so what is reported is always where the cursor ended up.
"
" The report is started and left to itself. Waiting on it would put the whole
" of vim behind a server that may have stopped listening, and every line
" stepped through would stutter.
let s:pending = 0

function! s:MdviewReport(timer) abort
  let s:pending = 0
  call job_start(['python3', $MDVIEW_LINK, 'cursor', $MDVIEW_URL, string(line('.'))])
endfunction

function! s:MdviewMoved() abort
  if s:pending
    return
  endif
  let s:pending = 1
  call timer_start(150, function('s:MdviewReport'))
endfunction

" A click is a jump rather than a move, so it is reported at once and as a
" click, and the page comes to the block the pointer landed on wherever the
" page was left. It is sent straight rather than through the timer, since the
" throttled report of the same line follows within 150ms and would arrive as an
" ordinary move that the page is right to sit still for.
function! s:MdviewClicked() abort
  call job_start(
    \ ['python3', $MDVIEW_LINK, 'cursor', $MDVIEW_URL, string(line('.')), 'click'])
endfunction

" Where a section begins and ends, for folding one away. A fold runs from a
" top level heading to the line before the next one, and nothing under that
" level folds at all: a section is the unit a long document is read in. The
" name is a plain one, since a name held to this file cannot be called from a
" fold expression.
function! BmvimFoldLevel(lnum) abort
  return getline(a:lnum) =~# '^# ' ? '>1' : '='
endfunction

" Folding by section, and the space that opens and closes one. Set on every
" document the reading shows rather than once at the start, since following a
" link in the page opens another file in the same window and a fresh buffer
" arrives with the vimrc's own settings on it. A reading opens with every
" section open.
function! s:MdviewFolds() abort
  setlocal foldmethod=expr
  setlocal foldexpr=BmvimFoldLevel(v:lnum)
  setlocal foldlevel=99
  nnoremap <buffer> <silent> <space> za
endfunction

" Name the rows the terminal may scroll within again, every time the reading is
" resized.
"
" vim names those rows once, as it starts, and a terminal holds on to what it
" was told. The reading resizes the terminal after vim has started in it, so
" from then on the terminal scrolls within the rows the pane had at first while
" vim writes as though the whole pane scrolled. A line vim ends at the foot of
" those first rows takes part of the document out from under vim's own record of
" what the pane holds, and vim, believing those rows drawn, leaves them as they
" are: the top of the pane shows lines the reading has moved on from until
" something makes vim draw the whole pane again.
"
" Naming the rows puts the terminal's cursor at the top left, so it is sent back
" to where vim left it in the same breath.
function! s:MdviewResized() abort
  call echoraw(printf("\<Esc>[r\<Esc>[%d;%dH", screenrow(), screencol()))
endfunction

augroup mdview
  autocmd!
  autocmd CursorMoved,CursorMovedI * call s:MdviewMoved()
  autocmd BufWinEnter * call s:MdviewFolds()
  autocmd VimResized * call s:MdviewResized()
augroup END

" The click itself first, so the cursor is where it landed before it is read.
nnoremap <silent> <LeftMouse> <LeftMouse>:call <SID>MdviewClicked()<CR>

" Where the cursor starts, so the page marks a block from the first moment
" rather than waiting to be moved. The document is open by the time this is
" sourced, so it is given its folds here as a later one is given them on
" arrival.
call s:MdviewFolds()
call s:MdviewReport(0)

" Where a clicked block lands. The page knows the source lines every block was
" built from and sends both ends of them, so the whole block is lit rather than
" the line it starts at. A pale ground for the eye to land on without hunting,
" and gone again once the eye has had it: long enough to be seen, short enough
" not to be read against. Set as a default, so that naming BmvimJump in .vimrc
" overrides it.
let s:linger = 1500
highlight default BmvimJump ctermfg=black ctermbg=153 guifg=black guibg=#BDDFFF

" The window and the mark are told to the moment that puts it out, rather than
" left for it to find, since by the time it comes round the window it was lit in
" may not be the one in hand. A mark already gone is no matter. The names are
" plain ones, since a name held to this file cannot be called from the page and
" cannot be handed to a timer.
function! BmvimFadeMark(window, match, timer) abort
  silent! call matchdelete(a:match, a:window)
endfunction

function! BmvimJumpTo(first, last) abort
  " Only the block last clicked is ever lit. The mark from the click before
  " goes, and so does the moment still counting down for it, which would
  " otherwise come round and put out the light this click has just lit.
  if exists('w:bmvim_timer')
    silent! call timer_stop(w:bmvim_timer)
    unlet w:bmvim_timer
  endif
  if exists('w:bmvim_match')
    silent! call matchdelete(w:bmvim_match)
    unlet w:bmvim_match
  endif
  call cursor(a:first, 1)
  normal! zz
  let w:bmvim_match = matchadd(
    \ 'BmvimJump', '\%>' . (a:first - 1) . 'l\%<' . (a:last + 1) . 'l.\+')
  let w:bmvim_timer =
    \ timer_start(s:linger, function('BmvimFadeMark', [win_getid(), w:bmvim_match]))
endfunction
