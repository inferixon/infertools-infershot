"""Session-local screenshot gallery and native-resolution clipboard sheets."""

import io
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageTk

from qa_core import sheet_layout


BG, PANEL, TEXT, MUTED = "#171a21", "#222630", "#eef2f7", "#9ca8b8"


class CaptureGallery:
    def __init__(self, root, copy_image):
        self.root = root
        self.copy_image = copy_image
        self.items = []
        self.window = None
        self.status = None
        self.photos = []
        self.on_close = None

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
            self.window.withdraw()
        callback, self.on_close = self.on_close, None
        if callback is not None:
            callback()

    def show(self, on_close=None):
        self.on_close = on_close
        if self.window is None or not self.window.winfo_exists():
            self.window = tk.Toplevel(self.root, background=BG)
            self.window.title("Infershot – recent screenshots")
            self.window.geometry("780x390")
            self.window.minsize(420, 260)
            self.window.protocol("WM_DELETE_WINDOW", self.hide)
            self.window.bind("<Escape>", lambda _event: self.hide())
            self.window.bind("<Control-g>", lambda _event: self.hide())
            self.actions = tk.Frame(self.window, background=BG)
            self.actions.pack(fill="x", padx=14, pady=10)
            self.button(self.actions, "Copy sheet", self.copy_sheet).pack(side="left", padx=(0, 16))
            self.button(self.actions, "Clear history", self.clear).pack(side="left")
            self.status = tk.Label(self.actions, background=BG, foreground=MUTED,
                                   font=("Palatino Linotype", 11), anchor="e")
            self.status.pack(side="right", expand=True, fill="x")
            self.canvas = tk.Canvas(self.window, background=BG, highlightthickness=0)
            scrollbar = tk.Scrollbar(self.window, orient="horizontal", command=self.canvas.xview)
            self.canvas.configure(xscrollcommand=scrollbar.set)
            scrollbar.pack(side="bottom", fill="x")
            self.canvas.pack(fill="both", expand=True, padx=14, pady=(0, 10))
            self.cards = tk.Frame(self.canvas, background=BG)
            self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
            self.cards.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.refresh()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    @staticmethod
    def button(parent, text, action):
        return tk.Button(parent, text=text, command=action, background=BG,
                         foreground=TEXT, activebackground=BG, activeforeground=TEXT,
                         relief="flat", borderwidth=0, cursor="hand2",
                         font=("Palatino Linotype", 11), takefocus=True)

    def refresh(self):
        for widget in self.cards.winfo_children():
            widget.destroy()
        self.photos = []
        if not self.items:
            tk.Label(self.cards, text="Capture a region or monitor to add a screenshot.",
                     background=BG, foreground=TEXT, font=("Palatino Linotype", 12)).pack(padx=20, pady=60)
        for item in self.items:
            card = tk.Frame(self.cards, background=PANEL, padx=10, pady=10)
            card.pack(side="left", padx=(0, 12), anchor="n")
            with Image.open(io.BytesIO(item["data"])) as image:
                preview = image.copy()
            preview.thumbnail((210, 150))
            photo = ImageTk.PhotoImage(preview, master=self.window)
            self.photos.append(photo)
            tk.Label(card, image=photo, background=PANEL, width=210, height=150).pack()
            selected = tk.BooleanVar(master=self.window, value=item["selected"])
            def toggle(entry=item, variable=selected):
                entry["selected"] = variable.get()
                self.update_status()
            tk.Checkbutton(card, text=item["path"].name, variable=selected, command=toggle,
                           background=PANEL, foreground=TEXT, activebackground=PANEL,
                           activeforeground=TEXT, selectcolor=BG, font=("Palatino Linotype", 11)).pack(anchor="w")
            tk.Label(card, text=f'{item["size"][0]} × {item["size"][1]}', background=PANEL,
                     foreground=MUTED, font=("Palatino Linotype", 10)).pack(anchor="w")
            row = tk.Frame(card, background=PANEL)
            row.pack(fill="x", pady=(6, 0))
            self.button(row, "Copy image", lambda entry=item: self.copy_one(entry)).pack(side="left")
            self.button(row, "Remove", lambda entry=item: self.remove(entry)).pack(side="right")
        self.update_status()

    def update_status(self, message=None):
        if self.status is not None:
            count = sum(item["selected"] for item in self.items)
            self.status.configure(text=message or f"{count} selected / {len(self.items)} captures")

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

    def clear(self):
        self.items.clear()
        self.refresh()
