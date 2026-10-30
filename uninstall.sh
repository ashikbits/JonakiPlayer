#!/usr/bin/env bash
# Jonaki for Linux - Uninstaller
# Removes Jonaki symlinks, desktop entries, and icons from ~/.local/

set -e

echo "=== Uninstalling Jonaki for Linux ==="

PURGE=false
for arg in "$@"; do
    if [ "$arg" = "--purge" ]; then
        PURGE=true
    fi
done

rm -f "$HOME/.local/bin/jonaki" 2>/dev/null || true
echo "[-] Removed $HOME/.local/bin/jonaki launcher"

rm -f "$HOME/.local/share/applications/jonaki.desktop" 2>/dev/null || true
echo "[-] Removed desktop entries"

rm -f "$HOME/.local/share/icons/hicolor/*/apps/jonaki.png" 2>/dev/null || true
echo "[-] Removed application icons"

# Clean up runtime IPC sockets and lockfiles
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    rm -f "$XDG_RUNTIME_DIR/jonaki_ipc.sock"*
fi
rm -f "/run/user/$(id -u)/jonaki_ipc.sock"* 2>/dev/null || true
if [ -d "/tmp/jonaki_$(id -u)" ]; then
    rm -rf "/tmp/jonaki_$(id -u)"
    echo "[-] Removed runtime directory /tmp/jonaki_$(id -u)"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

if [ "$PURGE" = true ]; then
    if [ -d "$HOME/.config/jonaki" ]; then
        rm -rf "$HOME/.config/jonaki"
        echo "[-] Purged configuration and database directory: $HOME/.config/jonaki"
    fi
else
    if [ -d "$HOME/.config/jonaki" ]; then
        echo "[*] Notice: User playback history, resume points, and settings remain in $HOME/.config/jonaki"
        echo "    To remove all configuration and database files, run: ./uninstall.sh --purge"
    fi
fi

echo "=== Uninstallation Complete ==="
