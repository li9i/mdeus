" What vim does for as long as a reading is up.
"
" Sourced by the vim a reading opens, and reached from nowhere else. It reports
" where the cursor is for the page to mark, and lights the block the page sends
" it to.
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

" A double click is a jump rather than a move, so it is reported at once and as
" a click, and the page comes to the block the pointer landed on wherever the
" page was left. It is sent straight rather than through the timer, since the
" throttled report of the same line follows within 150ms and would arrive as an
" ordinary move that the page is right to sit still for.
function! s:MdviewClicked() abort
  call job_start(
    \ ['python3', $MDVIEW_LINK, 'cursor', $MDVIEW_URL, string(line('.')), 'click'])
endfunction

augroup mdview
  autocmd!
  autocmd CursorMoved,CursorMovedI * call s:MdviewMoved()
augroup END

" The same gesture as the page's, so one hand does the same thing in either
" half: double click a line and the other half comes to it. A single click is
" left alone and puts the cursor where you pointed, as it does in any vim.
"
" Nothing is done about the cursor first, since the first click of the pair has
" already put it where you pointed, and the mapping is what keeps the second
" click from selecting the word under it. Handing vim a click of its own here
" instead would be counted as another click of the same gesture: vim would take
" the word after all, and the colon that follows would open a command line with
" the selection's range in it and the report would never be sent.
nnoremap <silent> <2-LeftMouse> :call <SID>MdviewClicked()<CR>

" Where the cursor starts, so the page marks a block from the first moment
" rather than waiting to be moved.
call s:MdviewReport(0)

" Where a clicked block lands. The page knows the source lines every block was
" built from and sends both ends of them, so the whole block is lit rather than
" the line it starts at. A pale ground for the eye to land on without hunting,
" and gone again once the eye has had it: long enough to be seen, short enough
" not to be read against. Set as a default, so that naming MdeusJump in .vimrc
" overrides it.
let s:linger = 1500
highlight default MdeusJump guifg=black guibg=#BDDFFF

" The window and the mark are told to the moment that puts it out, rather than
" left for it to find, since by the time it comes round the window it was lit in
" may not be the one in hand. A mark already gone is no matter. The names are
" plain ones, since a name held to this file cannot be called from the page and
" cannot be handed to a timer.
function! MdeusFadeMark(window, match, timer) abort
  silent! call matchdelete(a:match, a:window)
endfunction

function! MdeusJumpTo(first, last) abort
  " Only the block last clicked is ever lit. The mark from the click before
  " goes, and so does the moment still counting down for it, which would
  " otherwise come round and put out the light this click has just lit.
  if exists('w:mdeus_timer')
    silent! call timer_stop(w:mdeus_timer)
    unlet w:mdeus_timer
  endif
  if exists('w:mdeus_match')
    silent! call matchdelete(w:mdeus_match)
    unlet w:mdeus_match
  endif
  call cursor(a:first, 1)
  normal! zz
  let w:mdeus_match = matchadd(
    \ 'MdeusJump', '\%>' . (a:first - 1) . 'l\%<' . (a:last + 1) . 'l.\+')
  let w:mdeus_timer =
    \ timer_start(s:linger, function('MdeusFadeMark', [win_getid(), w:mdeus_match]))
endfunction
