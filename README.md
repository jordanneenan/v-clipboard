# V Clipboard Manager

**V** is a custom, modern clipboard manager built for Ubuntu (Wayland). It perfectly replicates the famous "hold to cycle, release to paste" behavior of Mac applications like Flycut or Jumpcut, while also providing a convenient system tray icon to view your entire clipboard history.

## Features
- **Flycut Behavior**: Hold `Ctrl + Shift`, tap `V` to cycle through your clipboard history, and release to instantly paste.
- **System Tray Icon**: A sleek "V" icon in your toolbar that drops down a list of your clipboard history.
- **Wayland Native**: Designed specifically for modern Linux distributions running Wayland (using `wl-clipboard`).

## Installation

### Prerequisites
V relies on standard Linux packages. The install script will automatically install:
- `wl-clipboard`
- `python3-evdev`
- `python3-gi` and GTK libraries
- `gir1.2-ayatanaappindicator3-0.1`

### Running the Installer
1. Clone or download this repository.
2. Open your terminal in the repository directory.
3. Run the installation script:
```bash
chmod +x install.sh
./install.sh
```

**IMPORTANT:** The installer will add your user account to the `input` group and update `udev` rules so V can globally monitor your keyboard. **You must log out and log back in (or reboot) for these changes to take effect.**

## Usage
Once installed and logged back in, V will automatically run in the background.

- **To cycle and paste**: Hold `Ctrl + Shift`. Tap `V` to cycle through your past clips. Release `Ctrl + Shift` to instantly paste the selected clip into your active window.
- **To view history**: Click the "V" icon in your system tray to see a dropdown of all recent clips. Click any clip to copy it to your clipboard.

## Troubleshooting
If `Ctrl+Shift+V` does not bring up the popup:
- Ensure you have logged out and logged back in after installation.
- Verify you are running Wayland (V is not designed for X11).
- Try starting the app manually from the terminal to check for errors by typing `v-clipboard`.
