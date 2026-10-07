#!/usr/bin/env python3
"""Pull a vehicle's meshes and textures out of a SnowRunner install.

Some SnowRunner mods are tuning reworks: they ship class XML only and reuse the
base game's own vehicle assets. Expeditions does not have those, so the port
needs them lifted across.

SnowRunner stores textures three ways, and which you take matters enormously:

    editor.pak            [textures]\\dds\\*.dds   <- standard DDS, DECODABLE
    shared_textures.pak   [textures]\\pct\\*.pct   <- Saber encoded, NOT decodable

Take the DDS. That is the difference between a vehicle with its real artwork and
one wearing flat colours.

    python extract_snowrunner.py jeep_wrangler jeep_cj7_renegade --out DIR
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import zipfile

from game_paths import GameNotFound, snowrunner_dir  # noqa: E402

try:
    SNOWRUNNER = snowrunner_dir()
except GameNotFound as _exc:
    SNOWRUNNER = ""
    _SR_ERROR = str(_exc)
else:
    _SR_ERROR = ""


def find_paks(root: str) -> list[str]:
    out = []
    for base, _d, files in os.walk(root):
        out += [os.path.join(base, f) for f in files if f.lower().endswith(".pak")]
    return out


def extract(paks: list[str], pattern: re.Pattern, out_dir: str,
            rename=None) -> list[tuple[str, int]]:
    os.makedirs(out_dir, exist_ok=True)
    got = []
    for p in paks:
        try:
            z = zipfile.ZipFile(p)
        except Exception:
            continue
        with z:
            for n in z.namelist():
                if not pattern.search(n):
                    continue
                flat = n.replace("\\", "/").split("/")[-1]
                if rename:
                    flat = rename(flat)
                dst = os.path.join(out_dir, flat)
                if os.path.exists(dst):
                    continue
                data = z.read(n)
                with open(dst, "wb") as f:
                    f.write(data)
                got.append((flat, len(data)))
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vehicles", nargs="+", help="mesh stems, e.g. jeep_wrangler")
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", default=SNOWRUNNER)
    a = ap.parse_args()

    paks = find_paks(a.root)
    print(f"scanning {len(paks)} SnowRunner paks under {a.root}")
    stems = "|".join(re.escape(v) for v in a.vehicles)

    meshes = extract(paks, re.compile(rf"\[meshes\][\\/].*(?:{stems})", re.I),
                     os.path.join(a.out, "meshes"))
    print(f"\nmeshes : {len(meshes)}")
    for n, s in meshes[:8]:
        print(f"   {s:>10,}  {n}")

    dds = extract(paks, re.compile(rf"\[textures\][\\/]dds[\\/].*(?:{stems})", re.I),
                  os.path.join(a.out, "dds"))
    print(f"\ndds    : {len(dds)}")
    for n, s in dds[:8]:
        print(f"   {s:>10,}  {n}")

    classes = extract(paks, re.compile(rf"classes[\\/].*(?:{stems}).*\.xml$", re.I),
                      os.path.join(a.out, "classes"))
    print(f"\nclasses: {len(classes)}")
    for n, s in classes[:8]:
        print(f"   {s:>10,}  {n}")

    # a mesh must still be [u32 len][xml][geometry] with the right magic
    bad = 0
    mdir = os.path.join(a.out, "meshes")
    for f in os.listdir(mdir) if os.path.isdir(mdir) else []:
        blob = open(os.path.join(mdir, f), "rb").read()
        if len(blob) < 8:
            bad += 1
            continue
        n = struct.unpack_from("<I", blob, 0)[0]
        if n > len(blob) or blob[4 + n:4 + n + 4] != bytes.fromhex("63ef3301"):
            print(f"   ! {f}: not a mesh container")
            bad += 1
    print(f"\nmesh containers valid: {len(meshes) - bad}/{len(meshes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
