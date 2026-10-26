#!/usr/bin/env bash
# Jonaki for Linux - Uninstaller
# Removes Jonaki symlinks, desktop entries, and icons from ~/.local/

set -e

echo "=== Uninstalling Jonaki for Linux ==="

rm -f "$HOME/.local/bin/jonaki"
rm -f "$HOME/.local/bin/potplayer"
echo "[-] Removed $HOME/.local/bin/jonaki and potplayer symlinks"

rm -f "$HOME/.local/share/applications/jonaki.desktop"
rm -f "$HOME/.local/share/applications/potplayer.desktop"
echo "[-] Removed desktop entries"

rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/jonaki.png"
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/potplayer.png"
echo "[-] Removed application icons"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "=== Uninstallation Complete ==="
