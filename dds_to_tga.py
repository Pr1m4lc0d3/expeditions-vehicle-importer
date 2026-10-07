#!/usr/bin/env python3
"""Convert SnowRunner .dds textures to the .tga that ResourceConverter wants.

DDS is a standard block-compressed format and decodes cleanly, which is the
whole reason lifting a vehicle out of SnowRunner's editor.pak beats trying to
read its .pct: one is a documented format, the other is Saber's own encoding.

Alpha matters and is decided by the name, not by the file: the postfix __d_a
means the albedo carries an alpha channel, __d means it does not. Writing 32-bit
where the engine expects 24 wastes memory on every mip.

    python dds_to_tga.py <dds dir> <tga dir>
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vehicle_pak import write_tga                                  # noqa: E402


def unflatten(name: str) -> str:
    """trucks_jeep_wrangler__d.dds -> trucks/jeep_wrangler__d.tga

    Pak entries are flattened with the folder as a prefix; the source tree the
    converter reads is nested. Only the FIRST underscore is a folder separator.
    """
    stem = os.path.splitext(name)[0]
    folder, _, rest = stem.partition("_")
    return f"{folder}/{rest}.tga" if rest else f"{stem}.tga"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--flat", action="store_true",
                    help="keep the flattened names instead of nesting by folder")
    a = ap.parse_args()

    from PIL import Image
    done = failed = 0
    for f in sorted(os.listdir(a.src)):
        if not f.lower().endswith(".dds"):
            continue
        try:
            im = Image.open(os.path.join(a.src, f))
            rel = f.rsplit(".", 1)[0] + ".tga" if a.flat else unflatten(f)
            out = os.path.join(a.dst, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            keep_alpha = "__d_a" in f.lower()
            write_tga(out, im.convert("RGBA" if keep_alpha else "RGB"),
                      alpha_from_image=keep_alpha)
            done += 1
        except Exception as e:                                     # noqa: BLE001
            print(f"  ! {f}: {e}")
            failed += 1
    print(f"converted {done}, failed {failed}  ->  {a.dst}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
