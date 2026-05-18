"""Render plain-text terminal output to a styled PNG (dark theme, monospace).

Used to produce smoke_tests_results.png and production_readiness.png without
needing screen-capture permission.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (30, 30, 30)
FG = (212, 212, 212)
GREEN = (78, 201, 176)
RED = (244, 71, 71)
YELLOW = (220, 220, 110)
HEADER_BG = (40, 40, 40)
PROMPT = (97, 175, 239)
PAD = 24
LINE_H = 22


def colour_for(line: str):
    s = line.strip()
    if "PASSED" in s or "[OK]" in s or "[PASS]" in s or "READY" in s:
        return GREEN
    if "FAILED" in s or "[FAIL]" in s or "Error" in s or "NOT READY" in s:
        return RED
    if "[SKIP]" in s or "warning" in s.lower():
        return YELLOW
    if s.startswith("===") or s.startswith("===="):
        return PROMPT
    return FG


def render(text: str, title: str, out_path: Path):
    font_path = "/System/Library/Fonts/Menlo.ttc"
    try:
        font = ImageFont.truetype(font_path, 14)
        title_font = ImageFont.truetype(font_path, 13)
    except OSError:
        font = ImageFont.load_default()
        title_font = font

    lines = text.rstrip().splitlines()
    width = max(900, min(1600, max((len(l) for l in lines), default=80) * 9 + PAD * 2))
    height = PAD * 2 + 32 + LINE_H * len(lines)

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([(0, 0), (width, 32)], fill=HEADER_BG)
    draw.text((PAD, 8), title, font=title_font, fill=FG)
    # Mac-style traffic lights
    for i, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse([(8 + i * 18, 10), (22 + i * 18, 24)], fill=color)

    y = 32 + PAD
    for line in lines:
        draw.text((PAD, y), line, font=font, fill=colour_for(line))
        y += LINE_H

    img.save(out_path, "PNG", optimize=True)
    print(f"Wrote {out_path} ({width}x{height})")


if __name__ == "__main__":
    src, dst, title = sys.argv[1], sys.argv[2], sys.argv[3]
    render(Path(src).read_text(), title, Path(dst))
