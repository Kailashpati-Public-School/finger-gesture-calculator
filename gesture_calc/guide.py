"""
guide.py
--------
Draws the "which finger sign means what" chart shown in the start-up popup.

The picture is generated with Pillow from the SAME tables that the recogniser
uses (gestures.py), so the guide can never get out of sync with the real signs.

Save it as a PNG (for the README) with:   python -m gesture_calc.guide
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from .gestures import DIGIT_PATTERNS, SPECIAL_PATTERNS

# ---- layout -----------------------------------------------------------------
COLS, CELL_W, CELL_H, PAD = 4, 240, 300, 12
GREEN, GRAY, SKIN = (46, 160, 67), (190, 190, 190), (247, 220, 190)
INK, MUTED, CARD, BORDER = (25, 25, 25), (110, 110, 110), (255, 255, 255), (210, 210, 210)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Try a few common fonts, fall back to Pillow's built-in one."""
    names = ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _capsule(d: ImageDraw.ImageDraw, p1: Tuple[float, float], p2: Tuple[float, float], width: int, fill) -> None:
    """A thick line with round ends (used for fingers)."""
    d.line([p1, p2], fill=fill, width=width)
    r = width / 2
    for x, y in (p1, p2):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _draw_hand(d: ImageDraw.ImageDraw, cx: int, top: int, pattern: Tuple[int, ...]) -> None:
    """Very simple hand icon: green finger = UP, gray stub = folded."""
    d.rounded_rectangle([cx - 50, top + 105, cx + 50, top + 195], radius=24, fill=SKIN, outline=(200, 160, 120), width=2)
    thumb, index, middle, ring, pinky = pattern

    base_y = top + 118
    for dx, length, up in ((-33, 82, index), (-11, 94, middle), (11, 84, ring), (33, 64, pinky)):
        tip_y = base_y - (length if up else 6)
        _capsule(d, (cx + dx, base_y), (cx + dx, tip_y), 20, GREEN if up else GRAY)

    # thumb sticks out sideways when up, lies on the palm when folded
    if thumb:
        _capsule(d, (cx - 44, top + 165), (cx - 92, top + 128), 20, GREEN)
    else:
        _capsule(d, (cx - 44, top + 165), (cx - 26, top + 158), 20, GRAY)


def _center_text(d, cx: int, y: int, text: str, font, fill) -> None:
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def _cells():
    """(pattern, title, subtitle) for every card, in display order."""
    names = {0: "Fist", 1: "Index finger", 2: "Index + Middle", 3: "3 fingers", 4: "4 fingers", 5: "Open palm"}
    for pattern, digit in DIGIT_PATTERNS.items():
        yield pattern, f"Digit {digit}", names[digit]
    titles = {
        "+": ("Plus  +", "Thumb only"), "-": ("Minus  -", "Pinky only"),
        "*": ("Multiply  x", "Index + Pinky"), "/": ("Divide  /", "Thumb + Pinky"),
        "=": ("Equals  =", "Thumb + Index"), "C": ("Clear  C", "Thumb+Index+Middle"),
        "BACK": ("Backspace", "Middle+Ring+Pinky"),
    }
    for pattern, gesture in SPECIAL_PATTERNS.items():
        yield pattern, *titles[gesture.value]


def build_guide_image() -> Image.Image:
    cards = list(_cells())
    total = len(cards) + 1  # +1 for the "6 to 9" info card
    rows = -(-total // COLS)  # ceiling division
    img = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), (245, 247, 250))
    d = ImageDraw.Draw(img)
    title_font, sub_font = _font(27, bold=True), _font(17)

    def card_box(i: int):
        x, y = (i % COLS) * CELL_W, (i // COLS) * CELL_H
        box = [x + PAD, y + PAD, x + CELL_W - PAD, y + CELL_H - PAD]
        d.rounded_rectangle(box, radius=18, fill=CARD, outline=BORDER, width=2)
        return x + CELL_W // 2, y

    for i, (pattern, title, subtitle) in enumerate(cards):
        cx, y = card_box(i)
        _draw_hand(d, cx, y + 20, pattern)
        _center_text(d, cx, y + 232, title, title_font, INK)
        _center_text(d, cx, y + 266, subtitle, sub_font, MUTED)

    # Last card: how to make 6..9 with two hands
    cx, y = card_box(len(cards))
    _center_text(d, cx, y + 40, "Digits 6 - 9", title_font, INK)
    _center_text(d, cx, y + 90, "Show BOTH hands", sub_font, MUTED)
    _center_text(d, cx, y + 120, "Fingers add up", sub_font, MUTED)
    _center_text(d, cx, y + 165, "5 + 1 = 6", sub_font, GREEN)
    _center_text(d, cx, y + 195, "5 + 4 = 9", sub_font, GREEN)
    return img


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "docs" / "gesture_guide.png"
    out.parent.mkdir(exist_ok=True)
    build_guide_image().save(out)
    print(f"Saved {out}")
