#!/usr/bin/env bash
#
# Install mdeus for one user, on Ubuntu or anything close enough to it.
#
#   git clone https://github.com/li9i/mdeus.git ~/mdeus
#   ~/mdeus/install.sh
#
# Nothing is copied. Five links are made into ~/.local, all of them pointing
# back at this checkout, so pulling the repository is the whole of updating and
# deleting the checkout after removing the links leaves nothing behind.
#
# Run it again whenever you like. Every step says what it found and does the
# least it can, so a second run changes nothing.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"

say() {
  printf '\n==> %s\n' "$1"
}

link() {
  local target="$1" name="$2"
  mkdir -p "$(dirname "$name")"
  ln -sfn "$target" "$name"
  echo "  $name -> $target"
}

echo "Installing mdeus from $REPO"

say "1. Packages"
# markdown-it parses, mdit-py-plugins draws the task lists and the footnotes,
# linkify-it finds the bare addresses and emoji answers the shortcodes. xlib
# draws the one window an editing session lives in and pil reads that window's
# icon off the disk. vim-gtk3 is a vim with a GUI and +clientserver, which is
# what the Edit toggle opens; Ubuntu's plain vim package has neither.
if command -v apt-get >/dev/null 2>&1; then
  echo "This needs root."
  sudo apt-get install -y python3-markdown-it python3-mdit-py-plugins \
    python3-linkify-it python3-emoji python3-xlib python3-pil vim-gtk3
else
  echo "No apt-get here, so install these yourself:"
  echo "  markdown-it-py, mdit-py-plugins, linkify-it-py, emoji, python-xlib, pillow"
  echo "  and a vim built with +clientserver and a GUI"
fi

say "2. Links"
link "$REPO/bin/mdeus" "$BIN_DIR/mdeus"
link "$REPO/share/icons/hicolor/24x24/apps/mdeus.png" "$ICON_DIR/24x24/apps/mdeus.png"
link "$REPO/share/icons/hicolor/128x128/apps/mdeus.png" "$ICON_DIR/128x128/apps/mdeus.png"
link "$REPO/share/applications/mdeus.desktop" "$DESKTOP_DIR/mdeus.desktop"
link "$REPO/share/bash-completion/completions/mdeus" "$COMPLETION_DIR/mdeus"

say "3. The Open With menu"
# The file manager reads the entry out of a cache rather than the directory, so
# an entry nobody has told it about does not appear.
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR"
  echo "  markdown files now offer mdeus under Open With"
else
  echo "  update-desktop-database is not here, so the Open With entry waits for"
  echo "  whatever refreshes that cache on this machine"
fi

say "Done"
case ":$PATH:" in
  *":$BIN_DIR:"*)
    echo "mdeus is on your path. Try: mdeus $REPO/README.md"
    ;;
  *)
    echo "$BIN_DIR is not on your path, so the command and its desktop entry"
    echo "will not resolve yet. Ubuntu's stock ~/.profile puts it there at login"
    echo "once the directory exists, and the directory exists now, so log out and"
    echo "back in. To use it before then:"
    echo
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac
