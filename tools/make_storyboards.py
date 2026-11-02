"""Compose the storyboard figures from captured screens: docs/storyboard_<n>.png.

    py -3.11 tools/make_storyboards.py

Every frame is a real screen of the running prototype, captured by tools/capture.mjs. The labels
are short on purpose: who acts and what happens. Explanations belong in the report text.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "docs" / "screens"
FONTS = Path("C:/Windows/Fonts")

STORIES = {
    "storyboard_1": ("A vague request: two readings and an error they share", [
        ("s1_1.png", "Person types a vague request"),
        ("s1_2.png", "Asked where the two readings differ"),
        ("s1_3.png", "Yes; then a bug-class probe: leaving"),
        ("s1_4.png", "Yes; no reading turns the light off"),
        ("s1_5.png", "Adds the rule; reads the restatement"),
        ("s1_6.png", "Chooses Save; only now is it saved"),
    ]),
}

COL_W, GAP, MARGIN, LABEL_H, TITLE_H = 760, 36, 36, 64, 70
BG, PANEL, INK, MUTED, ACCENT = "#ffffff", "#f4f5f7", "#1f2328", "#57606a", "#1f5fbf"


def font(name, size):
    for candidate in (name, "arial.ttf"):
        path = FONTS / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def compose(name, title, frames, cols=2):
    title_font, label_font, number_font = font("segoeuib.ttf", 34), font("segoeui.ttf", 27), font("segoeuib.ttf", 27)
    images = []
    for file, label in frames:
        im = Image.open(SCREENS / file).convert("RGB")
        scale = COL_W / im.width
        images.append((im.resize((COL_W, round(im.height * scale)), Image.LANCZOS), label))
    rows = [images[i:i + cols] for i in range(0, len(images), cols)]
    heights = [LABEL_H + max(im.height for im, _ in row) for row in rows]
    width = MARGIN * 2 + cols * COL_W + (cols - 1) * GAP
    height = MARGIN + TITLE_H + sum(heights) + GAP * (len(rows) - 1) + MARGIN
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, MARGIN), title, font=title_font, fill=INK)
    y, n = MARGIN + TITLE_H, 0
    for row, row_h in zip(rows, heights):
        for c, (im, label) in enumerate(row):
            n += 1
            x = MARGIN + c * (COL_W + GAP)
            draw.rounded_rectangle([x, y, x + COL_W, y + row_h], radius=14, fill=PANEL)
            draw.ellipse([x + 12, y + 14, x + 50, y + 52], fill=ACCENT)
            draw.text((x + 31, y + 33), str(n), font=number_font, fill="#ffffff", anchor="mm")
            draw.text((x + 62, y + 33), label, font=label_font, fill=INK, anchor="lm")
            canvas.paste(im, (x, y + LABEL_H))
        y += row_h + GAP
    out = ROOT / "docs" / f"{name}.png"
    canvas.save(out, optimize=True)
    print(f"wrote {out.relative_to(ROOT)} ({canvas.width}x{canvas.height})")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, (title, frames) in STORIES.items():
        if only and only != name:
            continue
        missing = [f for f, _ in frames if not (SCREENS / f).exists()]
        if missing:
            print(f"skip {name}: missing {', '.join(missing)} (run node tools/capture.mjs --stories first)")
            continue
        compose(name, title, frames)


if __name__ == "__main__":
    main()
