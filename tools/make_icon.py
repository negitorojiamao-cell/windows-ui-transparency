"""Create a crisp 1024px glass-style PNG and a multi-resolution Windows icon."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PNG = ASSETS / "windows-ui-transparency-icon.png"
ICO = ASSETS / "windows-ui-transparency.ico"
SIZE = 1024


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255
    )
    return mask


def gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int, int]]]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stops = sorted(stops, key=lambda item: item[0])
    for y in range(height):
        t = y / max(1, height - 1)
        color = stops[-1][1]
        for i in range(len(stops) - 1):
            start, ca = stops[i]
            end, cb = stops[i + 1]
            if start <= t <= end:
                fraction = (t - start) / max(1e-9, end - start)
                color = tuple(round(ca[k] * (1 - fraction) + cb[k] * fraction) for k in range(4))
                break
        draw.line((0, y, width, y), fill=color)
    return image


def paste_masked(dst: Image.Image, layer: Image.Image, xy: tuple[int, int], radius: int) -> None:
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), rounded_mask(layer.size, radius)))
    dst.alpha_composite(layer, xy)


def draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, outer: float, inner: float,
              fill: tuple[int, int, int, int]) -> None:
    points = []
    for i in range(8):
        angle = -math.pi / 2 + i * math.pi / 4
        radius = outer if i % 2 == 0 else inner
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    draw.polygon(points, fill=fill)


def create_icon() -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        (125, 105, 900, 925), radius=210, fill=(45, 135, 255, 150)
    )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60)))

    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (82, 70, 949, 954), radius=225, fill=(0, 0, 18, 170)
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(36)))

    tile = gradient(
        (850, 870),
        [(0, (46, 113, 223, 255)), (.34, (19, 65, 154, 255)),
         (.72, (12, 36, 102, 255)), (1, (6, 19, 56, 255))]
    )
    paste_masked(canvas, tile, (86, 64), 208)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((86, 64, 936, 934), radius=208,
                           outline=(238, 250, 255, 245), width=18)
    draw.rounded_rectangle((103, 81, 919, 917), radius=190,
                           outline=(104, 195, 255, 185), width=6)

    reflection = gradient((850, 350), [(0, (255, 255, 255, 62)), (1, (255, 255, 255, 0))])
    reflection.putalpha(ImageChops.multiply(reflection.getchannel("A"),
                                              rounded_mask(reflection.size, 180)))
    canvas.alpha_composite(reflection, (86, 64))

    pane_glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(pane_glow).rounded_rectangle(
        (193, 187, 770, 775), radius=60, fill=(77, 193, 255, 100)
    )
    canvas.alpha_composite(pane_glow.filter(ImageFilter.GaussianBlur(28)))

    panes = [
        (190, 200, 440, 432, (232, 248, 255, 242)),
        (468, 187, 726, 423, (207, 239, 255, 235)),
        (190, 462, 440, 701, (220, 237, 255, 231)),
        (468, 451, 726, 689, (183, 222, 255, 225)),
    ]
    draw = ImageDraw.Draw(canvas)
    for x1, y1, x2, y2, color in panes:
        draw.rounded_rectangle((x1 + 3, y1 + 9, x2 + 5, y2 + 11),
                               radius=31, fill=(3, 10, 45, 95))
        draw.rounded_rectangle((x1, y1, x2, y2), radius=31,
                               fill=color, outline=(255, 255, 255, 255), width=8)
        draw.rounded_rectangle((x1 + 11, y1 + 10, x2 - 11, y2 - 10),
                               radius=23, outline=(112, 197, 255, 200), width=4)
        draw.line((x1 + 30, y1 + 15, x2 - 35, y1 + 15),
                  fill=(255, 255, 255, 155), width=5)

    plate = (535, 446, 826, 773)
    glass = gradient(
        (plate[2] - plate[0], plate[3] - plate[1]),
        [(0, (199, 239, 255, 145)), (.5, (115, 190, 255, 84)), (1, (202, 163, 255, 80))]
    )
    paste_masked(canvas, glass, (plate[0], plate[1]), 42)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(plate, radius=42, outline=(245, 252, 255, 240), width=12)
    draw.rounded_rectangle((550, 461, 811, 758), radius=32,
                           outline=(103, 219, 255, 175), width=4)
    draw.line((572, 474, 779, 474), fill=(255, 255, 255, 140), width=7)

    ribbon_path = [(166, 754), (270, 790), (412, 779), (572, 731),
                   (706, 674), (811, 598), (839, 534)]
    ribbon_glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ribbon_glow).line(ribbon_path, fill=(63, 193, 255, 120), width=38, joint="curve")
    canvas.alpha_composite(ribbon_glow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(canvas)
    draw.line(ribbon_path, fill=(133, 221, 255, 190), width=23, joint="curve")
    draw.line([(x, y - 4) for x, y in ribbon_path],
              fill=(250, 253, 255, 210), width=5, joint="curve")

    draw = ImageDraw.Draw(canvas)
    draw_star(draw, 805, 333, 68, 15, (252, 253, 255, 248))
    draw_star(draw, 859, 430, 27, 8, (219, 242, 255, 230))
    draw.ellipse((165, 130, 190, 155), fill=(255, 255, 255, 190))
    draw.ellipse((825, 135, 837, 147), fill=(255, 255, 255, 200))
    return canvas


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = create_icon()
    icon.save(PNG, optimize=True, compress_level=9)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        ICO, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated 1024px icon: {PNG}")
    print(f"Generated multi-resolution Windows icon: {ICO}")


if __name__ == "__main__":
    main()
