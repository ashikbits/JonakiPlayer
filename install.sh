#!/usr/bin/env bash
# Jonaki for Linux - System / User Installer
# Installs Jonaki desktop entry, launcher binary, and icons into ~/.local/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing Jonaki for Linux ==="

# 1. Ensure target directories exist
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"

# 2. Make launchers executable and link to ~/.local/bin/
chmod +x "$SCRIPT_DIR/bin/jonaki"
chmod +x "$SCRIPT_DIR/bin/potplayer"
ln -sf "$SCRIPT_DIR/bin/jonaki" "$HOME/.local/bin/jonaki"
ln -sf "$SCRIPT_DIR/bin/jonaki" "$HOME/.local/bin/potplayer"
echo "[+] Linked launcher to $HOME/.local/bin/jonaki (and alias potplayer)"

# 3. Install App Icon
cp -f "$SCRIPT_DIR/assets/logos/jonaki.png" "$HOME/.local/share/icons/hicolor/256x256/apps/jonaki.png"
cp -f "$SCRIPT_DIR/assets/logos/jonaki.png" "$HOME/.local/share/icons/hicolor/256x256/apps/potplayer.png"
echo "[+] Installed application icon to $HOME/.local/share/icons/hicolor/256x256/apps/jonaki.png"

# 4. Generate & Install Desktop Entry
DESKTOP_FILE="$HOME/.local/share/applications/jonaki.desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=Jonaki
GenericName=Multimedia Player
Comment=High-performance media player for Linux, inspired by PotPlayer
Exec=$HOME/.local/bin/jonaki %U
Icon=jonaki
Terminal=false
Type=Application
Categories=AudioVideo;Player;Recorder;
MimeType=video/mp4;video/x-matroska;video/avi;video/webm;video/quicktime;audio/mpeg;audio/flac;audio/ogg;
Keywords=video;audio;player;subtitles;jonaki;potplayer;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
echo "[+] Installed desktop entry to $DESKTOP_FILE"

# Optional legacy desktop file pointer
ln -sf "$DESKTOP_FILE" "$HOME/.local/share/applications/potplayer.desktop"

# 5. Update desktop and MIME databases
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "[+] Updated desktop database"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "[+] Updated icon cache"
fi

echo ""
echo "=== Installation Complete! ==="
echo "You can now run 'jonaki' (or 'potplayer') from your terminal or launch Jonaki from your Application Menu."
