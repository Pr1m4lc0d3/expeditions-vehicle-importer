#!/usr/bin/env python3
"""Regression tests for the texture format. Run after touching any skin tool.

    python test_texture_format.py

These exist because a vertically flipped TGA is invisible on a flat colour and
on a tiled pattern, and completely scrambles a real UV atlas. It shipped for
days behind flat-colour skins before a vehicle with genuine artwork exposed it.
Every check here has a negative control: a test that cannot fail is not a test.
"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vehicle_pak import write_tga                                  # noqa: E402

USER = os.path.join(os.path.expanduser("~"), "Documents", "My Games", "Expeditions")
SAMPLE = os.path.join(USER, "Media", "Mods", "tundra_test")
GAME_TGA = os.path.join(SAMPLE, "textures", "trucks", "mod_scout__d.tga")
GAME_DDS = os.path.join(SAMPLE, "prebuild", "textures", "dds", "trucks_mod_scout__d.dds")

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def read_tga(path):
    """Read a TGA the way the FORMAT defines it: rows bottom-up."""
    from PIL import Image
    b = open(path, "rb").read()
    w, h = struct.unpack_from("<HH", b, 12)
    px = b[16] // 8
    off = 18 + b[0]
    im = Image.frombytes("RGBA" if px == 4 else "RGB", (w, h),
                         bytes(b[off:off + w * h * px]))
    ch = im.split()
    im = Image.merge("RGB", (ch[2], ch[1], ch[0]))
    return im.transpose(Image.FLIP_TOP_BOTTOM)


def mae(a, b):
    a, b = a.resize((128, 128)), b.resize((128, 128))
    la, lb = list(a.getdata()), list(b.getdata())
    return sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2])
               for x, y in zip(la, lb)) / (3 * len(la))


def main() -> int:
    from PIL import Image
    tmp = os.path.join(os.environ.get("TEMP", "."), "_fmt_test.tga")

    print("header and footer")
    img = Image.new("RGB", (64, 32), (10, 20, 30))
    write_tga(tmp, img)
    b = open(tmp, "rb").read()
    w, h = struct.unpack_from("<HH", b, 12)
    check("dimensions", (w, h) == (64, 32), f"{w}x{h}")
    check("24-bit for no alpha", b[16] == 24, f"{b[16]}bpp")
    check("expected size", len(b) == 18 + 64 * 32 * 3 + 26, f"{len(b)} B")
    check("footer signature", b[-18:-1] == b"TRUEVISION-XFILE.")
    check("origin bit clear (bottom-up)", not (b[17] & 0x20), f"desc 0x{b[17]:02x}")

    img = Image.new("RGBA", (16, 16), (1, 2, 3, 128))
    write_tga(tmp, img, alpha_from_image=True)
    b = open(tmp, "rb").read()
    check("32-bit when alpha asked for", b[16] == 32, f"{b[16]}bpp")
    check("alpha depth in descriptor", (b[17] & 0x0F) == 8, f"desc 0x{b[17]:02x}")

    print("\nchannel order (BGR on disk)")
    img = Image.new("RGB", (4, 4), (200, 100, 50))
    write_tga(tmp, img)
    b = open(tmp, "rb").read()
    check("B,G,R order", (b[18], b[19], b[20]) == (50, 100, 200),
          f"{b[18]},{b[19]},{b[20]}")

    print("\nROW ORDER vs the game's own files")
    if os.path.exists(GAME_TGA) and os.path.exists(GAME_DDS):
        # the game's tga, read as the format defines, must match its own dds
        m = mae(read_tga(GAME_TGA), Image.open(GAME_DDS).convert("RGB"))
        check("game's tga reads correctly bottom-up", m < 2, f"MAE {m:.2f}")
        # our writer must reproduce the game's tga from that same dds
        write_tga(tmp, Image.open(GAME_DDS), alpha_from_image=True)
        m2 = mae(read_tga(tmp), read_tga(GAME_TGA))
        check("our output matches the game's tga", m2 < 2, f"MAE {m2:.2f}")
        # NEGATIVE CONTROL: a deliberate flip must be caught
        flipped = read_tga(tmp).transpose(Image.FLIP_TOP_BOTTOM)
        m3 = mae(flipped, read_tga(GAME_TGA))
        check("negative control: a flip IS detected", m3 > 10, f"MAE {m3:.2f}")
    else:
        print("  SKIP  no tundra_test sample mod on this machine")

    print("\nonly one writer owns the format")
    here = os.path.dirname(os.path.abspath(__file__))
    vehicle_tools = ["camo_from_source.py", "make_truck_skins.py", "port_vehicle.py",
                     "vehicle_skins.py", "vehicle_ui.py", "dds_to_tga.py"]
    rogue = []
    for f in vehicle_tools:
        p = os.path.join(here, f)
        if os.path.exists(p) and "TRUEVISION-XFILE" in open(p, encoding="utf-8").read():
            rogue.append(f)
    check("no vehicle tool writes TGA bytes itself", not rogue, ", ".join(rogue))

    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILURE(S): ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
