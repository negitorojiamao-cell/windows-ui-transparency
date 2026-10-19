"""Build the multi-size Windows .ico from the checked-in app icon PNG."""
from __future__ import annotations

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PNG = ASSETS / "windows-ui-transparency-icon.png"
ICO = ASSETS / "windows-ui-transparency.ico"


def main() -> None:
    if not PNG.exists():
        raise FileNotFoundError(
            f"Missing icon source: {PNG}. The icon PNG must be included in the repository."
        )
    image = Image.open(PNG).convert("RGBA")
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(
        ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated {ICO}")


if __name__ == "__main__":
    main()
