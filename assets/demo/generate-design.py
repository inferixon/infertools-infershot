"""Build the designer demo; stages mirror generate.py's independent layers."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

import generate as shared


DIRECTORY = Path(__file__).with_name("design")
BACKGROUND = DIRECTORY / "background.png"
ANNOTATED = DIRECTORY / "annotated.png"
UI_OVERLAY = shared.UI_OVERLAY
FINAL = shared.ROOT / "assets" / "infershot-design-demo.png"
RED, GREEN = shared.RED, shared.GREEN
INK, MUTED, PAPER = "#24352f", "#68756f", "#f5f3eb"


def label(draw, point, text, size=22, color=INK, bold=False, serif=False):
    filename = "pala.ttf" if serif else ("segoeuib.ttf" if bold else "segoeui.ttf")
    draw.text(point, text, font=shared.font(filename, size), fill=color, spacing=8)


def background():
    image = Image.new("RGB", (shared.WIDTH, shared.HEIGHT), "#171a21")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1600, 70), fill="#222630")
    label(draw, (42, 18), "form-and-field.design / draft", 25, "#eef2f7", bold=True)
    label(draw, (1320, 26), "DESIGN QA", 18, "#8e98a8")
    draw.rectangle(shared.SELECTION, fill=PAPER)

    # Intentional issue: two identical navigation items.
    label(draw, (96, 159), "form & field", 32, bold=True, serif=True)
    for x, text in ((866, "Home"), (1000, "Work"), (1134, "Work"), (1270, "About")):
        label(draw, (x, 169), text, 22)
    draw.rounded_rectangle((1400, 157, 1510, 201), radius=22, fill=INK)
    label(draw, (1422, 166), "Let's talk", 18, "#ffffff")
    draw.line((94, 230, 1510, 230), fill="#d9ddd4", width=1)

    label(draw, (96, 275), "INDEPENDENT DESIGN STUDIO", 17, MUTED, bold=True)
    label(draw, (94, 316), "Make room\nfor good ideas.", 64, serif=True)
    label(draw, (98, 476), "Thoughtful websites and useful digital products.\nBuilt around the people who use them.", 22, MUTED)

    # Positive example: an unmistakable, high-contrast primary action.
    draw.rounded_rectangle((98, 562, 348, 624), radius=12, fill=INK)
    label(draw, (123, 577), "Start a project", 23, "#ffffff", bold=True)
    draw.line((311, 594, 326, 594), fill="#ffffff", width=2)
    draw.line((321, 589, 327, 594, 321, 599), fill="#ffffff", width=2)

    # A simple graphic hero keeps attention on the review annotations.
    draw.rounded_rectangle((835, 275, 1510, 603), radius=24, fill="#e2e6dc")
    draw.ellipse((1150, 310, 1470, 630), fill="#c5d2bd")
    draw.rounded_rectangle((916, 320, 1124, 554), radius=16, fill="#fdfbf4")
    draw.rounded_rectangle((1138, 369, 1408, 532), radius=16, fill="#bf7656")
    label(draw, (941, 344), "F / F", 38, serif=True)
    draw.line((942, 411, 1090, 411), fill="#bdc8ba", width=5)
    draw.line((942, 434, 1060, 434), fill="#bdc8ba", width=5)
    draw.ellipse((942, 477, 985, 520), fill=INK)
    label(draw, (1165, 393), "Less noise.\nMore purpose.", 28, "#fff8ef", serif=True)
    label(draw, (863, 570), "A small studio. A considered approach.", 18, MUTED)

    label(draw, (96, 666), "Selected work", 37, serif=True)
    label(draw, (1300, 679), "View all projects  →", 18, MUTED)

    # The first two cards have a narrower gutter than the second pair.
    for box in ((96, 748, 480, 973), (556, 748, 960, 973), (1064, 748, 1510, 973)):
        draw.rounded_rectangle(box, radius=16, fill="#fffef9", outline="#d9ddd4", width=1)
    draw.rounded_rectangle((118, 770, 458, 827), radius=8, fill="#dce6d3")
    label(draw, (135, 782), "01 / Brand & web", 19, INK, bold=True)
    label(draw, (120, 849), "Northline", 30, serif=True)
    label(draw, (120, 898), "A clearer home for a growing brand.", 18, MUTED)
    label(draw, (120, 941), "Explore project  →", 17, INK, bold=True)

    draw.rounded_rectangle((578, 770, 938, 827), radius=8, fill="#eedccb")
    label(draw, (595, 782), "02 / Digital product", 19, INK, bold=True)
    label(draw, (580, 849), "Fold", 30, serif=True)
    # Intentional issue: an unexplained placeholder and faint link.
    label(draw, (866, 852), "TBD", 17, "#acb3aa")
    label(draw, (580, 898), "Tools that make everyday work easier.", 18, MUTED)
    label(draw, (580, 941), "Explore project  →", 17, "#d0d5ce")

    label(draw, (1090, 773), "DESIGN REVIEW", 17, MUTED, bold=True)
    label(draw, (1090, 814), "A second pair of eyes.", 27, serif=True)
    label(draw, (1090, 859), "Book a focused review of your site.", 18, MUTED)
    # Intentional issue: this card has no action button.
    return image


def annotation(kind, **properties):
    return {"kind": kind, "color": RED, **properties}


def note(point, text, color=RED):
    return annotation("text", start=point, text=text, color=color,
                      font_family="Segoe UI", font_size=18)


def annotations(image):
    selector = shared.infershot.RectSelector.__new__(shared.infershot.RectSelector)
    selector.annotations = [
        annotation("cross", center=(1163, 184), size=40),
        annotation("arrow", start=(1310, 261), end=(1193, 200)),
        note((1230, 266), "Duplicate nav item"),
        # Both arrowheads occupy the actual inter-card gutter.
        annotation("double_arrow", start=(484, 796), end=(552, 796)),
        note((390, 707), "Widen this gutter"),
        annotation("arrow", start=(507, 736), end=(528, 777)),
        annotation("question", center=(982, 861), size=54),
        annotation("freehand", points=[(581, 966), (630, 969), (680, 965), (739, 968)]),
        note((580, 985), "Low contrast"),
        annotation("rectangle", start=(1090, 900), end=(1480, 954)),
        annotation("arrow", start=(1450, 710), end=(1450, 894)),
        note((1090, 642), "Add component button"),
        annotation("arrow", start=(596, 600), end=(356, 594), color=GREEN),
        note((415, 629), "Good: clear primary action", GREEN),
    ]
    selector.draw_annotations(image, (0, 0, shared.WIDTH, shared.HEIGHT))
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", default="all",
                        choices=("background", "annotations", "ui", "final", "all"))
    stage = parser.parse_args().stage
    shared.infershot.CONFIG = shared.infershot.load_config()
    DIRECTORY.mkdir(exist_ok=True)
    if stage in ("background", "all"):
        background().save(BACKGROUND, optimize=True)
        print(BACKGROUND)
    if stage in ("annotations", "all"):
        annotations(Image.open(BACKGROUND).convert("RGB")).save(ANNOTATED, optimize=True)
        print(ANNOTATED)
    if stage in ("ui", "all"):
        shared.render_ui_overlay().save(UI_OVERLAY, optimize=True)
        print(UI_OVERLAY)
    if stage in ("final", "all"):
        composed = Image.alpha_composite(Image.open(ANNOTATED).convert("RGBA"),
                                        Image.open(UI_OVERLAY).convert("RGBA"))
        composed.convert("RGB").save(FINAL, optimize=True)
        print(FINAL)


if __name__ == "__main__":
    main()
