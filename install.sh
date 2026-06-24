#!/bin/bash

# V Clipboard Manager Installer
# Run this script to install V on your Ubuntu system.

echo "Installing V Clipboard Manager..."
echo "-----------------------------------"

# 1. Install dependencies
echo "Installing required dependencies (requires sudo)..."
sudo apt-get update
sudo apt-get install -y wl-clipboard python3-evdev python3-gi gir1.2-gtk-4.0 gir1.2-gtk-3.0 python3-gi-cairo gir1.2-ayatanaappindicator3-0.1

# 2. Add user to input group
echo "Adding user to input group for keyboard monitoring..."
sudo usermod -aG input $USER

# 3. Add udev rule for uinput
echo "Adding udev rule for uinput..."
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

# 4. Install files to ~/.local/share/v-clipboard
INSTALL_DIR="$HOME/.local/share/v-clipboard"
echo "Installing application files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/assets"
mkdir -p "$INSTALL_DIR/src"

cp -r assets/* "$INSTALL_DIR/assets/"
cp -r src/* "$INSTALL_DIR/src/"
chmod +x "$INSTALL_DIR/src/v_app.py"

# 5. Create Desktop entry for autostart
echo "Setting up autostart..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/v-clipboard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=V Clipboard
Comment=Flycut-style Wayland Clipboard Manager
Exec=bash -c "sleep 3 && $INSTALL_DIR/src/v_app.py"
Icon=$INSTALL_DIR/assets/v_icon.svg
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

cat > "$APPS_DIR/v-clipboard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=V Clipboard
Comment=Flycut-style Wayland Clipboard Manager
Exec=$INSTALL_DIR/src/v_app.py
Icon=$INSTALL_DIR/assets/v_icon.svg
Terminal=false
Categories=Utility;
EOF

# 6. Create start script in ~/.local/bin
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/v-clipboard" << EOF
#!/bin/bash
nohup $INSTALL_DIR/src/v_app.py > /dev/null 2>&1 &
EOF
chmod +x "$HOME/.local/bin/v-clipboard"

echo "-----------------------------------"
echo "Installation Complete!"
echo "IMPORTANT: You MUST log out and log back in (or reboot) for the keyboard permissions to take effect."
echo "After logging back in, V will start automatically. You can also start it manually by running 'v-clipboard' from your terminal."
