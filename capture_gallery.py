"""Folder-backed screenshot manager and native-resolution clipboard sheets."""

import io
import math
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from qa_core import sheet_layout, write_capture_archive, screenshot_files, clear_screenshot_folder


BG, PANEL, TEXT, MUTED = "#171a21", "#222630", "#eef2f7", "#9ca8b8"


def icon_image(name, size, glow=False):
    """Scope-style icon geometry; no font glyph or platform theme dependency."""
    scale = size * 4 / 24
    image = Image.new("RGBA", (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    def line(points):
        draw.line([(round(x * scale), round(y * scale)) for x, y in points],
                  fill=TEXT, width=max(1, round(1.8 * scale)), joint="curve")
    if name in {"copy", "copied"}:
        draw.rectangle(tuple(round(v * scale) for v in (8, 8, 20, 21)), outline=TEXT, width=round(1.8 * scale))
        line(((16, 8), (16, 3), (3, 3), (3, 16), (8, 16)))
        if name == "copied":
            line(((11, 14), (14, 17), (18, 12)))
    elif name == "archive":
        line(((12, 3), (12, 15)))
        line(((7, 10), (12, 15), (17, 10)))
        line(((4, 16), (4, 21), (20, 21), (20, 16)))
    elif name == "clear":
        draw.arc(tuple(round(v * scale) for v in (3, 3, 21, 21)), 200, 510,
                 fill=TEXT, width=round(1.8 * scale))
        line(((3, 3), (3, 10), (10, 10)))
    elif name == "trash":
        line(((4, 6), (20, 6)))
        line(((9, 3), (15, 3)))
        line(((6, 8), (7, 21), (17, 21), (18, 8)))
        line(((10, 10), (10, 18)))
        line(((14, 10), (14, 18)))
    elif name in {"previous", "next"}:
        direction = 1 if name == "next" else -1
        line(((12 - direction * 4, 5), (12 + direction * 4, 12), (12 - direction * 4, 19)))
    else:
        line(((5, 5), (19, 19)))
        line(((19, 5), (5, 19)))
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    if glow:
        halo = Image.new("RGBA", image.size, "white")
        halo.putalpha(image.getchannel("A").filter(ImageFilter.GaussianBlur(1.6)).point(lambda alpha: round(alpha * .65)))
        image = Image.alpha_composite(halo, image)
    return image


class IconButton(tk.Canvas):
    def __init__(self, parent, icon, title, command, size=28):
        super().__init__(parent, width=size, height=size, background=parent.cget("background"),
                         highlightthickness=0, borderwidth=0, cursor="hand2", takefocus=True)
        self.icon, self.title, self.command, self.size = icon, title, command, size
        self.hovered, self.focused, self.tooltip, self.tip_timer = False, False, None, None
        self.enabled = True
        self.bind("<ButtonRelease-1>", lambda _event: self.invoke())
        self.bind("<Return>", lambda _event: self.invoke())
        self.bind("<space>", lambda _event: self.invoke())
        self.bind("<Enter>", self.enter)
        self.bind("<Leave>", self.leave)
        self.bind("<Unmap>", self.leave)
        self.bind("<FocusIn>", lambda _event: self.focus(True))
        self.bind("<FocusOut>", lambda _event: self.focus(False))
        self.paint()

    def paint(self):
        self.delete("all")
        icon = icon_image(self.icon, self.size - 6, self.hovered and self.enabled)
        if not self.enabled:
            icon.putalpha(icon.getchannel("A").point(lambda value: value // 3))
        self.photo = ImageTk.PhotoImage(icon, master=self)
        self.create_image(self.size / 2, self.size / 2, image=self.photo)
        if self.focused:
            self.create_rectangle(1, 1, self.size - 2, self.size - 2, outline="#9cbad4")

    def invoke(self):
        self.leave()
        if self.enabled:
            self.command()
        return "break"

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow", takefocus=enabled)
        self.paint()

    def focus(self, value):
        self.focused = value
        self.paint()

    def enter(self, _event=None):
        self.hovered = True
        self.paint()
        self.tip_timer = self.after(450, self.show_tip)

    def show_tip(self):
        self.tip_timer = None
        self.tooltip = tk.Toplevel(self)
        self.tooltip.overrideredirect(True)
        self.tooltip.transient(self.winfo_toplevel())
        self.tooltip.attributes("-topmost", True)
        tk.Label(self.tooltip, text=self.title, background=PANEL, foreground=TEXT,
                 font=("Palatino Linotype", 10), padx=6, pady=3).pack()
        self.tooltip.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.size + 4}")

    def leave(self, _event=None):
        if self.tip_timer is not None:
            self.after_cancel(self.tip_timer)
            self.tip_timer = None
        if self.tooltip is not None:
            self.tooltip.destroy()
            self.tooltip = None
        self.hovered = False
        if self.winfo_exists():
            self.paint()


class CaptureGallery:
    def __init__(self, root, copy_image, settings=None, save_sheet=None):
        self.root = root
        self.copy_image = copy_image
        self.items = []
        self.window = None
        self.status = None
        self.photos = []
        self.on_close = None
        self.settings = settings
        self.save_sheet = save_sheet
        self.anchor = None
        self.bounds = None
        self.page = 0
        self.drag_offset = None
        self.manual_position = None

    def folder_files(self):
        return screenshot_files(self.settings()["save_path"]) if self.settings else []

    def sync_folder(self):
        if not self.settings:
            return
        settings = self.settings()
        previous = {item["path"]: item["selected"] for item in self.items}
        self.items = []
        for path in self.folder_files():
            try:
                with Image.open(path) as image:
                    if image.width * image.height > 100_000_000:
                        continue
                    buffer = io.BytesIO()
                    image.convert("RGB").save(buffer, "PNG")
                    self.items.append({"path": path, "data": buffer.getvalue(),
                                       "size": image.size, "selected": previous.get(path, True)})
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
            if len(self.items) >= settings["gallery"]["limit"]:
                break

    def clear_folder(self, parent=None):
        if self.settings is None:
            return
        try:
            files = screenshot_files(self.settings()["save_path"], captures_only=True)
            if not files:
                return
            folder = self.settings()["save_path"]
            recovery = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Infershot" / "Trash"
            clear_screenshot_folder(folder, recovery, files)
            self.sync_folder()
            if self.window is not None:
                self.refresh()
                if not self.items:
                    self.hide()
        except (OSError, ValueError) as error:
            messagebox.showerror("Clear screenshot folder", f"{error}\nRecovery folder: {recovery if 'recovery' in locals() else 'unchanged'}",
                                 parent=parent or self.window or self.root)

    def add(self, image, path, limit=20):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "PNG")
        self.items.append({"path": Path(path), "data": buffer.getvalue(),
                           "size": image.size, "selected": True})
        del self.items[:-limit]
        if self.window is not None:
            self.refresh()

    def hide(self):
        self.drag_offset = None
        if self.window is not None:
            self.close_button.place_forget()
            self.window.withdraw()
        callback, self.on_close = self.on_close, None
        if callback is not None:
            callback()

    def show(self, on_close=None, anchor=None, bounds=None):
        self.on_close = on_close
        self.anchor, self.bounds, self.page = anchor, bounds, 0
        self.manual_position = None
        try:
            self.sync_folder()
        except OSError as error:
            messagebox.showerror("Screenshot manager", str(error), parent=self.root)
            self.hide()
            return
        if not self.items:
            self.hide()
            return
        if self.window is None or not self.window.winfo_exists():
            self.window = tk.Toplevel(self.root, background=BG)
            self.window.withdraw()
            self.window.title("Infershot – screenshot manager")
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            self.window.resizable(False, False)
            self.window.protocol("WM_DELETE_WINDOW", self.hide)
            self.window.bind("<Escape>", lambda _event: self.hide())
            self.window.bind("<ButtonPress-1>", self.start_drag, add="+")
            self.window.bind("<B1-Motion>", self.drag, add="+")
            self.window.bind("<ButtonRelease-1>", self.end_drag, add="+")
            self.close_button = IconButton(self.window, "remove", "Close – Esc", self.hide, size=24)
            self.window.bind("<Enter>", self.show_close, add="+")
            self.window.bind("<Leave>", lambda _event: self.window.after_idle(self.hide_close), add="+")
            self.actions = tk.Frame(self.window, background=BG)
            self.actions.pack(side="bottom", anchor="e", padx=8, pady=(0, 6))
            self.action_buttons = []
            for icon, title, action in (("copy", "Copy sheet", self.copy_sheet),
                                         ("archive", "Save ZIP archive", self.export_archive),
                                         ("trash", "Clear screenshot folder – ScreenShot-*.*", self.clear_folder)):
                button = IconButton(self.actions, icon, title, action)
                button.pack(side="left", padx=3)
                self.action_buttons.append(button)
            self.pagination = tk.Frame(self.window, background=BG)
            self.previous_button = IconButton(self.pagination, "previous", "Previous screenshots", lambda: self.change_page(-1))
            self.previous_button.pack(side="left", padx=3)
            self.next_button = IconButton(self.pagination, "next", "Next screenshots", lambda: self.change_page(1))
            self.next_button.pack(side="left", padx=3)
            self.status = tk.StringVar(master=self.window)
            self.cards = tk.Frame(self.window, background=BG)
            self.cards.pack(padx=8, pady=(26, 8))
        self.refresh()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def show_close(self, _event=None):
        self.close_button.place(relx=1, x=-26, y=1)
        tk.Misc.lift(self.close_button)

    def start_drag(self, event):
        if event.widget == self.window and 0 <= event.y < 26:
            self.drag_offset = (event.x_root - self.window.winfo_x(),
                                event.y_root - self.window.winfo_y())

    def drag(self, event):
        if self.drag_offset is not None:
            x, y = event.x_root - self.drag_offset[0], event.y_root - self.drag_offset[1]
            self.manual_position = x, y
            self.window.geometry(f"+{x}+{y}")

    def end_drag(self, _event=None):
        self.drag_offset = None

    def hide_close(self):
        if self.window is None or not self.window.winfo_exists():
            return
        x, y = self.window.winfo_pointerxy()
        if not (self.window.winfo_rootx() <= x < self.window.winfo_rootx() + self.window.winfo_width()
                and self.window.winfo_rooty() <= y < self.window.winfo_rooty() + self.window.winfo_height()):
            self.close_button.place_forget()

    def refresh(self):
        for widget in self.cards.winfo_children():
            widget.destroy()
        self.photos = []
        bounds = self.bounds or (0, 0, self.window.winfo_screenwidth(), self.window.winfo_screenheight())
        left, top, right, bottom = bounds
        available_w, available_h = right - left - 32, bottom - top - 32
        tile = max(1, min(336, available_w - 24, available_h - 80))
        if self.anchor:
            room_right, room_left = right - self.anchor[2] - 28, self.anchor[0] - left - 28
            side_room = room_right if room_right >= tile + 24 else room_left
            if side_room >= tile + 24:
                available_w = side_room
        count = max(1, len(self.items))
        columns = max(1, min(count, 6, int((available_w - 16) // (tile + 8))))
        rows = max(1, int((available_h - 80) // (tile + 8)))
        self.page_size = columns * rows
        pages = max(1, math.ceil(len(self.items) / self.page_size))
        self.page = min(self.page, pages - 1)
        if pages > 1:
            self.pagination.pack(side="bottom", anchor="w", padx=8, pady=(0, 6), before=self.cards)
        else:
            self.pagination.pack_forget()
        self.previous_button.set_enabled(self.page > 0)
        self.next_button.set_enabled(self.page + 1 < pages)
        self.tile_size = tile
        if self.settings:
            self.action_buttons[2].set_enabled(bool(screenshot_files(self.settings()["save_path"], captures_only=True)))
        if not self.items:
            tk.Label(self.cards, text="Capture a region or monitor to add a screenshot.",
                     background=BG, foreground=MUTED, font=("Palatino Linotype", 11)).pack(padx=8, pady=20)
        self.card_controls = []
        start = self.page * self.page_size
        for index, item in enumerate(self.items[start:start + self.page_size]):
            card = tk.Frame(self.cards, background=BG, width=tile, height=tile,
                            highlightthickness=1, highlightbackground="#9cbad4" if item["selected"] else "#505967",
                            takefocus=True)
            card.grid(row=index // columns, column=index % columns, padx=4, pady=4)
            card.pack_propagate(False)
            with Image.open(io.BytesIO(item["data"])) as image:
                preview = image.copy()
            preview.thumbnail((tile - 4, tile - 4))
            photo = ImageTk.PhotoImage(preview, master=self.window)
            self.photos.append(photo)
            picture = tk.Label(card, image=photo, background=BG)
            picture.pack(fill="both", expand=True)
            def toggle(_event=None, entry=item, frame=card):
                entry["selected"] = not entry["selected"]
                frame.configure(highlightbackground="#9cbad4" if entry["selected"] else "#505967")
                self.update_status()
            picture.bind("<ButtonRelease-1>", toggle)
            card.bind("<space>", toggle)
            controls = (IconButton(card, "copy", f'Copy {item["path"].name} – {item["size"][0]} × {item["size"][1]}',
                                   lambda entry=item: self.copy_one(entry), size=22),
                        IconButton(card, "remove", "Remove from history", lambda entry=item: self.remove(entry), size=22))
            self.card_controls.append(controls)
            def reveal(_event=None, buttons=controls):
                buttons[0].place(relx=1, x=-48, y=2)
                buttons[1].place(relx=1, x=-24, y=2)
            def conceal(_event=None, frame=card, buttons=controls):
                if not frame.winfo_exists():
                    return
                x, y = frame.winfo_pointerxy()
                focus = self.window.focus_get()
                focused = focus is not None and str(focus).startswith(str(frame))
                inside = frame.winfo_rootx() <= x < frame.winfo_rootx() + tile and frame.winfo_rooty() <= y < frame.winfo_rooty() + tile
                if not inside and not focused:
                    for button in buttons:
                        button.place_forget()
            for widget in (card, picture, *controls):
                widget.bind("<Enter>", reveal, add="+")
                widget.bind("<Leave>", lambda event, action=conceal: self.window.after(30, action), add="+")
                widget.bind("<FocusIn>", reveal, add="+")
                widget.bind("<FocusOut>", lambda event, action=conceal: self.window.after_idle(action), add="+")
        self.update_status()
        self.window.update_idletasks()
        width, height = self.window.winfo_reqwidth(), self.window.winfo_reqheight()
        x, y = left + (right - left - width) // 2, top + (bottom - top - height) // 2
        if self.anchor:
            if self.anchor[2] + 12 + width <= right - 16:
                x = self.anchor[2] + 12
            elif self.anchor[0] - 12 - width >= left + 16:
                x = self.anchor[0] - 12 - width
        if self.manual_position is not None:
            x, y = self.manual_position
        # Negative desktop coordinates are absolute positions, not Tk's
        # negative geometry offsets from the right/bottom screen edge.
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def change_page(self, delta):
        self.page = max(0, self.page + delta)
        self.refresh()

    def update_status(self, message=None):
        if self.status is not None:
            count = sum(item["selected"] for item in self.items)
            self.status.set(message or f"{count} selected / {len(self.items)} captures")
            self.window.title("Infershot – screenshot manager – " + self.status.get())

    def export_archive(self, destination=None):
        selected = [item for item in self.items if item["selected"]]
        if not selected:
            self.update_status("Choose at least one screenshot")
            return
        if destination is None:
            folder = selected[-1]["path"].parent
            destination = filedialog.asksaveasfilename(parent=self.window, title="Save screenshot archive",
                initialdir=str(folder) if folder.exists() else None, initialfile="infershot-captures.zip",
                defaultextension=".zip", filetypes=(("ZIP archive", "*.zip"),))
        if not destination:
            return
        try:
            names = write_capture_archive(destination, selected)
            self.update_status(f"Saved archive – {len(names)} screenshots")
        except Exception as error:
            self.update_status(f"Archive failed: {error}")

    def copy_one(self, item):
        try:
            with Image.open(io.BytesIO(item["data"])) as image:
                self.copy_image(image.convert("RGB"))
            self.update_status("Copied image")
        except Exception as error:
            self.update_status(f"Copy failed: {error}")

    def copy_sheet(self):
        selected = [item for item in self.items if item["selected"]]
        try:
            size, cells = sheet_layout([item["size"] for item in selected])
            if size[0] * size[1] > 100_000_000:
                raise ValueError("Select fewer screenshots for the sheet")
            sheet = Image.new("RGB", size, BG)
            for item, (x, y, _w, _h) in zip(selected, cells):
                with Image.open(io.BytesIO(item["data"])) as image:
                    sheet.paste(image.convert("RGB"), (x, y))
            path = self.save_sheet(sheet) if self.save_sheet else None
            try:
                self.copy_image(sheet)
            except Exception as error:
                self.update_status(f"Saved {path.name}; clipboard failed: {error}" if path else str(error))
                return
            saved = f"Saved {path.name}; " if path else ""
            self.update_status(f"{saved}Copied sheet – {size[0]} × {size[1]}")
        except Exception as error:
            self.update_status(str(error))

    def remove(self, item):
        self.items.remove(item)
        self.refresh()
        if not self.items:
            self.hide()

    def clear(self):
        self.items.clear()
        self.refresh()
        self.hide()
