#!/usr/bin/env python3
import threading
import subprocess
import time
import sys
import os
import signal
import asyncio
import json
import uuid
import hashlib
from evdev import InputDevice, categorize, ecodes as e, list_devices, UInput
import gi

gi.require_version('Gtk', '3.0')
try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except ValueError:
    print("Warning: AyatanaAppIndicator3 not found. Tray icon will not be available.")
    AppIndicator = None
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf

# Constants
CONFIG_DIR = os.path.expanduser("~/.config/v-clipboard")
CACHE_DIR = os.path.expanduser("~/.cache/v-clipboard/images")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Default Config
config = {
    "shortcut": "Ctrl+Shift+V",
    "start_index": 0,
    "history_limit": 0 # 0 means unlimited
}

clipboard_history = []
current_index = 0
ui_window = None
ui_label = None
ui_image = None
ui_stack = None
ui_index_label = None

is_active = False
cancel_paste = False
indicator = None
menu = None
ctrl_pressed = False
shift_pressed = False
alt_pressed = False
super_pressed = False

global_uinput = None

def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

def load_config():
    global config
    ensure_dirs()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as exc:
            print("Error loading config:", exc)
    save_config()

def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as exc:
        print("Error saving config:", exc)

def clear_history():
    global clipboard_history
    clipboard_history.clear()
    for f in os.listdir(CACHE_DIR):
        os.remove(os.path.join(CACHE_DIR, f))
    GLib.idle_add(build_menu)

def get_icon_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, 'assets', 'v_icon.svg')
    if os.path.exists(path):
        return path
    return 'edit-paste'

# Preferences Dialog
class PrefsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="V Preferences")
        self.set_default_size(350, -1)
        self.set_border_width(20)
        self.set_wmclass("v-clipboard-prefs", "v-clipboard-prefs")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)

        # Shortcut
        hbox1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox1.pack_start(Gtk.Label(label="Shortcut:"), False, False, 0)
        self.shortcut_combo = Gtk.ComboBoxText()
        self.shortcut_combo.append_text("Ctrl+Shift+V")
        self.shortcut_combo.append_text("Super+V")
        self.shortcut_combo.append_text("Alt+V")
        self.shortcut_combo.set_active(0)
        for i, text in enumerate(["Ctrl+Shift+V", "Super+V", "Alt+V"]):
            if text == config["shortcut"]:
                self.shortcut_combo.set_active(i)
                break
        hbox1.pack_end(self.shortcut_combo, False, False, 0)
        main_box.pack_start(hbox1, False, False, 0)

        # Start Index
        hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox2.pack_start(Gtk.Label(label="Start on 2nd Item:"), False, False, 0)
        self.start_switch = Gtk.Switch()
        self.start_switch.set_active(config["start_index"] == 1)
        self.start_switch.set_valign(Gtk.Align.CENTER)
        hbox2.pack_end(self.start_switch, False, False, 0)
        main_box.pack_start(hbox2, False, False, 0)

        # History Limit
        hbox3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox3.pack_start(Gtk.Label(label="History Limit (0=Unlimited):"), False, False, 0)
        adj = Gtk.Adjustment(value=config["history_limit"], lower=0, upper=10000, step_increment=10)
        self.limit_spin = Gtk.SpinButton(adjustment=adj, numeric=True)
        self.limit_spin.set_valign(Gtk.Align.CENTER)
        hbox3.pack_end(self.limit_spin, False, False, 0)
        main_box.pack_start(hbox3, False, False, 0)

        # Native Button Box
        btn_box = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_layout(Gtk.ButtonBoxStyle.EXPAND)
        btn_box.set_spacing(15)
        btn_box.set_margin_top(10)

        clear_btn = Gtk.Button(label="Clear History")
        clear_btn.connect("clicked", self.on_clear_clicked)

        save_btn = Gtk.Button(label="Save & Apply")
        save_btn.connect("clicked", self.on_save_clicked)

        btn_box.add(clear_btn)
        btn_box.add(save_btn)

        main_box.pack_start(btn_box, False, False, 0)

        self.add(main_box)
        self.show_all()

    def on_clear_clicked(self, widget):
        clear_history()

    def on_save_clicked(self, widget):
        config["shortcut"] = self.shortcut_combo.get_active_text()
        config["start_index"] = 1 if self.start_switch.get_active() else 0
        config["history_limit"] = int(self.limit_spin.get_value())
        save_config()
        self.destroy()

def show_preferences(_):
    PrefsWindow()

def build_menu():
    global menu
    if menu:
        menu.destroy()
    menu = Gtk.Menu()
    
    if not clipboard_history:
        item = Gtk.MenuItem(label="Clipboard is empty")
        item.set_sensitive(False)
        menu.append(item)
    else:
        for i, item_data in enumerate(clipboard_history):
            if item_data["type"] == "text":
                text = item_data["content"]
                display_text = text[:40] + "..." if len(text) > 40 else text
                display_text = display_text.replace('\n', ' ')
            else:
                display_text = "[Image]"
            item = Gtk.MenuItem(label=f"{i+1}. {display_text}")
            item.connect('activate', on_menu_item_selected, item_data)
            menu.append(item)
            
    menu.append(Gtk.SeparatorMenuItem())
    
    prefs_item = Gtk.MenuItem(label="Preferences")
    prefs_item.connect('activate', show_preferences)
    menu.append(prefs_item)
    
    quit_item = Gtk.MenuItem(label="Quit V")
    quit_item.connect('activate', on_quit)
    menu.append(quit_item)
    menu.show_all()
    if indicator:
        indicator.set_menu(menu)

def on_menu_item_selected(widget, item_data):
    if item_data["type"] == "text":
        subprocess.run(['wl-copy'], input=item_data["content"], text=True)
    elif item_data["type"] == "image":
        subprocess.run(f"wl-copy -t image/png < '{item_data['content']}'", shell=True)
    
    if item_data in clipboard_history:
        clipboard_history.remove(item_data)
    clipboard_history.insert(0, item_data)
    GLib.idle_add(build_menu)

def on_quit(_):
    Gtk.main_quit()
    sys.exit(0)

def build_ui_list():
    # Clear existing rows
    for row in ui_listbox.get_children():
        ui_listbox.remove(row)
        
    for item in clipboard_history:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        
        # Icon
        icon = Gtk.Image()
        if item["type"] == "text":
            icon.set_from_icon_name("text-x-generic", Gtk.IconSize.LARGE_TOOLBAR)
        else:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(item["content"], 50, 50, True)
                icon.set_from_pixbuf(pixbuf)
            except:
                icon.set_from_icon_name("image-x-generic", Gtk.IconSize.LARGE_TOOLBAR)
        
        box.pack_start(icon, False, False, 0)
        
        # Content snippet
        lbl = Gtk.Label()
        lbl.set_xalign(0.0)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(60)
        
        if item["type"] == "text":
            text = item["content"].replace('\n', ' ')
            lbl.set_text(text)
        else:
            lbl.set_text("[Image]")
        
        box.pack_start(lbl, True, True, 0)
        row.add(box)
        ui_listbox.add(row)
    
    ui_listbox.show_all()

def center_scroll(row):
    adj = ui_scrolled_window.get_vadjustment()
    row_alloc = row.get_allocation()
    page_size = adj.get_page_size()
    target_value = row_alloc.y - (page_size / 2) + (row_alloc.height / 2)
    target_value = max(adj.get_lower(), min(target_value, adj.get_upper() - page_size))
    adj.set_value(target_value)
    return False

def update_ui():
    if not is_active or not clipboard_history:
        return
        
    row = ui_listbox.get_row_at_index(current_index)
    if row:
        ui_listbox.select_row(row)
        # Delay centering slightly to ensure layout is calculated if just shown
        GLib.idle_add(center_scroll, row)

def show_ui():
    build_ui_list()
    ui_window.show_all()
    update_ui()

def hide_ui():
    ui_window.hide()

def on_draw(widget, cr):
    cr.set_source_rgba(0, 0, 0, 0)
    cr.set_operator(1)
    cr.paint()
    return False

def setup_ui():
    global ui_window, ui_listbox, ui_scrolled_window
    ui_window = Gtk.Window(type=Gtk.WindowType.POPUP)
    ui_window.set_decorated(False)
    ui_window.set_keep_above(True)
    ui_window.set_position(Gtk.WindowPosition.CENTER)
    ui_window.set_wmclass("v-clipboard", "v-clipboard")
    
    screen = ui_window.get_screen()
    visual = screen.get_rgba_visual()
    if visual and screen.is_composited():
        ui_window.set_visual(visual)
    
    ui_window.set_app_paintable(True)
    ui_window.connect("draw", on_draw)
    ui_window.set_size_request(600, 450)
    
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.set_name("FlycutBox")
    
    css = b"""
    #FlycutBox {
        background-color: rgba(0, 0, 0, 0.85);
        border-radius: 16px;
    }
    list {
        background: transparent;
    }
    row {
        color: white;
        padding: 5px 15px;
        background: transparent;
        border-radius: 8px;
        margin: 2px 10px;
    }
    row:selected {
        background-color: rgba(255, 255, 255, 0.2);
    }
    label {
        color: white;
        font-size: 16px;
    }
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    
    # Inner layout
    ui_scrolled_window = Gtk.ScrolledWindow()
    ui_scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    ui_scrolled_window.set_margin_top(15)
    ui_scrolled_window.set_margin_bottom(15)
    
    ui_listbox = Gtk.ListBox()
    ui_listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
    ui_scrolled_window.add(ui_listbox)
    
    box.pack_start(ui_scrolled_window, True, True, 0)
    
    ui_window.add(box)

def setup_indicator():
    global indicator
    if AppIndicator is None:
        return
    indicator = AppIndicator.Indicator.new(
        "v-clipboard-app",
        get_icon_path(),
        AppIndicator.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    build_menu()

def fetch_clipboard_once():
    global current_index
    time.sleep(0.15) # Wait for target app to write
    try:
        types_res = subprocess.run(['wl-paste', '--list-types'], stdout=subprocess.PIPE, text=True, timeout=1)
        types = types_res.stdout.splitlines()
        
        text_res = subprocess.run(['wl-paste', '--no-newline'], stdout=subprocess.PIPE, text=True, timeout=1)
        fallback_text = text_res.stdout if text_res.returncode == 0 else ""
        
        is_text = False
        for t in types:
            if 'text/plain' in t or 'STRING' in t:
                is_text = True
                break
            if 'image/' in t:
                break
                
        if is_text and fallback_text:
            item = {"type": "text", "content": fallback_text}
            if not clipboard_history or clipboard_history[0] != item:
                clipboard_history[:] = [x for x in clipboard_history if not (x["type"] == "text" and x["content"] == fallback_text)]
                clipboard_history.insert(0, item)
                
                if config["history_limit"] > 0 and len(clipboard_history) > config["history_limit"]:
                    popped = clipboard_history.pop()
                    if popped["type"] == "image":
                        try: os.remove(popped["content"])
                        except: pass
                GLib.idle_add(build_menu)
                if is_active:
                    current_index = 0
                    GLib.idle_add(update_ui)
        else:
            handled = False
            if 'image/png' in types or 'image/jpeg' in types:
                img_res = subprocess.run(['wl-paste', '-t', 'image/png'], stdout=subprocess.PIPE, timeout=2)
                if len(img_res.stdout) > 0:
                    img_size = len(img_res.stdout)
                    final_path = os.path.join(CACHE_DIR, f"{img_size}.png")
                    with open(final_path, 'wb') as f:
                        f.write(img_res.stdout)
                        
                    item = {"type": "image", "content": final_path}
                    if not clipboard_history or clipboard_history[0].get("content") != final_path:
                        clipboard_history[:] = [x for x in clipboard_history if not (x["type"] == "image" and x["content"] == final_path)]
                        clipboard_history.insert(0, item)
                        handled = True
                        
                        if config["history_limit"] > 0 and len(clipboard_history) > config["history_limit"]:
                            popped = clipboard_history.pop()
                            if popped["type"] == "image":
                                try: os.remove(popped["content"])
                                except: pass
                        GLib.idle_add(build_menu)
                        if is_active:
                            current_index = 0
                            GLib.idle_add(update_ui)
            
            if not handled and fallback_text:
                item = {"type": "text", "content": fallback_text}
                if not clipboard_history or clipboard_history[0] != item:
                    clipboard_history[:] = [x for x in clipboard_history if not (x["type"] == "text" and x["content"] == fallback_text)]
                    clipboard_history.insert(0, item)
                    
                    if config["history_limit"] > 0 and len(clipboard_history) > config["history_limit"]:
                        popped = clipboard_history.pop()
                        if popped["type"] == "image":
                            try: os.remove(popped["content"])
                            except: pass
                    GLib.idle_add(build_menu)
                    if is_active:
                        current_index = 0
                        GLib.idle_add(update_ui)
    except Exception:
        pass

def paste_current():
    if not clipboard_history:
        return
    item_data = clipboard_history[current_index]
    
    if item_data["type"] == "text":
        subprocess.run(['wl-copy'], input=item_data["content"], text=True)
    elif item_data["type"] == "image":
        subprocess.run(f"wl-copy -t image/png < '{item_data['content']}'", shell=True)
    
    time.sleep(0.05)
    try:
        global_uinput.write(e.EV_KEY, e.KEY_LEFTCTRL, 1)
        global_uinput.write(e.EV_KEY, e.KEY_V, 1)
        global_uinput.write(e.EV_KEY, e.KEY_V, 0)
        global_uinput.write(e.EV_KEY, e.KEY_LEFTCTRL, 0)
        global_uinput.syn()
    except Exception as exc:
        print(f"Error simulating paste: {exc}")

async def monitor_device(device):
    global is_active, current_index, ctrl_pressed, shift_pressed, alt_pressed, super_pressed, global_uinput, cancel_paste
    
    try:
        device.grab()
    except Exception as exc:
        print(f"Could not grab {device.name}: {exc}")
        return

    try:
        async for event in device.async_read_loop():
            if event.type != e.EV_KEY:
                global_uinput.write_event(event)
                continue
                
            swallow = False
            
            # Modifier tracking
            if event.value in (1, 2):
                if event.code in (e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL): ctrl_pressed = True
                elif event.code in (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT): shift_pressed = True
                elif event.code in (e.KEY_LEFTALT, e.KEY_RIGHTALT): alt_pressed = True
                elif event.code in (e.KEY_LEFTMETA, e.KEY_RIGHTMETA): super_pressed = True
            elif event.value == 0:
                if event.code in (e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL): ctrl_pressed = False
                elif event.code in (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT): shift_pressed = False
                elif event.code in (e.KEY_LEFTALT, e.KEY_RIGHTALT): alt_pressed = False
                elif event.code in (e.KEY_LEFTMETA, e.KEY_RIGHTMETA): super_pressed = False

            # Check if active combo is held
            combo = config["shortcut"]
            is_combo_held = False
            if combo == "Ctrl+Shift+V" and ctrl_pressed and shift_pressed: is_combo_held = True
            elif combo == "Alt+V" and alt_pressed: is_combo_held = True
            elif combo == "Super+V" and super_pressed: is_combo_held = True
            
            if event.value in (1, 2):
                if ctrl_pressed and event.code in (e.KEY_C, e.KEY_X, e.KEY_INSERT):
                    threading.Thread(target=fetch_clipboard_once, daemon=True).start()
                    
                if event.code == e.KEY_ESC and is_active:
                    swallow = True
                    is_active = False
                    cancel_paste = True
                    GLib.idle_add(hide_ui)
                if event.code == e.KEY_V:
                    if is_combo_held:
                        swallow = True
                        if event.value == 1:
                            if not is_active:
                                is_active = True
                                cancel_paste = False
                                current_index = config["start_index"]
                                if current_index >= len(clipboard_history): current_index = 0
                                GLib.idle_add(show_ui)
                                # Fetch clipboard in background to catch any mouse copies since last check
                                threading.Thread(target=fetch_clipboard_once, daemon=True).start()
                            else:
                                current_index = (current_index + 1) % len(clipboard_history) if clipboard_history else 0
                                GLib.idle_add(update_ui)
            elif event.value == 0:
                if event.code == e.KEY_V:
                    if is_active:
                        swallow = True
                elif event.code == e.KEY_ESC and cancel_paste:
                    swallow = True
                
                if is_active and not is_combo_held:
                    is_active = False
                    GLib.idle_add(hide_ui)
                    if not cancel_paste:
                        threading.Thread(target=paste_current).start()
            
            if not swallow:
                global_uinput.write_event(event)

    except Exception as exc:
        print(f"Device {device.name} error: {exc}")
    finally:
        try:
            device.ungrab()
        except:
            pass

def key_listener():
    global global_uinput
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    devices = [InputDevice(path) for path in list_devices()]
    keyboard_devices = []
    all_keys = set()
    
    for d in devices:
        caps = d.capabilities()
        if e.EV_KEY in caps and e.KEY_V in caps[e.EV_KEY]:
            # Critical Fix: Do not grab mice, touchpads, or combined receiver mouse nodes
            if e.EV_REL in caps or e.EV_ABS in caps:
                continue
            if d.name != "V-Clipboard-Virtual-Keyboard":
                keyboard_devices.append(d)
                for key in caps[e.EV_KEY]:
                    all_keys.add(key)
            
    if not keyboard_devices:
        print("Could not find any keyboard devices!")
        return
        
    global_uinput = UInput({e.EV_KEY: list(all_keys)}, name="V-Clipboard-Virtual-Keyboard")
        
    for d in keyboard_devices:
        print(f"Listening and grabbing {d.name}")
        asyncio.ensure_future(monitor_device(d), loop=loop)
        
    loop.run_forever()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    load_config()
    
    # Watcher thread is replaced by event-driven key hooks
    
    listener_thread = threading.Thread(target=key_listener, daemon=True)
    listener_thread.start()
    
    setup_ui()
    setup_indicator()
    Gtk.main()
