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
        self.photo = ImageTk.PhotoImage(icon_image(self.icon, self.size - 6, self.hovered), master=self)
        self.create_image(self.size / 2, self.size / 2, image=self.photo)
        if self.focused:
            self.create_rectangle(1, 1, self.size - 2, self.size - 2, outline="#9cbad4")

    def invoke(self):
        self.leave()
        self.command()
        return "break"

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
    def __init__(self, root, copy_image, settings=None):
        self.root = root
        self.copy_image = copy_image
        self.items = []
        self.window = None
        self.status = None
        self.photos = []
        self.on_close = None
        self.settings = settings

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
            files = self.folder_files()
            if not files:
                return
            folder = self.settings()["save_path"]
            if not messagebox.askyesno("Clear screenshot folder",
                    f"Move {len(files)} screenshots from\n{folder}\nto the Infershot recovery folder?\nOther files and subfolders stay in place.",
                    parent=parent or self.window or self.root):
                return
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
        if self.window is not None:
            self.close_button.place_forget()
            self.window.withdraw()
        callback, self.on_close = self.on_close, None
        if callback is not None:
            callback()

    def show(self, on_close=None):
        self.on_close = on_close
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
            self.close_button = IconButton(self.window, "remove", "Close – Esc", self.hide, size=24)
            self.window.bind("<Enter>", self.show_close, add="+")
            self.window.bind("<Leave>", lambda _event: self.window.after_idle(self.hide_close), add="+")
            self.actions = tk.Frame(self.window, background=BG)
            self.actions.pack(side="bottom", anchor="e", padx=8, pady=(0, 6))
            self.action_buttons = []
            for icon, title, action in (("copy", "Copy sheet", self.copy_sheet),
                                         ("archive", "Save ZIP archive", self.export_archive),
                                         ("clear", "Clear history", self.clear)):
                button = IconButton(self.actions, icon, title, action)
                button.pack(side="left", padx=3)
                self.action_buttons.append(button)
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
        available_w = max(200, self.window.winfo_screenwidth() - 80)
        available_h = max(180, self.window.winfo_screenheight() - 120)
        tile = 112
        count = max(1, len(self.items))
        while True:
            columns = max(1, min(count, 6, int(available_w // (tile + 8))))
            rows = math.ceil(count / columns)
            if rows * (tile + 8) + 50 <= available_h or tile <= 48:
                break
            tile -= 8
        if not self.items:
            tk.Label(self.cards, text="Capture a region or monitor to add a screenshot.",
                     background=BG, foreground=MUTED, font=("Palatino Linotype", 11)).pack(padx=8, pady=20)
        self.card_controls = []
        for index, item in enumerate(self.items):
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
        x = max(0, (self.window.winfo_screenwidth() - width) // 2)
        y = max(0, self.window.winfo_screenheight() - height - 64)
        self.window.geometry(f"{width}x{height}+{x}+{y}")

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
            self.copy_image(sheet)
            self.update_status(f"Copied sheet – {size[0]} × {size[1]}")
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
