#!/usr/bin/env python3
"""Turn a real camouflage swatch into a game-ready truck skin.

A photographed swatch is not a texture: it has a lighting gradient, its edges do
not meet, and its pattern is usually too coarse once wrapped onto a vehicle.
This fixes all three, then writes the TGA that ResourceConverter expects.

    python camo_from_source.py in.png out.tga --tile 2
    python camo_from_source.py in.jpg out.tga --tile 2 --hue 60   # tan -> green
"""

from __future__ import annotations

import argparse
import struct

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vehicle_pak import write_tga
from PIL import Image, ImageFilter


def square_crop(im: Image.Image) -> Image.Image:
    s = min(im.size)
    l = (im.width - s) // 2
    t = (im.height - s) // 2
    return im.crop((l, t, l + s, t + s))


def flat_field(im: Image.Image, strength: float = 0.85) -> Image.Image:
    """Remove the slow lighting gradient a photographed swatch always carries.

    Divide by a heavily blurred copy of itself and re-centre on the mean. Without
    this the pattern reads as 'dirty' on one side of the vehicle.
    """
    blur = im.filter(ImageFilter.GaussianBlur(im.width / 8))
    out = Image.new("RGB", im.size)
    src, bl, dst = im.load(), blur.load(), out.load()
    mean = [sum(c) / (im.width * im.height) for c in
            (im.getchannel(i).getdata() for i in range(3))]
    for y in range(im.height):
        for x in range(im.width):
            p, b = src[x, y], bl[x, y]
            dst[x, y] = tuple(
                min(255, max(0, int(p[i] + (mean[i] - b[i]) * strength)))
                for i in range(3))
    return out


def make_seamless(im: Image.Image, feather: int = 0) -> Image.Image:
    """Offset by half, then blend the cross seam that the offset exposes.

    Mirror-tiling would also be seamless but produces obvious symmetry; camo
    shows that badly. This keeps the pattern irregular.
    """
    w, h = im.size
    feather = feather or w // 8
    rolled = Image.new("RGB", (w, h))
    rolled.paste(im.crop((w // 2, h // 2, w, h)), (0, 0))
    rolled.paste(im.crop((0, h // 2, w // 2, h)), (w - w // 2, 0))
    rolled.paste(im.crop((w // 2, 0, w, h // 2)), (0, h - h // 2))
    rolled.paste(im.crop((0, 0, w // 2, h // 2)), (w - w // 2, h - h // 2))

    # mask is opaque away from the new seams and fades across them
    mask = Image.new("L", (w, h), 255)
    px = mask.load()
    for y in range(h):
        dy = min(abs(y - h // 2), feather)
        for x in range(w):
            dx = min(abs(x - w // 2), feather)
            px[x, y] = int(255 * min(dx, dy) / feather)
    return Image.composite(rolled, im.filter(ImageFilter.GaussianBlur(1)), mask)


def shift_hue(im: Image.Image, degrees: float) -> Image.Image:
    h, s, v = im.convert("HSV").split()
    off = int(degrees / 360 * 255) & 0xFF
    return Image.merge("HSV", (h.point(lambda p: (p + off) & 0xFF), s, v)).convert("RGB")


def save_tga(im: Image.Image, path: str) -> None:
    """Delegates to the ONE verified writer.

    This used to be its own copy of the format, and it had the rows the wrong
    way up. A duplicated format writer is how a fix lands in one place and not
    the other three, so there is now exactly one.
    """
    write_tga(path, im)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--size", type=int, default=1024, help="output edge, default 1024")
    ap.add_argument("--tile", type=int, default=2,
                    help="repeats across the texture; higher = finer pattern")
    ap.add_argument("--hue", type=float, default=0.0,
                    help="hue shift in degrees, e.g. 60 turns desert tan to green")
    ap.add_argument("--saturation", type=float, default=1.0)
    ap.add_argument("--value", type=float, default=1.0,
                    help="brightness multiplier. A hue shift preserves lightness, so "
                         "recolouring a desert pattern to woodland needs about 0.6 "
                         "or it comes out a pale mint green")
    ap.add_argument("--no-flat-field", action="store_true")
    a = ap.parse_args()

    im = square_crop(Image.open(a.src).convert("RGB"))
    im = im.resize((512, 512), Image.LANCZOS)        # work small: flat_field is per-pixel
    if not a.no_flat_field:
        im = flat_field(im)
    im = make_seamless(im)
    if a.hue:
        im = shift_hue(im, a.hue)
    if a.saturation != 1.0 or a.value != 1.0:
        h, s, v = im.convert("HSV").split()
        s = s.point(lambda p: min(255, int(p * a.saturation)))
        v = v.point(lambda p: min(255, int(p * a.value)))
        im = Image.merge("HSV", (h, s, v)).convert("RGB")

    cell = a.size // a.tile
    im = im.resize((cell, cell), Image.LANCZOS)
    out = Image.new("RGB", (a.size, a.size))
    for ty in range(a.tile):
        for tx in range(a.tile):
            out.paste(im, (tx * cell, ty * cell))
    save_tga(out, a.dst)
    print(f"{a.dst}  {a.size}x{a.size}, pattern tiled {a.tile}x{a.tile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
