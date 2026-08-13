#!/usr/bin/env bash

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"
CACHE_DIR="$HOME/.cache/mdeus"
STATE_DIR="$HOME/.config/mdeus"

say() {
  printf '\n==> %s\n' "$1"
}

unlink_ours() {
  local name="$1" target
  if [ ! -L "$name" ]; then
    if [ -e "$name" ]; then
      echo "  $name is not a link this installer made, so it stays"
    fi
    return
  fi
  target="$(readlink -f "$name" || true)"
  case "$target" in
    "$REPO"/*)
      rm -f "$name"
      echo "  removed $name"
      ;;
    *)
      echo "  $name points outside $REPO, so it stays"
      ;;
  esac
}

echo "Uninstalling mdeus linked from $REPO"

say "1. Links"
unlink_ours "$BIN_DIR/mdeus"
unlink_ours "$ICON_DIR/24x24/apps/mdeus.png"
unlink_ours "$ICON_DIR/128x128/apps/mdeus.png"
unlink_ours "$DESKTOP_DIR/mdeus.desktop"
unlink_ours "$COMPLETION_DIR/mdeus"

say "2. The Open With menu"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR"
  echo "  markdown files no longer offer mdeus under Open With"
else
  echo "  update-desktop-database is not here, so the Open With entry goes when"
  echo "  whatever refreshes that cache on this machine next runs"
fi

say "3. What a reading left behind"
for dir in "$STATE_DIR" "$CACHE_DIR"; do
  if [ -d "$dir" ]; then
    rm -rf "$dir"
    echo "  removed $dir"
  fi
done

say "Done"
echo "The checkout at $REPO is untouched, so delete it yourself when you want"
echo "it gone. The packages the installer fetched are untouched too, since"
echo "other things may want them:"
echo
echo "  python3-markdown-it  python3-mdit-py-plugins  python3-linkify-it"
echo "  python3-emoji  python3-xlib  python3-pil  vim-gtk3"
