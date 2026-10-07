"""Build the README demo from independent code, annotation, and UI layers.

Run `python assets/demo/generate.py all` for a complete rebuild.
For toolbar-only changes, run `python assets/demo/generate.py ui`, then `final`.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import infershot  # noqa: E402


SOURCE = Path(__file__).with_name("buggy-checkout.js")
BACKGROUND = Path(__file__).with_name("background.png")
ANNOTATED = Path(__file__).with_name("annotated.png")
UI_OVERLAY = Path(__file__).with_name("ui-overlay.png")
FINAL = ROOT / "assets" / "infershot-qa-demo.png"
WIDTH, HEIGHT = 1600, 1050
CODE_X, CODE_Y, LINE_HEIGHT = 124, 174, 31
SELECTION = (28, 126, 1572, 1022)
RED, GREEN = "#ff2020", "#22c55e"
KEYWORDS = {"const", "function", "return", "true", "false"}
TOKEN_RE = re.compile(r"//.*|\"(?:\\.|[^\"])*\"|\b[A-Za-z_]\w*\b|\b\d+\b|[^\w\s]|\s+")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


CODE_FONT = font("consola.ttf", 23)
SMALL_FONT = font("segoeui.ttf", 18)
TITLE_FONT = font("segoeuib.ttf", 25)


def lines() -> list[str]:
    return SOURCE.read_text(encoding="utf-8").splitlines()


def locate(source: list[str], needle: str) -> tuple[int, int, int, int]:
    matches = [(index, line.index(needle)) for index, line in enumerate(source) if needle in line]
    if len(matches) != 1:
        raise ValueError(f"Expected one occurrence of {needle!r}; found {len(matches)}")
    index, column = matches[0]
    x = round(CODE_X + CODE_FONT.getlength(source[index][:column]))
    y = CODE_Y + index * LINE_HEIGHT
    return x, y, round(x + CODE_FONT.getlength(needle)), y + 25


def render_background(source: list[str]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#171a21")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 70), fill="#222630")
    draw.text((42, 18), "buggy-checkout.js", font=TITLE_FONT, fill="#eef2f7")
    draw.text((1320, 26), "QA DEMO", font=SMALL_FONT, fill="#8e98a8")
    draw.rectangle((28, 126, 1572, 1022), fill="#1c2029", outline="#303746", width=2)
    draw.line((108, 148, 108, 997), fill="#353c4b", width=1)

    for index, line in enumerate(source):
        y = CODE_Y + index * LINE_HEIGHT
        draw.text((57, y), f"{index + 1:>2}", font=CODE_FONT, fill="#687487")
        x = CODE_X
        for match in TOKEN_RE.finditer(line):
            token = match.group()
            if token.startswith("//"):
                color = "#818b9a"
            elif token in KEYWORDS:
                color = "#75b7ee"
            elif token.isdigit():
                color = "#e9b47b"
            elif token in {"{", "}", "[", "]", "(", ")"}:
                color = "#e8c46b"
            else:
                color = "#dce3ec"
            draw.text((round(x), y), token, font=CODE_FONT, fill=color)
            x += CODE_FONT.getlength(token)
    return image


def add_annotations(image: Image.Image, source: list[str]) -> None:
    cart = locate(source, "const cart")
    typo = locate(source, "item.quantitty")
    assignment = locate(source, "user.isPremium = true")
    discount = locate(source, "+ discount")
    off_by_one = locate(source, "items.length")

    selector = infershot.RectSelector.__new__(infershot.RectSelector)
    selector.annotations = [
        {"kind": "text", "start": (900, cart[1] - 6),
         "text": "// Good: clear input data", "color": GREEN,
         "font_family": "Segoe UI", "font_size": 20},
        # Freehand underline – the misspelled property causes NaN.
        {"kind": "freehand", "points": [
            (typo[0] + 65, typo[3] + 5), (typo[0] + 91, typo[3] + 8),
            (typo[0] + 119, typo[3] + 5), (typo[2], typo[3] + 7),
        ], "color": RED},
        {"kind": "text", "start": (900, typo[1] - 6),
         "text": "// Typo: use quantity", "color": RED,
         "font_family": "Segoe UI", "font_size": 20},
        # Cross out the assignment, then explain the correct operation.
        {"kind": "line", "start": (assignment[0] - 3, assignment[1] + 14),
         "end": (assignment[2] + 2, assignment[1] + 14), "color": RED},
        {"kind": "text", "start": (900, assignment[1] - 6),
         "text": "// Assignment mutates the user", "color": RED,
         "font_family": "Segoe UI", "font_size": 20},
        # A box and an arrow both point at the wrong arithmetic operator.
        {"kind": "rectangle", "start": (discount[0] - 4, discount[1] - 3),
         "end": (discount[0] + 18, discount[3] + 3), "color": RED},
        {"kind": "arrow", "start": (discount[0] + 185, discount[1] + 57),
         "end": (discount[0] + 26, discount[1] + 14), "color": RED},
        {"kind": "text", "start": (940, discount[1] + 11),
         "text": "// Wrong sign: subtract discount", "color": RED,
         "font_family": "Segoe UI", "font_size": 20},
        # The final index is one past the last array element.
        {"kind": "question", "center": (575, off_by_one[1] + 9),
         "size": 72, "color": RED},
        {"kind": "text", "start": (900, off_by_one[1] - 6),
         "text": "// Out of bounds: length - 1", "color": RED,
         "font_family": "Segoe UI", "font_size": 20},
    ]
    # The production annotation renderer ensures exported marks match Infershot.
    selector.draw_annotations(image, (0, 0, WIDTH, HEIGHT))


class DemoCanvas:
    """Rasterize the selector's own Canvas commands without opening a desktop window."""

    def __init__(self, image: Image.Image):
        self.image = image
        self.items: dict[int, dict] = {}
        self.order: list[int] = []
        self.next_id = 1

    def _create(self, kind: str, coords: tuple, options: dict) -> int:
        if len(coords) == 1 and isinstance(coords[0], (tuple, list)):
            coords = tuple(coords[0])
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {"kind": kind, "coords": coords, "options": options}
        self.order.append(item_id)
        return item_id

    def create_rectangle(self, *coords, **options):
        return self._create("rectangle", coords, options)

    def create_polygon(self, *coords, **options):
        return self._create("polygon", coords, options)

    def create_line(self, *coords, **options):
        return self._create("line", coords, options)

    def create_oval(self, *coords, **options):
        return self._create("oval", coords, options)

    def create_text(self, *coords, **options):
        return self._create("text", coords, options)

    def coords(self, item_id, *coords):
        self.items[item_id]["coords"] = coords

    def itemconfigure(self, item_id, **options):
        self.items[item_id]["options"].update(options)

    def delete(self, tag):
        targets = [item_id for item_id, item in self.items.items()
                   if tag == item_id or tag in item["options"].get("tags", ())]
        for item_id in targets:
            del self.items[item_id]
            self.order.remove(item_id)

    def tag_raise(self, target):
        targets = [item_id for item_id in self.order if
                   item_id == target or target in self.items[item_id]["options"].get("tags", ())]
        for item_id in targets:
            self.order.remove(item_id)
            self.order.append(item_id)

    @staticmethod
    def _paint(value, alpha=255):
        if not value:
            return None
        return (*tuple(bytes.fromhex(value.lstrip("#"))), alpha)

    @staticmethod
    def _pairs(coords):
        return list(zip(coords[::2], coords[1::2]))

    def render(self):
        overlay = Image.new("RGBA", self.image.size)
        draw = ImageDraw.Draw(overlay)
        for item_id in self.order:
            kind = self.items[item_id]["kind"]
            coords = self.items[item_id]["coords"]
            options = self.items[item_id]["options"]
            if options.get("state") == "hidden":
                continue
            alpha = 64 if options.get("stipple") else 255
            fill = self._paint(options.get("fill"), alpha)
            outline = self._paint(options.get("outline"))
            width = options.get("width", 1)
            if kind == "rectangle":
                draw.rectangle(coords, fill=fill, outline=outline, width=width)
            elif kind == "oval":
                draw.ellipse(coords, fill=fill, outline=outline, width=width)
            elif kind == "polygon":
                points = self._pairs(coords)
                if options.get("smooth"):
                    xs, ys = zip(*points)
                    radius = round(points[0][0] - min(xs))
                    draw.rounded_rectangle((min(xs), min(ys), max(xs), max(ys)),
                                           radius=radius, fill=fill, outline=outline, width=width)
                else:
                    draw.polygon(points, fill=fill, outline=outline, width=width)
            elif kind == "line":
                points = self._pairs(coords)
                draw.line(points, fill=fill, width=width, joint="curve")
                for start, end in ((points[-2], points[-1]), (points[1], points[0])):
                    if options.get("arrow") not in (infershot.tk.BOTH, infershot.tk.LAST):
                        break
                    if end == points[0] and options["arrow"] != infershot.tk.BOTH:
                        continue
                    angle = math.atan2(end[1] - start[1], end[0] - start[0])
                    length = options.get("arrowshape", (9, 11, 4))[1]
                    spread = options.get("arrowshape", (9, 11, 4))[2]
                    base = (end[0] - length * math.cos(angle), end[1] - length * math.sin(angle))
                    normal = (-math.sin(angle), math.cos(angle))
                    draw.polygon((end, (base[0] + spread * normal[0], base[1] + spread * normal[1]),
                                  (base[0] - spread * normal[0], base[1] - spread * normal[1])), fill=fill)
            elif kind == "text":
                family, size, *style = options["font"]
                typeface = "segoeuib.ttf" if "bold" in style else "segoeui.ttf"
                text_font = font(typeface, abs(size))
                draw.text(coords, options["text"], fill=fill, font=text_font, anchor="mm")
        composited = Image.alpha_composite(self.image.convert("RGBA"), overlay)
        self.image.paste(composited if self.image.mode == "RGBA" else composited.convert("RGB"))


def add_selector_ui(image: Image.Image) -> None:
    selector = infershot.RectSelector.__new__(infershot.RectSelector)
    selector.width, selector.height = image.size
    selector.rect = SELECTION
    selector.active_tool = "question"
    selector.current_color = RED
    selector.selected_color_index = 0
    selector.hover_tool = None
    selector.canvas = DemoCanvas(image)
    selector.rect_id = selector.canvas.create_rectangle(0, 0, 0, 0,
        outline="#00d4ff", width=2, state="hidden")
    selector.handles = [selector.canvas.create_rectangle(0, 0, 0, 0,
        fill="#00d4ff", outline="#001018", state="hidden") for _ in range(8)]
    selector.draw_rect()
    assert len(selector.toolbar_hitboxes) == len(selector.TOOLBAR_TOOLS) + len(infershot.CONFIG["colors"])
    selector.canvas.render()


def render_annotated(source: list[str]) -> Image.Image:
    image = Image.open(BACKGROUND).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("Background dimensions differ from the demo canvas")
    add_annotations(image, source)
    return image


def render_ui_overlay() -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    add_selector_ui(image)
    return image


def render_final() -> Image.Image:
    annotated = Image.open(ANNOTATED).convert("RGBA")
    ui_overlay = Image.open(UI_OVERLAY).convert("RGBA")
    if annotated.size != (WIDTH, HEIGHT) or ui_overlay.size != (WIDTH, HEIGHT):
        raise ValueError("Demo layers have mismatched dimensions")
    return Image.alpha_composite(annotated, ui_overlay).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?",
                        choices=("background", "annotations", "ui", "final", "all"), default="all")
    args = parser.parse_args()
    infershot.CONFIG = infershot.load_config()
    if infershot.CONFIG["colors"][:2] != [RED, GREEN]:
        raise ValueError("The public demo requires red and green as the first two configured colors")
    source = lines()
    if args.stage in {"background", "all"}:
        render_background(source).save(BACKGROUND, optimize=True)
        print(BACKGROUND)
    if args.stage in {"annotations", "all"}:
        if not BACKGROUND.exists():
            raise FileNotFoundError("Build the background stage first")
        render_annotated(source).save(ANNOTATED, optimize=True)
        print(ANNOTATED)
    if args.stage in {"ui", "all"}:
        render_ui_overlay().save(UI_OVERLAY, optimize=True)
        print(UI_OVERLAY)
    if args.stage in {"final", "all"}:
        if not ANNOTATED.exists() or not UI_OVERLAY.exists():
            raise FileNotFoundError("Build the annotation and UI layers first")
        render_final().save(FINAL, optimize=True)
        print(FINAL)


if __name__ == "__main__":
    main()
