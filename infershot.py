import ctypes
import io
import json
import math
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import ImageDraw, ImageEnhance, ImageFont, ImageGrab, ImageTk


APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
PID_FILE = Path(__file__).with_suffix(".pid")
LOG_FILE = Path(__file__).with_suffix(".log")

DEFAULT_CONFIG = {
    "save_path": r"C:\SCREENSHOTS",
    "format": "jpg",
    "quality": 95,
    "filename_mask": "ScreenShot-{nnn}",
    "copy_to_clipboard": True,
    "hotkeys": {
        "rectangle": "PrintScreen",
        "fullscreen": "Ctrl+PrintScreen",
        "line_start": "Ctrl+LeftMouse",
        "line_finish": "LeftMouse",
        "arrow_start": "Ctrl+RightMouse",
        "arrow_finish": "RightMouse",
        "save": "Enter",
        "cancel": "Escape"
    }
}

CONFIG = {}
FILE_RE = None

VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SNAPSHOT = 0x2C

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
HC_ACTION = 0

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MONITOR_DEFAULTTONEAREST = 2
CF_DIB = 8
GMEM_MOVEABLE = 0x0002


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelKeyboardProc, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_long
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

try:
    user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
except AttributeError:
    pass


def log(message):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"{stamp} {message}\n")


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    config = DEFAULT_CONFIG | raw
    config["hotkeys"] = DEFAULT_CONFIG["hotkeys"] | raw.get("hotkeys", {})
    config["format"] = str(config["format"]).lower().lstrip(".")
    if config["format"] == "jpeg":
        config["format"] = "jpg"
    config["quality"] = max(1, min(100, int(config["quality"])))
    config["copy_to_clipboard"] = bool(config["copy_to_clipboard"])
    return config


def apply_config():
    global CONFIG, FILE_RE
    CONFIG = load_config()
    mask_pattern = re.escape(CONFIG["filename_mask"]).replace(re.escape("{nnn}"), r"(\d{3})")
    extension_pattern = re.escape(CONFIG["format"])
    if CONFIG["format"] == "jpg":
        extension_pattern = r"jpe?g"
    FILE_RE = re.compile(rf"^{mask_pattern}\.{extension_pattern}$", re.IGNORECASE)
    log(f"config loaded {CONFIG_FILE}")


def key_combo_state():
    modifiers = set()
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL)):
        modifiers.add("ctrl")
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT)):
        modifiers.add("shift")
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (VK_MENU, VK_LMENU, VK_RMENU)):
        modifiers.add("alt")
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (VK_LWIN, VK_RWIN)):
        modifiers.add("win")
    return modifiers


def parse_hotkey(value):
    parts = [part.strip().lower() for part in str(value).replace(" ", "").split("+") if part.strip()]
    aliases = {
        "control": "ctrl",
        "prtscr": "printscreen",
        "prtsc": "printscreen",
        "snapshot": "printscreen",
        "windows": "win",
    }
    normalized = {aliases.get(part, part) for part in parts}
    if "printscreen" not in normalized:
        raise ValueError(f"Only PrintScreen hotkeys are supported – {value}")
    normalized.remove("printscreen")
    return normalized


def hotkey_matches(name, modifiers):
    configured = CONFIG.get("hotkeys", {}).get(name, "")
    return modifiers == parse_hotkey(configured)


def selector_binding(value):
    aliases = {
        "control": "ctrl",
        "lmb": "leftmouse",
        "mouse1": "leftmouse",
        "rmb": "rightmouse",
        "mouse3": "rightmouse",
        "return": "enter",
        "esc": "escape",
    }
    parts = [part.strip().lower() for part in str(value).replace(" ", "").split("+") if part.strip()]
    parts = [aliases.get(part, part) for part in parts]
    modifiers = [part for part in parts if part in {"ctrl", "shift", "alt"}]
    keys = [part for part in parts if part not in {"ctrl", "shift", "alt"}]
    if len(keys) != 1 or len(modifiers) != len(set(modifiers)):
        raise ValueError(f"Invalid selector hotkey – {value}")

    modifier_names = {"ctrl": "Control", "shift": "Shift", "alt": "Alt"}
    prefix = "-".join(modifier_names[name] for name in modifiers)
    key = keys[0]
    if key == "leftmouse":
        event = "ButtonPress-1"
    elif key == "rightmouse":
        event = "ButtonPress-3"
    elif key == "enter":
        event = "Return"
    elif key == "escape":
        event = "Escape"
    elif len(key) == 1:
        event = f"KeyPress-{key}"
    else:
        raise ValueError(f"Unsupported selector hotkey – {value}")
    return f"<{prefix + '-' if prefix else ''}{event}>"


def enable_dpi_awareness():
    try:
        # Per-monitor v2 keeps Tk coordinates and screenshots in physical pixels.
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            log("dpi awareness: per-monitor-v2")
            return
    except Exception as error:
        log(f"dpi awareness context failed: {error!r}")

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        result = shcore.SetProcessDpiAwareness(2)
        log(f"dpi awareness: per-monitor result={result}")
        return
    except Exception as error:
        log(f"dpi awareness shcore failed: {error!r}")

    try:
        user32.SetProcessDPIAware()
        log("dpi awareness: system")
    except Exception as error:
        log(f"dpi awareness legacy failed: {error!r}")


def get_virtual_screen():
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, left + width, top + height


def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def monitor_bbox_at_cursor():
    point = POINT(*get_cursor_pos())
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return get_virtual_screen()
    rect = info.rcMonitor
    return rect.left, rect.top, rect.right, rect.bottom


def next_path():
    capture_dir = Path(CONFIG["save_path"])
    capture_dir.mkdir(parents=True, exist_ok=True)
    highest = 0
    for item in capture_dir.iterdir():
        if not item.is_file():
            continue
        match = FILE_RE.match(item.name)
        if match:
            highest = max(highest, int(match.group(1)))

    number = highest + 1
    while True:
        stem = CONFIG["filename_mask"].replace("{nnn}", f"{number:03d}")
        path = capture_dir / f"{stem}.{CONFIG['format']}"
        if not path.exists():
            return path
        number += 1


def save_capture(image):
    path = next_path()
    image = image.convert("RGB")
    if CONFIG["format"] == "png":
        image.save(path, "PNG", optimize=True)
    else:
        image.save(path, "JPEG", quality=CONFIG["quality"], optimize=True)
    if CONFIG["copy_to_clipboard"]:
        copy_image_to_clipboard(image)
    log(f"saved {path}")
    return path


def copy_image_to_clipboard(image):
    output = io.BytesIO()
    image.save(output, "BMP")
    data = output.getvalue()[14:]
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        log("clipboard failed: GlobalAlloc")
        return

    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        log("clipboard failed: GlobalLock")
        return
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        log("clipboard failed: OpenClipboard")
        return
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_DIB, handle):
            log("clipboard failed: SetClipboardData")
            return
        log("clipboard updated")
    finally:
        user32.CloseClipboard()


def capture_monitor():
    vleft, vtop, _vright, _vbottom = get_virtual_screen()
    left, top, right, bottom = monitor_bbox_at_cursor()
    desktop = ImageGrab.grab(all_screens=True)
    crop_box = (left - vleft, top - vtop, right - vleft, bottom - vtop)
    log(f"monitor capture bbox={left},{top},{right},{bottom} virtual_origin={vleft},{vtop} desktop={desktop.size[0]}x{desktop.size[1]} crop={crop_box}")
    image = desktop.crop(crop_box)
    path = save_capture(image)
    print(f"Saved fullscreen: {path}", flush=True)


class RectSelector:
    HANDLE = 10
    MIN_SIZE = 8
    ANNOTATION_COLOR = "#ff2020"
    ANNOTATION_WIDTH = 5
    ARROW_HEAD_LENGTH = 27
    ARROW_HEAD_ANGLE = math.radians(28)
    TOOLBAR_TOOLS = ("line", "arrow", "freehand", "text")
    TOOLBAR_BUTTON = 34
    TOOLBAR_GAP = 4
    TOOLBAR_PAD = 6
    TOOLBAR_MARGIN = 8
    TEXT_SIZE = 22

    def __init__(self, root):
        self.root = root
        self.vleft, self.vtop, self.vright, self.vbottom = get_virtual_screen()
        self.width = self.vright - self.vleft
        self.height = self.vbottom - self.vtop
        self.original = ImageGrab.grab(all_screens=True)
        if self.original.size != (self.width, self.height):
            log(f"overlay size mismatch metrics={self.width}x{self.height} image={self.original.size[0]}x{self.original.size[1]}")
            self.width, self.height = self.original.size
            self.vright = self.vleft + self.width
            self.vbottom = self.vtop + self.height
        else:
            log(f"overlay size metrics={self.width}x{self.height} image={self.original.size[0]}x{self.original.size[1]}")
        self.dimmed = ImageEnhance.Brightness(self.original).enhance(0.48)
        self.photo = ImageTk.PhotoImage(self.dimmed)

        self.rect = None
        self.mode = "new"
        self.anchor = None
        self.start_rect = None
        self.annotations = []
        self.pending_annotation = None
        self.pending_annotation_id = None
        self.active_tool = None
        self.toolbar_hitboxes = []
        self.freehand_points = None
        self.freehand_id = None
        self.text_entry = None
        self.text_window_id = None
        self.text_origin = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{self.width}x{self.height}+{self.vleft}+{self.vtop}")
        self.window.focus_force()

        self.canvas = tk.Canvas(self.window, width=self.width, height=self.height, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.image_id = self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline="#00d4ff", width=2, state="hidden")
        self.handles = []
        for _ in range(8):
            self.handles.append(self.canvas.create_rectangle(0, 0, 0, 0, fill="#00d4ff", outline="#001018", state="hidden"))

        self.window.bind("<ButtonPress-1>", self.on_down)
        self.window.bind("<B1-Motion>", self.on_drag)
        self.window.bind("<ButtonRelease-1>", self.on_up)
        self.bind_hotkey("line_start", self.on_line_click)
        self.bind_hotkey("line_finish", self.on_line_finish)
        self.bind_hotkey("arrow_start", self.on_arrow_click)
        self.bind_hotkey("arrow_finish", self.on_arrow_finish)
        self.bind_hotkey("save", self.save)
        self.bind_hotkey("cancel", self.on_cancel)
        self.window.bind("<Motion>", self.on_motion)
        self.draw_rect()

    def bind_hotkey(self, name, callback):
        value = CONFIG["hotkeys"][name]
        binding = selector_binding(value)
        self.window.bind(binding, callback, add="+")
        log(f"selector hotkey {name}={value} binding={binding}")

    def local_point(self, event):
        return max(0, min(self.width, event.x)), max(0, min(self.height, event.y))

    def normalized_rect(self):
        if not self.rect:
            return None
        x1, y1, x2, y2 = self.rect
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if right - left < self.MIN_SIZE or bottom - top < self.MIN_SIZE:
            return None
        return int(left), int(top), int(right), int(bottom)

    def hit_test(self, x, y):
        rect = self.normalized_rect()
        if not rect:
            return "new"
        left, top, right, bottom = rect
        h = self.HANDLE
        points = {
            "nw": (left, top),
            "n": ((left + right) // 2, top),
            "ne": (right, top),
            "e": (right, (top + bottom) // 2),
            "se": (right, bottom),
            "s": ((left + right) // 2, bottom),
            "sw": (left, bottom),
            "w": (left, (top + bottom) // 2),
        }
        for name, (px, py) in points.items():
            if abs(x - px) <= h and abs(y - py) <= h:
                return name
        if left <= x <= right and top <= y <= bottom:
            return "move"
        return "new"

    def cursor_for_mode(self, mode):
        return {
            "move": "fleur",
            "n": "sb_v_double_arrow",
            "s": "sb_v_double_arrow",
            "e": "sb_h_double_arrow",
            "w": "sb_h_double_arrow",
            "nw": "size_nw_se",
            "se": "size_nw_se",
            "ne": "size_ne_sw",
            "sw": "size_ne_sw",
        }.get(mode, "crosshair")

    def on_motion(self, event):
        if self.text_entry is not None and event.widget is self.text_entry:
            return
        self.update_annotation_preview(event)
        if self.toolbar_tool_at(event.x, event.y):
            cursor = "hand2"
        else:
            mode = self.hit_test(event.x, event.y)
            if mode not in {"new", "move"}:
                cursor = self.cursor_for_mode(mode)
            elif self.active_tool == "text" and self.point_in_selection(event.x, event.y):
                cursor = "xterm"
            elif self.active_tool and self.point_in_selection(event.x, event.y):
                cursor = "crosshair"
            else:
                cursor = self.cursor_for_mode(mode)
        self.canvas.configure(cursor=cursor)

    def point_in_selection(self, x, y):
        rect = self.normalized_rect()
        if not rect:
            return False
        left, top, right, bottom = rect
        return left <= x <= right and top <= y <= bottom

    def annotation_click(self, event, kind):
        x, y = self.local_point(event)
        if not self.point_in_selection(x, y):
            return "break"

        if self.pending_annotation is None:
            self.pending_annotation = {"kind": kind, "start": (x, y)}
            self.pending_annotation_id = self.create_annotation_item(kind, (x, y), (x, y))
            self.canvas.configure(cursor="crosshair")
            return "break"

        if self.pending_annotation["kind"] != kind:
            return "break"

        start = self.pending_annotation["start"]
        if math.dist(start, (x, y)) < 3:
            return "break"

        self.annotations.append({"kind": kind, "start": start, "end": (x, y)})
        self.canvas.coords(self.pending_annotation_id, *start, x, y)
        self.pending_annotation = None
        self.pending_annotation_id = None
        self.raise_selection_controls()
        return "break"

    def on_line_click(self, event):
        return self.annotation_click(event, "line")

    def on_arrow_click(self, event):
        return self.annotation_click(event, "arrow")

    def on_line_finish(self, event):
        if self.pending_annotation is not None and self.pending_annotation["kind"] == "line":
            return self.annotation_click(event, "line")

    def on_arrow_finish(self, event):
        if self.pending_annotation is not None and self.pending_annotation["kind"] == "arrow":
            return self.annotation_click(event, "arrow")

    def create_annotation_item(self, kind, start, end):
        options = {
            "fill": self.ANNOTATION_COLOR,
            "width": self.ANNOTATION_WIDTH,
            "capstyle": tk.ROUND,
        }
        if kind == "arrow":
            options.update(arrow=tk.LAST, arrowshape=(27, 33, 10))
        return self.canvas.create_line(*start, *end, **options)

    def toolbar_tool_at(self, x, y):
        for left, top, right, bottom, tool in self.toolbar_hitboxes:
            if left <= x <= right and top <= y <= bottom:
                return tool
        return None

    def select_tool(self, tool):
        self.discard_pending()
        self.active_tool = None if self.active_tool == tool else tool
        self.draw_toolbar()
        log(f"toolbar tool={self.active_tool or 'none'}")

    def draw_toolbar(self):
        self.canvas.delete("toolbar")
        self.toolbar_hitboxes = []
        rect = self.normalized_rect()
        if not rect:
            return

        left, top, right, bottom = rect
        count = len(self.TOOLBAR_TOOLS)
        width = self.TOOLBAR_PAD * 2 + count * self.TOOLBAR_BUTTON + (count - 1) * self.TOOLBAR_GAP
        height = self.TOOLBAR_PAD * 2 + self.TOOLBAR_BUTTON
        x = max(0, min(self.width - width, left))
        if top >= height + self.TOOLBAR_MARGIN:
            y = top - height - self.TOOLBAR_MARGIN
        elif bottom + height + self.TOOLBAR_MARGIN <= self.height:
            y = bottom + self.TOOLBAR_MARGIN
        else:
            y = max(0, min(self.height - height, top + self.TOOLBAR_MARGIN))

        self.canvas.create_rectangle(
            x, y, x + width, y + height,
            fill="#111827", outline="#7b8492", width=1,
            stipple="gray50", tags=("toolbar",),
        )
        for index, tool in enumerate(self.TOOLBAR_TOOLS):
            bx1 = x + self.TOOLBAR_PAD + index * (self.TOOLBAR_BUTTON + self.TOOLBAR_GAP)
            by1 = y + self.TOOLBAR_PAD
            bx2 = bx1 + self.TOOLBAR_BUTTON
            by2 = by1 + self.TOOLBAR_BUTTON
            selected = tool == self.active_tool
            self.canvas.create_rectangle(
                bx1, by1, bx2, by2,
                fill="#7f1d1d" if selected else "#27303b",
                outline="#ff5a5a" if selected else "#657080",
                stipple="gray50", tags=("toolbar",),
            )
            self.draw_toolbar_icon(tool, bx1, by1, bx2, by2, selected)
            self.toolbar_hitboxes.append((bx1, by1, bx2, by2, tool))
        self.canvas.tag_raise("toolbar")

    def draw_toolbar_icon(self, tool, left, top, right, bottom, selected):
        color = "#ffffff" if selected else "#c7ced8"
        cx = (left + right) / 2
        cy = (top + bottom) / 2
        tags = ("toolbar",)
        if tool == "line":
            self.canvas.create_line(left + 8, bottom - 8, right - 8, top + 8, fill=color, width=3, tags=tags)
        elif tool == "arrow":
            self.canvas.create_line(left + 7, bottom - 8, right - 7, top + 8, fill=color, width=3, arrow=tk.LAST, arrowshape=(9, 11, 4), tags=tags)
        elif tool == "freehand":
            self.canvas.create_line(
                left + 6, cy + 5, left + 12, cy - 5, cx, cy + 4,
                right - 10, cy - 6, right - 6, cy,
                fill=color, width=3, smooth=True, tags=tags,
            )
        else:
            self.canvas.create_text(cx, cy, text="T", fill=color, font=("Segoe UI", 18, "bold"), tags=tags)

    def start_freehand(self, x, y):
        self.freehand_points = [(x, y)]
        self.freehand_id = self.canvas.create_line(
            x, y, x, y,
            fill=self.ANNOTATION_COLOR,
            width=self.ANNOTATION_WIDTH,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
            smooth=True,
        )

    def extend_freehand(self, x, y):
        if self.freehand_points is None or self.freehand_id is None:
            return
        rect = self.normalized_rect()
        if not rect:
            return
        left, top, right, bottom = rect
        point = (max(left, min(right, x)), max(top, min(bottom, y)))
        if math.dist(self.freehand_points[-1], point) < 1:
            return
        self.freehand_points.append(point)
        coords = [coordinate for pair in self.freehand_points for coordinate in pair]
        self.canvas.coords(self.freehand_id, *coords)
        self.raise_selection_controls()

    def finish_freehand(self):
        if self.freehand_points is None:
            return
        if len(self.freehand_points) > 1:
            self.annotations.append({"kind": "freehand", "points": list(self.freehand_points)})
        elif self.freehand_id is not None:
            self.canvas.delete(self.freehand_id)
        self.freehand_points = None
        self.freehand_id = None
        self.raise_selection_controls()

    def start_text(self, x, y):
        self.cancel_text()
        self.text_origin = (x, y)
        self.text_entry = tk.Entry(
            self.window,
            font=("Segoe UI", self.TEXT_SIZE),
            fg=self.ANNOTATION_COLOR,
            bg="#ffffff",
            insertbackground=self.ANNOTATION_COLOR,
            relief="flat",
            width=18,
        )
        self.text_window_id = self.canvas.create_window(x, y, window=self.text_entry, anchor="nw")
        self.text_entry.bind("<Return>", self.commit_text)
        self.text_entry.bind("<Escape>", self.cancel_text)
        self.text_entry.focus_set()

    def commit_text(self, _event=None):
        if self.text_entry is None or self.text_origin is None:
            return "break"
        value = self.text_entry.get().strip()
        origin = self.text_origin
        self.cancel_text()
        if value:
            self.annotations.append({"kind": "text", "start": origin, "text": value})
            self.canvas.create_text(
                *origin,
                text=value,
                fill=self.ANNOTATION_COLOR,
                font=("Segoe UI", self.TEXT_SIZE),
                anchor="nw",
            )
            self.raise_selection_controls()
        return "break"

    def cancel_text(self, _event=None):
        if self.text_window_id is not None:
            self.canvas.delete(self.text_window_id)
        if self.text_entry is not None:
            self.text_entry.destroy()
        self.text_entry = None
        self.text_window_id = None
        self.text_origin = None
        return "break"

    def update_annotation_preview(self, event):
        if self.pending_annotation is None or self.pending_annotation_id is None:
            return
        x, y = self.local_point(event)
        if not self.point_in_selection(x, y):
            return
        start = self.pending_annotation["start"]
        self.canvas.coords(self.pending_annotation_id, *start, x, y)
        self.raise_selection_controls()

    def on_down(self, event):
        if self.text_entry is not None and event.widget is self.text_entry:
            return "break"
        tool = self.toolbar_tool_at(event.x, event.y)
        if tool:
            self.select_tool(tool)
            return "break"
        if self.pending_annotation is not None:
            if self.active_tool == self.pending_annotation["kind"]:
                return self.annotation_click(event, self.active_tool)
            return
        x, y = self.local_point(event)
        mode = self.hit_test(x, y)
        if mode not in {"new", "move"}:
            self.mode = mode
            self.anchor = (x, y)
            self.start_rect = self.normalized_rect()
            return "break"
        if self.active_tool in {"line", "arrow"} and self.point_in_selection(x, y):
            return self.annotation_click(event, self.active_tool)
        if self.active_tool == "freehand" and self.point_in_selection(x, y):
            self.start_freehand(x, y)
            return "break"
        if self.active_tool == "text" and self.point_in_selection(x, y):
            self.start_text(x, y)
            return "break"
        self.mode = mode
        self.anchor = (x, y)
        self.start_rect = self.normalized_rect()
        if self.mode == "new":
            self.rect = (x, y, x, y)
        self.draw_rect()

    def on_drag(self, event):
        if self.text_entry is not None and event.widget is self.text_entry:
            return "break"
        x, y = self.local_point(event)
        if self.freehand_points is not None:
            self.extend_freehand(x, y)
            return
        if not self.anchor:
            return
        ax, ay = self.anchor
        if self.mode == "new":
            self.rect = (ax, ay, x, y)
        elif self.mode == "move" and self.start_rect:
            sx1, sy1, sx2, sy2 = self.start_rect
            dx, dy = x - ax, y - ay
            w, h = sx2 - sx1, sy2 - sy1
            nx1 = max(0, min(self.width - w, sx1 + dx))
            ny1 = max(0, min(self.height - h, sy1 + dy))
            self.rect = (nx1, ny1, nx1 + w, ny1 + h)
        elif self.start_rect:
            x1, y1, x2, y2 = self.start_rect
            l, r = sorted((x1, x2))
            t, b = sorted((y1, y2))
            if "w" in self.mode:
                l = min(x, r - self.MIN_SIZE)
            if "e" in self.mode:
                r = max(x, l + self.MIN_SIZE)
            if "n" in self.mode:
                t = min(y, b - self.MIN_SIZE)
            if "s" in self.mode:
                b = max(y, t + self.MIN_SIZE)
            self.rect = (l, t, r, b)
        self.draw_rect()

    def on_up(self, event):
        if self.text_entry is not None and event.widget is self.text_entry:
            return "break"
        if self.freehand_points is not None:
            self.finish_freehand()
            return
        self.anchor = None
        self.start_rect = None

    def draw_rect(self):
        rect = self.normalized_rect()
        if not rect:
            self.canvas.itemconfigure(self.rect_id, state="hidden")
            for handle in self.handles:
                self.canvas.itemconfigure(handle, state="hidden")
            self.draw_toolbar()
            return

        left, top, right, bottom = rect
        self.canvas.coords(self.rect_id, left, top, right, bottom)
        self.canvas.itemconfigure(self.rect_id, state="normal")

        points = [
            (left, top), ((left + right) // 2, top), (right, top),
            (right, (top + bottom) // 2), (right, bottom), ((left + right) // 2, bottom),
            (left, bottom), (left, (top + bottom) // 2),
        ]
        half = self.HANDLE // 2
        for handle, (x, y) in zip(self.handles, points):
            self.canvas.coords(handle, x - half, y - half, x + half, y + half)
            self.canvas.itemconfigure(handle, state="normal")
        self.raise_selection_controls()
        self.draw_toolbar()

    def raise_selection_controls(self):
        self.canvas.tag_raise(self.rect_id)
        for handle in self.handles:
            self.canvas.tag_raise(handle)
        self.canvas.tag_raise("toolbar")

    def draw_annotations(self, image, rect):
        left, top, _right, _bottom = rect
        draw = ImageDraw.Draw(image)
        for annotation in self.annotations:
            kind = annotation["kind"]
            if kind == "freehand":
                points = [(x - left, y - top) for x, y in annotation["points"]]
                if len(points) > 1:
                    draw.line(points, fill=self.ANNOTATION_COLOR, width=self.ANNOTATION_WIDTH, joint="curve")
                continue
            if kind == "text":
                x, y = annotation["start"]
                try:
                    font = ImageFont.truetype("segoeui.ttf", self.TEXT_SIZE)
                except OSError:
                    font = ImageFont.load_default()
                draw.text((x - left, y - top), annotation["text"], fill=self.ANNOTATION_COLOR, font=font)
                continue
            sx, sy = annotation["start"]
            ex, ey = annotation["end"]
            start = (sx - left, sy - top)
            end = (ex - left, ey - top)
            draw.line((start, end), fill=self.ANNOTATION_COLOR, width=self.ANNOTATION_WIDTH)
            if kind == "arrow":
                self.draw_arrow_head(draw, start, end)

    def draw_arrow_head(self, draw, start, end):
        sx, sy = start
        ex, ey = end
        angle = math.atan2(ey - sy, ex - sx)
        back = angle + math.pi
        left = (
            ex + self.ARROW_HEAD_LENGTH * math.cos(back - self.ARROW_HEAD_ANGLE),
            ey + self.ARROW_HEAD_LENGTH * math.sin(back - self.ARROW_HEAD_ANGLE),
        )
        right = (
            ex + self.ARROW_HEAD_LENGTH * math.cos(back + self.ARROW_HEAD_ANGLE),
            ey + self.ARROW_HEAD_LENGTH * math.sin(back + self.ARROW_HEAD_ANGLE),
        )
        draw.polygon((end, left, right), fill=self.ANNOTATION_COLOR)

    def save(self, _event=None):
        rect = self.normalized_rect()
        if not rect:
            return
        image = self.original.crop(rect)
        self.draw_annotations(image, rect)
        path = save_capture(image)
        print(f"Saved rectangle: {path}", flush=True)
        self.window.destroy()

    def on_cancel(self, _event=None):
        if self.discard_pending():
            self.canvas.configure(cursor="crosshair")
            log("pending annotation cancelled")
            return "break"
        self.cancel()
        return "break"

    def discard_pending(self):
        discarded = False
        if self.pending_annotation is not None:
            if self.pending_annotation_id is not None:
                self.canvas.delete(self.pending_annotation_id)
            self.pending_annotation = None
            self.pending_annotation_id = None
            discarded = True
        if self.freehand_points is not None:
            if self.freehand_id is not None:
                self.canvas.delete(self.freehand_id)
            self.freehand_points = None
            self.freehand_id = None
            discarded = True
        if self.text_entry is not None:
            self.cancel_text()
            discarded = True
        return discarded

    def cancel(self, _event=None):
        self.window.destroy()


class InfershotApp:
    def __init__(self):
        enable_dpi_awareness()
        self.tasks = queue.Queue()
        self.last_key_time = 0
        self.hook = None
        self.selector_open = False
        self.proc = LowLevelKeyboardProc(self.keyboard_proc)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("INFERSHOT")
        self.root.after(60, self.drain_tasks)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def install_hook(self):
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.proc, None, 0)
        if not self.hook:
            raise ctypes.WinError(ctypes.get_last_error())
        log(f"hook installed pid={os.getpid()}")

    def keyboard_proc(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if event.vkCode == VK_SNAPSHOT:
                    modifiers = key_combo_state()
                    log(f"printscreen event w_param={int(w_param)} flags={event.flags} modifiers={','.join(sorted(modifiers))}")
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        now = time.monotonic()
                        if now - self.last_key_time > 0.35:
                            self.last_key_time = now
                            if hotkey_matches("fullscreen", modifiers):
                                self.tasks.put("monitor")
                            elif hotkey_matches("rectangle", modifiers):
                                self.tasks.put("rectangle")
                    if w_param in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
                        return 1
        except Exception as error:
            log(f"keyboard_proc error: {error!r}")
        return user32.CallNextHookEx(self.hook, n_code, w_param, l_param)

    def drain_tasks(self):
        try:
            while True:
                task = self.tasks.get_nowait()
                log(f"task {task}")
                if task == "monitor":
                    threading.Thread(target=capture_monitor, daemon=True).start()
                elif task == "rectangle" and not self.selector_open:
                    self.selector_open = True
                    selector = RectSelector(self.root)
                    selector.window.bind("<Destroy>", self.selector_closed, add="+")
        except queue.Empty:
            pass
        self.root.after(60, self.drain_tasks)

    def selector_closed(self, _event=None):
        self.selector_open = False

    def quit(self):
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        self.root.destroy()

    def run(self):
        apply_config()
        log("starting")
        PID_FILE.write_text(str(os.getpid()), encoding="ascii")
        self.install_hook()
        print("INFERSHOT active.", flush=True)
        self.root.mainloop()


def acquire_single_instance():
    mutex_name = "Global\\INFERSHOT_SINGLE_INSTANCE"
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if kernel32.GetLastError() == 183:
        return None
    return handle


if __name__ == "__main__":
    try:
        if "--capture-monitor" in sys.argv:
            apply_config()
            capture_monitor()
            sys.exit(0)

        mutex = acquire_single_instance()
        if mutex is None:
            log("already running")
            print("INFERSHOT is already running.", flush=True)
            sys.exit(0)
        app = InfershotApp()
        app.run()
    except Exception as error:
        log(f"fatal: {error!r}")
        raise
