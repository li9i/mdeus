#!/usr/bin/env bash

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"
PACKAGES=(python3-markdown-it python3-mdit-py-plugins python3-linkify-it
  python3-emoji python3-lxml python3-xlib python3-pil vim-gtk3)

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
if command -v apt-get >/dev/null 2>&1; then
  MISSING=()
  for package in "${PACKAGES[@]}"; do
    if [ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null)" \
        != installed ]; then
      MISSING+=("$package")
    fi
  done
  if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "This needs root."
    sudo apt-get install -y "${MISSING[@]}"
  else
    echo "  already installed"
  fi
else
  echo "No apt-get here, so install these yourself:"
  echo "  markdown-it-py, mdit-py-plugins, linkify-it-py, emoji, lxml,"
  echo "  python-xlib, pillow"
  echo "  and a vim built with +clientserver and a GUI"
fi

say "2. Links"
link "$REPO/bin/mdeus" "$BIN_DIR/mdeus"
link "$REPO/share/icons/hicolor/24x24/apps/mdeus.png" "$ICON_DIR/24x24/apps/mdeus.png"
link "$REPO/share/icons/hicolor/128x128/apps/mdeus.png" "$ICON_DIR/128x128/apps/mdeus.png"
link "$REPO/share/applications/mdeus.desktop" "$DESKTOP_DIR/mdeus.desktop"
link "$REPO/share/bash-completion/completions/mdeus" "$COMPLETION_DIR/mdeus"

say "3. The Open With menu"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR"
  echo "  markdown files now offer mdeus under Open With"
else
  echo "  update-desktop-database is not here, so the Open With entry waits for"
  echo "  whatever refreshes that cache on this machine"
fi

say "4. git difftool"
if command -v git >/dev/null 2>&1; then
  git config --global difftool.mdeus.cmd \
    'mdeus --diff "$LOCAL" "$REMOTE" "$MERGED"'
  echo "  git difftool -t mdeus now shows markdown changes in mdeus"
  echo "  plain git difftool still opens whatever it opened before"
else
  echo "  git is not here, so git difftool -t mdeus waits until it is and the"
  echo "  installer is run again"
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
