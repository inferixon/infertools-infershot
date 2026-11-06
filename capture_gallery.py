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
ICON_BLUE, ICON_HOVER, ICON_DIM = "#9cbad4", "#c9e2fb", "#596f86"


def icon_image(name, size, glow=False, color=ICON_BLUE):
    """Scope-style icon geometry; no font glyph or platform theme dependency."""
    scale = size * 4 / 24
    mask = Image.new("L", (size * 4, size * 4))
    draw = ImageDraw.Draw(mask)
    def line(points):
        draw.line([(round(x * scale), round(y * scale)) for x, y in points],
                  fill=255, width=max(1, round(1.8 * scale)), joint="curve")
    if name in {"copy", "copied"}:
        draw.rectangle(tuple(round(v * scale) for v in (8, 8, 20, 21)), outline=255, width=round(1.8 * scale))
        line(((16, 8), (16, 3), (3, 3), (3, 16), (8, 16)))
        if name == "copied":
            line(((11, 14), (14, 17), (18, 12)))
    elif name == "archive":
        line(((12, 3), (12, 15)))
        line(((7, 10), (12, 15), (17, 10)))
        line(((4, 16), (4, 21), (20, 21), (20, 16)))
    elif name in {"screenshots", "sheets"}:
        line(((3, 5), (21, 5), (21, 19), (3, 19), (3, 5)))
        if name == "screenshots":
            line(((4, 17), (9, 11), (13, 15), (17, 10), (20, 13)))
        else:
            line(((12, 5), (12, 19)))
            line(((3, 12), (21, 12)))
    elif name in {"select_all", "select_none"}:
        line(((4, 4), (20, 4), (20, 20), (4, 20), (4, 4)))
        if name == "select_all":
            line(((7, 12), (10, 15), (17, 8)))
    elif name == "clear":
        draw.arc(tuple(round(v * scale) for v in (3, 3, 21, 21)), 200, 510,
                 fill=255, width=round(1.8 * scale))
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
    image = Image.new("RGBA", (size, size), color)
    image.putalpha(mask.resize(image.size, Image.Resampling.LANCZOS))
    if glow:
        halo = Image.new("RGBA", image.size, ICON_HOVER)
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
        self.checked = None
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
        hovered = self.hovered and self.enabled
        color = ICON_HOVER if hovered else ICON_BLUE
        if not self.enabled:
            color = ICON_DIM
        elif self.checked is False:
            color = "#7f9db7" if hovered else ICON_DIM
        icon = icon_image(self.icon, self.size - 6, hovered, color)
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
    def __init__(self, root, copy_image, settings=None, save_sheet=None, save_filter=None):
        self.root = root
        self.copy_image = copy_image
        self.items = []
        self.shown_types = {"screenshots", "sheets"}
        self.window = None
        self.status = None
        self.photos = []
        self.on_close = None
        self.settings = settings
        self.save_sheet = save_sheet
        self.save_filter = save_filter
        self.sheet_feedback_timer = None
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
                                       "size": image.size, "selected": previous.get(path, False)})
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
            if len(self.items) >= settings["gallery"]["limit"]:
                break

    def clear_folder(self, parent=None, *, respect_selection=False):
        if self.settings is None:
            return
        folder = self.settings()["save_path"]
        recovery = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Infershot" / "Trash"
        try:
            if respect_selection:
                files, _partial = self.manager_delete_targets(self.visible_items())
            else:
                files = screenshot_files(folder, captures_only=True)
            if not files:
                return
            try:
                clear_screenshot_folder(folder, recovery, files, captures_only=not respect_selection)
            finally:
                self.sync_folder()
                if self.window is not None:
                    self.refresh()
                    if not self.items:
                        self.hide()
        except (OSError, ValueError) as error:
            messagebox.showerror("Clear screenshot folder", f"{error}\nRecovery folder: {recovery}",
                                 parent=parent or self.window or self.root)

    def add(self, image, path, limit=20):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "PNG")
        self.items.insert(0, {"path": Path(path), "data": buffer.getvalue(),
                              "size": image.size, "selected": False})
        del self.items[limit:]
        if self.window is not None:
            self.refresh()

    def hide(self):
        self.set_sheet_copied()
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
        if self.save_filter:
            gallery = self.settings()["gallery"]
            self.shown_types = {kind for kind in ("screenshots", "sheets") if gallery.get(f"show_{kind}", True)}
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
            self.selection_button = IconButton(self.actions, "select_none", "Select all", self.toggle_selection)
            self.selection_button.pack(side="left", padx=3)
            self.filter_buttons = {}
            for kind in ("screenshots", "sheets"):
                button = IconButton(self.actions, kind, f"Show {kind}",
                                    lambda kind=kind: self.toggle_filter(kind))
                button.pack(side="left", padx=3)
                self.filter_buttons[kind] = button
            self.action_buttons = []
            for icon, title, action in (("copy", "Copy sheet", self.copy_sheet),
                                         ("archive", "Save ZIP archive", self.export_archive),
                                         ("trash", "Delete images", lambda: self.clear_folder(respect_selection=True))):
                button = IconButton(self.actions, icon, title, action)
                button.pack(side="left", padx=(15, 3) if icon == "copy" else 3)
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

    def matches_filters(self, path):
        kind = "sheets" if path.name.casefold().startswith("screensheet-") else "screenshots"
        return kind in self.shown_types

    def visible_items(self):
        return [item for item in self.items if self.matches_filters(item["path"])]

    def manager_delete_targets(self, visible):
        if not self.settings or not self.shown_types:
            return [], False
        selected = [item["path"] for item in visible if item["selected"]]
        if 0 < len(selected) < len(visible):
            return selected, True
        generated = screenshot_files(self.settings()["save_path"], captures_only=True)
        matching = [path for path in generated if self.matches_filters(path)]
        return list(dict.fromkeys(matching + selected)), False

    def toggle_filter(self, kind):
        enabled = kind not in self.shown_types
        if self.save_filter:
            try:
                self.save_filter(kind, enabled)
            except (OSError, ValueError, TypeError) as error:
                messagebox.showerror("Save screenshot filters", str(error), parent=self.window)
                return
        if enabled:
            self.shown_types.add(kind)
        else:
            self.shown_types.remove(kind)
        self.page = 0
        self.set_sheet_copied()
        self.refresh()

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
        visible = self.visible_items()
        count = max(1, len(visible))
        columns = max(1, min(count, 6, int((available_w - 16) // (tile + 8))))
        rows = max(1, int((available_h - 80) // (tile + 8)))
        self.page_size = columns * rows
        pages = max(1, math.ceil(len(visible) / self.page_size))
        self.page = min(self.page, pages - 1)
        if pages > 1:
            self.pagination.pack(side="bottom", anchor="w", padx=8, pady=(0, 6), before=self.cards)
        else:
            self.pagination.pack_forget()
        self.previous_button.set_enabled(self.page > 0)
        self.next_button.set_enabled(self.page + 1 < pages)
        self.tile_size = tile
        for kind, button in self.filter_buttons.items():
            button.checked = kind in self.shown_types
            button.title = f"Show {kind} ({'on' if button.checked else 'off'})"
            button.paint()
        if not visible:
            message = "No images match the active filters." if self.items else "Capture a region or monitor to add a screenshot."
            tk.Label(self.cards, text=message,
                     background=BG, foreground=MUTED, font=("Palatino Linotype", 11)).pack(padx=8, pady=20)
        self.card_controls = []
        start = self.page * self.page_size
        for index, item in enumerate(visible[start:start + self.page_size]):
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
                        IconButton(card, "remove", "Delete screenshot file", lambda entry=item: self.remove(entry), size=22))
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

    def toggle_selection(self):
        visible = self.visible_items()
        selected = not all(item["selected"] for item in visible)
        for item in visible:
            item["selected"] = selected
        self.set_sheet_copied()
        self.refresh()

    def update_status(self, message=None):
        if self.status is not None:
            visible = self.visible_items()
            count = sum(item["selected"] for item in visible)
            all_selected = bool(visible) and count == len(visible)
            self.selection_button.checked = all_selected
            self.selection_button.icon = "select_all" if all_selected else "select_none"
            self.selection_button.title = "Clear selection" if all_selected else "Select all"
            self.selection_button.set_enabled(bool(visible))
            try:
                targets, partial = self.manager_delete_targets(visible)
            except OSError:
                targets, partial = [], False
            trash = self.action_buttons[2]
            trash.title = "Delete selected images" if partial else "Delete all captures matching filters"
            trash.set_enabled(bool(targets))
            self.status.set(message or f"{count} selected / {len(visible)} captures")
            self.window.title("Infershot – screenshot manager – " + self.status.get())

    def export_archive(self, destination=None):
        selected = [item for item in self.visible_items() if item["selected"]]
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

    def set_sheet_copied(self, copied=False):
        if self.window is None or not self.window.winfo_exists():
            return
        if self.sheet_feedback_timer is not None:
            self.window.after_cancel(self.sheet_feedback_timer)
            self.sheet_feedback_timer = None
        button = self.action_buttons[0]
        button.icon = "copied" if copied else "copy"
        button.title = "Sheet copied" if copied else "Copy sheet"
        button.paint()
        if copied:
            self.sheet_feedback_timer = self.window.after(1500, self.set_sheet_copied)

    def copy_sheet(self):
        self.set_sheet_copied()
        selected = [item for item in self.visible_items() if item["selected"]]
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
            self.set_sheet_copied(True)
        except Exception as error:
            self.update_status(str(error))

    def remove(self, item):
        if item not in self.items:
            return
        folder = self.settings()["save_path"] if self.settings else item["path"].parent
        recovery = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Infershot" / "Trash"
        try:
            clear_screenshot_folder(folder, recovery, [item["path"]], captures_only=False)
        except (OSError, ValueError) as error:
            messagebox.showerror("Delete screenshot file", str(error), parent=self.window)
            return
        if self.settings:
            self.sync_folder()
        else:
            self.items.remove(item)
        self.refresh()
        if not self.items:
            self.hide()

    def clear(self):
        self.items.clear()
        self.refresh()
        self.hide()
