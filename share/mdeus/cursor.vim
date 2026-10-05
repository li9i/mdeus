let s:ends = 0
let s:pending = 0

function! s:MdeusReport(timer) abort
  let s:pending = 0
  call job_start(
    \ ['python3', $MDEUS_LINK, 'cursor', $MDEUS_URL, string(line('.')), s:MdeusShare()])
endfunction

function! s:MdeusMoved() abort
  if s:pending
    return
  endif
  let s:pending = 1
  call timer_start(150, function('s:MdeusReport'))
endfunction

function! s:MdeusClicked() abort
  let word = expand('<cword>')
  let earlier = map(filter(s:MdeusMatches(word, 1, line('.')),
    \ {_, found -> found[0] <# line('.') || found[2] <# col('.')}),
    \ {_, found -> found[0]})
  call job_start(['python3', $MDEUS_LINK, 'cursor', $MDEUS_URL,
    \ string(line('.')), s:MdeusShare(), 'click', word, json_encode(earlier)])
endfunction

function! s:MdeusMatches(word, first, last) abort
  if a:word ==# ''
    return []
  endif
  let pattern = '\C\V\k\@<!' . escape(a:word, '\') . '\k\@!'
  let found = []
  for line in range(a:first, a:last)
    let text = getline(line)
    let [at, upto] = matchstrpos(text, pattern)[1:]
    while at >=# 0
      call add(found, [line, at, upto])
      let [at, upto] = matchstrpos(text, pattern, upto)[1:]
    endwhile
  endfor
  return found
endfunction

function! s:MdeusShare() abort
  let height = winheight(0)
  return height <=# 0 ? '0' : string((winline() - 1) * 1.0 / height)
endfunction

function! s:MdeusEnds(command) abort
  return a:command =~# '^\s*\%(wq\|x\%[it]\|exi\%[t]\)!\=$'
endfunction

function! s:MdeusEnding() abort
  call system(
    \ 'python3 ' . shellescape($MDEUS_LINK) . ' ending ' . shellescape($MDEUS_URL))
endfunction

augroup mdeus
  autocmd!
  autocmd CursorMoved,CursorMovedI * call s:MdeusMoved()
  autocmd CmdlineLeave :
    \ let s:ends = !get(v:event, 'abort', 0) && s:MdeusEnds(getcmdline())
  autocmd FileChangedShell * call s:MdeusChanged()
  autocmd VimLeavePre * if s:ends | call s:MdeusEnding() | endif
augroup END

nnoremap <silent> <2-LeftMouse> :call <SID>MdeusClicked()<CR>
nnoremap <silent> <CR> :call <SID>MdeusClicked()<CR>

call s:MdeusReport(0)

let s:mine = 0
let s:claim = 2.0

function! s:MdeusFresh() abort
  if s:mine <=# 0
    return 0
  endif
  return reltimefloat(reltime()) - s:mine <# s:claim
endfunction

function! s:MdeusChanged() abort
  let unsaved = getbufvar(str2nr(expand('<abuf>')), '&modified')
  let v:fcs_choice = s:MdeusFresh() && !unsaved ? 'reload' : 'ask'
  let s:mine = 0
endfunction

function! MdeusGo() abort
  if getbufinfo({'bufmodified': 1}) != []
    echohl WarningMsg
    echo 'mdeus: something here is unwritten'
    echohl None
    return
  endif
  qa
endfunction

function! MdeusMine(writing) abort
  let s:mine = a:writing ? reltimefloat(reltime()) : 0
  return 1
endfunction

let s:look = 1000

function! s:MdeusLook(timer) abort
  checktime
endfunction

call timer_start(s:look, function('s:MdeusLook'), {'repeat': -1})

let s:linger = 1500
highlight default MdeusJump guifg=black guibg=#BDDFFF
highlight default MdeusWord guifg=black guibg=#5CA8FF

function! MdeusFadeMark(window, marks, timer) abort
  for mark in a:marks
    silent! call matchdelete(mark, a:window)
  endfor
endfunction

function! MdeusJumpTo(first, last, word, nth) abort
  if exists('w:mdeus_timer')
    silent! call timer_stop(w:mdeus_timer)
    unlet w:mdeus_timer
  endif
  if exists('w:mdeus_marks')
    call MdeusFadeMark(win_getid(), w:mdeus_marks, 0)
    unlet w:mdeus_marks
  endif
  let [line, at, upto] = get(s:MdeusMatches(list2str(a:word), a:first, a:last),
    \ a:nth, [a:first, 0, 0])
  call cursor(line, at + 1)
  normal! zz
  let w:mdeus_marks = [
    \ matchadd('MdeusJump',
    \   '\%>' . (a:first - 1) . 'l\%<' . (a:last + 1) . 'l.\+'),
    \ matchaddpos('MdeusWord', [[line, at + 1, upto - at]], 11)]
  let w:mdeus_timer = timer_start(s:linger,
    \ function('MdeusFadeMark', [win_getid(), w:mdeus_marks]))
endfunction

function! MdeusTick(line, done, path) abort
  if mode(1) =~# '^r'
    return 0
  endif
  if expand('%:p') !=# a:path
    return 0
  endif
  let text = getline(a:line)
  if text !~# '^[ \t]*\%([-*+]\|\d\+[.)]\)[ \t]\+\[[ xX]\]'
    return 0
  endif
  call setline(a:line, substitute(text, '\[[ xX]\]', a:done ? '[x]' : '[ ]', ''))
  return 1
endfunction
