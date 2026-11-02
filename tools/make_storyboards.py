"""Compose the storyboard figures from captured screens: docs/storyboard_<n>.png (and _a, _b halves).

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
    "storyboard_1": ("Three readings narrowed, then an error all three share", [
        ("s1_1.png", "Asked where three readings differ"),
        ("s1_2.png", "Yes; where the last two differ"),
        ("s1_3.png", "Yes; then a probe: leaving"),
        ("s1_4.png", "Yes; no reading turns it off"),
        ("s1_5.png", "Adds the rule; reviews it"),
        ("s1_6.png", "Saves; only now is it stored"),
    ]),
    "storyboard_2": ("No, Not sure, then Back to change an answer", [
        ("s2_1.png", "Asked where two readings differ"),
        ("s2_2.png", "No; then a probe: arriving"),
        ("s2_3.png", "Yes; offered an arrival rule"),
        ("s2_4.png", "Adds it; last question: leaving"),
        ("s2_5.png", "Not sure; the gap is stated"),
        ("s2_6.png", "Back, Yes, Add: off rule added"),
    ]),
    "storyboard_3": ("A decline, then one confident reading still checked", [
        ("s3_1.png", "Asks for a door lock: declined"),
        ("s3_2.png", "Edits; probe: dark at home"),
        ("s3_3.png", "Yes; offered a sunset rule"),
        ("s3_4.png", "Adds it; then a probe: leaving"),
        ("s3_5.png", "Yes; offered the off rule"),
        ("s3_6.png", "Adds it; reviews three rules"),
    ]),
}

COL_W, GAP, MARGIN, LABEL_H, TITLE_H = 500, 26, 30, 58, 64
BG, PANEL, INK, MUTED, ACCENT = "#ffffff", "#f4f5f7", "#1f2328", "#57606a", "#1f5fbf"


def font(name, size):
    for candidate in (name, "arial.ttf"):
        path = FONTS / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def compose(name, title, frames, cols=3):
    """One image with every frame (docs/<name>.png), plus one image per row (<name>_a.png, _b.png)
    so the report can place a storyboard across two pages without shrinking it."""
    title_font, label_font, number_font = font("segoeuib.ttf", 32), font("segoeui.ttf", 24), font("segoeuib.ttf", 23)
    images = []
    for file, label in frames:
        im = Image.open(SCREENS / file).convert("RGB")
        scale = COL_W / im.width
        images.append((im.resize((COL_W, round(im.height * scale)), Image.LANCZOS), label))
    rows = [images[i:i + cols] for i in range(0, len(images), cols)]
    width = MARGIN * 2 + cols * COL_W + (cols - 1) * GAP

    def draw_rows(selected, first_number, heading):
        heights = [LABEL_H + max(im.height for im, _ in row) for row in selected]
        height = MARGIN + TITLE_H + sum(heights) + GAP * (len(selected) - 1) + MARGIN
        canvas = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((MARGIN, MARGIN), heading, font=title_font, fill=INK)
        y, n = MARGIN + TITLE_H, first_number - 1
        for row, row_h in zip(selected, heights):
            for c, (im, label) in enumerate(row):
                n += 1
                x = MARGIN + c * (COL_W + GAP)
                draw.rounded_rectangle([x, y, x + COL_W, y + row_h], radius=14, fill=PANEL)
                draw.ellipse([x + 10, y + 12, x + 44, y + 46], fill=ACCENT)
                draw.text((x + 27, y + 29), str(n), font=number_font, fill="#ffffff", anchor="mm")
                draw.text((x + 54, y + 29), label, font=label_font, fill=INK, anchor="lm")
                canvas.paste(im, (x, y + LABEL_H))
            y += row_h + GAP
        return canvas

    outputs = [(f"{name}.png", draw_rows(rows, 1, title))]
    for i, row in enumerate(rows):
        part = "ab"[i] if len(rows) <= 2 else str(i + 1)
        first = i * cols + 1
        outputs.append((f"{name}_{part}.png",
                        draw_rows([row], first, f"{title} ({first}–{first + len(row) - 1})")))
    for file, canvas in outputs:
        out = ROOT / "docs" / file
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
