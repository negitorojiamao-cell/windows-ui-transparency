"""Generate the Windows UI Transparency app icon (ICO + PNG) using Pillow."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
S = 1024


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                           radius=radius, fill=255)
    return mask


def vertical_gradient(size: tuple[int, int],
                      top: tuple[int, int, int, int],
                      bottom: tuple[int, int, int, int]) -> Image.Image:
    w, h = size
    im = Image.new("RGBA", size)
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(4))
        for x in range(w):
            px[x, y] = row
    return im


def create_icon() -> Image.Image:
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((95, 85, 929, 939), radius=220,
                                           fill=(21, 139, 255, 130))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(58)))

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((82, 75, 942, 945), radius=220,
                                             fill=(0, 3, 20, 190))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(42)))

    rect = (70, 55, 944, 929)
    tile_size = (rect[2] - rect[0] + 1, rect[3] - rect[1] + 1)
    tile = vertical_gradient(tile_size, (18, 135, 255, 255), (4, 28, 94, 255))
    tile.putalpha(ImageChops.multiply(tile.getchannel("A"), rounded_mask(tile_size, 205)))
    canvas.alpha_composite(tile, (rect[0], rect[1]))

    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(rect, radius=205, outline=(219, 244, 255, 245), width=17)
    d.rounded_rectangle((89, 74, 925, 910), radius=187,
                        outline=(100, 191, 255, 200), width=7)

    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shine_rect = (108, 88, 906, 390)
    shine_layer = Image.new("RGBA", (shine_rect[2] - shine_rect[0],
                                     shine_rect[3] - shine_rect[1]), (255, 255, 255, 30))
    shine_layer.putalpha(ImageChops.multiply(
        shine_layer.getchannel("A"),
        rounded_mask(shine_layer.size, 175)))
    shine.alpha_composite(shine_layer, (shine_rect[0], shine_rect[1]))
    canvas.alpha_composite(shine)

    panes = [
        (210, 220, 455, 450),
        (492, 204, 744, 432),
        (210, 486, 455, 717),
        (492, 468, 744, 700),
    ]
    d = ImageDraw.Draw(canvas)
    for pane in panes:
        d.rounded_rectangle(pane, radius=32, fill=(244, 251, 255, 246),
                            outline=(255, 255, 255, 255), width=6)

    glass = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glass_rect = (540, 465, 827, 793)
    glass_tile = vertical_gradient(
        (glass_rect[2] - glass_rect[0] + 1, glass_rect[3] - glass_rect[1] + 1),
        (226, 248, 255, 125), (130, 208, 255, 72))
    glass_tile.putalpha(ImageChops.multiply(glass_tile.getchannel("A"),
                                             rounded_mask(glass_tile.size, 42)))
    glass.alpha_composite(glass_tile, (glass_rect[0], glass_rect[1]))
    gd = ImageDraw.Draw(glass)
    gd.rounded_rectangle(glass_rect, radius=42, outline=(255, 255, 255, 225), width=11)
    gd.line((575, 493, 787, 493), fill=(255, 255, 255, 115), width=8)
    canvas.alpha_composite(glass)

    d = ImageDraw.Draw(canvas)
    cx, cy = 802, 188
    d.polygon([(cx, cy - 43), (cx + 11, cy - 10), (cx + 42, cy),
               (cx + 11, cy + 10), (cx, cy + 42), (cx - 10, cy + 10),
               (cx - 40, cy), (cx - 10, cy - 10)], fill=(255, 255, 255, 238))
    return canvas


def main() -> None:
    icon = create_icon()
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(
        ASSETS / "windows-ui-transparency-icon.png", optimize=True)
    icon.save(ASSETS / "windows-ui-transparency.ico", format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Generated assets/windows-ui-transparency.ico and .png")


if __name__ == "__main__":
    main()
