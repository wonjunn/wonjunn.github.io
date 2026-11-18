#!/usr/bin/env python3
"""Make the web copy of a city's photo for the map.

    python3 _map/add_photo.py <source image> <city slug>

Example:  python3 _map/add_photo.py ~/Downloads/IMG_1234.HEIC philadelphia

It writes photos/<slug>.jpg at the repo root, next to the main page that carries the map, and prints the fields
to put into _map/cities.json. The source is only read. The copy
  - is at most 800px on its long side (the card shows it about 150 to 190px wide, so that is plenty),
  - is turned upright and converted to sRGB,
  - carries no metadata: no location, no date, no camera or phone details.
Needs macOS `sips` (to read HEIC and convert colors) and Pillow (to write the clean copy).
Then run  python3 -I _map/build.py  to draw the city into the page.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
LONG_SIDE = 800
SRGB = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"


def main():
    source, slug = Path(sys.argv[1]).expanduser(), sys.argv[2]
    out = ROOT / "photos" / f"{slug}.jpg"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        # sips reads HEIC and converts the colors to sRGB; this in-between file still has the metadata and is thrown away
        step = Path(tmp) / "step.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", "-m", SRGB, str(source), "--out", str(step)],
                       check=True, capture_output=True)
        with Image.open(step) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
            # a new image holds the pixels only, so nothing from the source's metadata can ride along
            clean = Image.new("RGB", im.size)
            clean.paste(im)
            clean.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    with Image.open(out) as check:
        left = {k: v for k, v in check.info.items() if k not in ("jfif", "jfif_version", "jfif_unit", "jfif_density", "progressive", "progression")}
        assert not check.getexif() and not left, f"metadata left in the copy: {dict(check.getexif())} {left}"
        w, h = check.size
    print(f"wrote {out.relative_to(ROOT)} ({w}x{h}, {out.stat().st_size / 1024:.0f}KB, no metadata)")
    print(f'for _map/cities.json:  "photo": "photos/{slug}.jpg", "photo_w": {w}, "photo_h": {h}')


if __name__ == "__main__":
    main()
