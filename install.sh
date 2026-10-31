#!/usr/bin/env bash
# Jonaki for Linux - System / User Installer
# Installs Jonaki desktop entry, launcher binary, and icons into ~/.local/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing Jonaki for Linux ==="

# 0. Check essential runtime dependencies
MISSING_DEPS=()
if ! command -v python3 >/dev/null 2>&1; then
    MISSING_DEPS+=("python3")
fi
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" >/dev/null 2>&1; then
    MISSING_DEPS+=("python3-gi / PyGObject (Gtk 3.0)")
fi
if ! python3 -c "import cairo" >/dev/null 2>&1; then
    MISSING_DEPS+=("python3-cairo")
fi
if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "[!] Notice: The following dependencies were not detected in current Python environment:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "    - $dep"
    done
    echo "    On Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 ffmpeg"
    echo "    On Fedora:        sudo dnf install python3-gobject gtk3 ffmpeg"
    echo "    On Arch:          sudo pacman -S python-gobject gtk3 ffmpeg"
    echo ""
fi

# 1. Ensure target directories exist
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"

# 2. Make launcher executable and link to ~/.local/bin/
chmod +x "$SCRIPT_DIR/bin/jonaki"
ln -sf "$SCRIPT_DIR/bin/jonaki" "$HOME/.local/bin/jonaki"
ln -sf "$SCRIPT_DIR/bin/jonaki" "$HOME/.local/bin/potplayer"
echo "[+] Linked launcher to $HOME/.local/bin/jonaki and $HOME/.local/bin/potplayer"

# 3. Install App Icon in multi-resolution hierarchy (16x16 to 512x512)
python3 -c "
import os
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

src = '$SCRIPT_DIR/assets/logos/jonaki.png'
base_icon_dir = os.path.expanduser('~/.local/share/icons/hicolor')
sizes = [16, 24, 32, 48, 64, 128, 256, 512]
for s in sizes:
    target_dir = os.path.join(base_icon_dir, f'{s}x{s}', 'apps')
    os.makedirs(target_dir, exist_ok=True)
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(src, s, s, True)
        pb.savev(os.path.join(target_dir, 'jonaki.png'), 'png', [], [])
    except Exception as e:
        pass
" 2>/dev/null || {
    # Fallback to direct 256x256 copy if GdkPixbuf python binding is absent
    mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
    cp -f "$SCRIPT_DIR/assets/logos/jonaki.png" "$HOME/.local/share/icons/hicolor/256x256/apps/jonaki.png"
}
echo "[+] Installed multi-resolution application icons to $HOME/.local/share/icons/hicolor/"

# 4. Generate & Install Desktop Entry
DESKTOP_FILE="$HOME/.local/share/applications/jonaki.desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=Jonaki
GenericName=Multimedia Player
Comment=High-performance media player for Linux
Exec="$HOME/.local/bin/jonaki" %U
Icon=jonaki
Terminal=false
Type=Application
StartupWMClass=jonaki
Categories=AudioVideo;Player;Recorder;
MimeType=video/mp4;video/x-matroska;video/avi;video/webm;video/quicktime;audio/mpeg;audio/flac;audio/ogg;
Keywords=video;audio;player;subtitles;jonaki;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
echo "[+] Installed desktop entry to $DESKTOP_FILE"

# 5. Update desktop, icon, and KDE system configuration databases
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "[+] Updated desktop database"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "[+] Updated icon cache"
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 2>/dev/null || true
    echo "[+] Updated KDE Sycoca6 cache"
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
    kbuildsycoca5 2>/dev/null || true
    echo "[+] Updated KDE Sycoca5 cache"
fi

echo ""
echo "=== Installation Complete! ==="
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Warning: Add $HOME/.local/bin to your PATH to run jonaki from terminal."
fi
echo "You can now run 'jonaki' from your terminal or launch Jonaki from your Application Menu."
