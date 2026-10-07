#!/usr/bin/env python3
"""Build a vehicle mod's textures for every platform, not just Windows.

mod.io hosts one upload per platform and serves each player the matching one,
which is why a published mod can declare windows, switch, ps4, ps5, xboxone and
xboxseriesx while the folder on your PC only ever contains `pc.pak`. A PC-only
build reaches PC players and nobody else.

THE PIPELINE, measured rather than inferred:

  1. `--all-pct --make-pct-headers` on a .tga produces TWO outputs, and the
     toolkit used to collect only the first:
         prebuild/textures/pct/<name>.pct   + .pct_header   <- PC
         prebuild/textures/nx/<name>.pct    + .pct_header   <- Switch
  2. `--make-console-pct` on that PC .pct produces the other four:
         <out>/<name>.pct/playstation_4/<name>.pct
         <out>/<name>.pct/playstation_5/<name>.pct
         <out>/<name>.pct/xbox_one/<name>.pct
         <out>/<name>.pct/xbox_series/<name>.pct

Two requirements that are not in the help text and cost an hour to find:

  * the `.pct_header` must exist beside the `.pct`, so step 1 needs
    `--make-pct-headers`. Without it step 2 answers
    `Can't load pct file "...", console textures was not created`.
  * the input `.pct` must live UNDER `-r`, exactly like `-i` on the tga pass.

Measured on one 4096-wide texture: pc 349,694 · nx64 158,438 ·
playstation_4 354,446 · xbox_one 354,446 · playstation_5 360,590 ·
xbox_series 360,590. PS4 and Xbox One come out BYTE-IDENTICAL; PS5 and Xbox
Series share a size but differ.

⚠ WHAT IS NOT VERIFIED. The texture generation above is measured. The PAK NAMING
is inferred: a mod's Windows textures ship in a file called literally `pc.pak`,
and the engine's own os_build_part_manager.cpp names the build parts `xbox_one`,
`playstation_4`, `playstation_5`, `xbox_series`, `nx64` -- the same tokens the
level packer uses for `level_<name>_playstation_4.pak`. So `<part>.pak` beside
`<Name>.pak` is the consistent reading, and the internal layout is kept the same
as pc.pak's. Confirming it needs one real console vehicle mod to look at, which
cannot be downloaded on a PC. Until then, treat the paks as a best reading and
the textures as solid.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game_paths import resource_converter  # noqa: E402
from vehicle_pak import validate_pak, write_pak  # noqa: E402

# build part -> where its .pct ends up. "pc" and "nx64" come straight out of the
# first pass; the rest come from --make-console-pct.
CONSOLE_PARTS = ("playstation_4", "playstation_5", "xbox_one", "xbox_series")
ALL_PARTS = ("pc", "nx64") + CONSOLE_PARTS

PAK_MEMBER = "prebuild/textures/pct/{name}"


def encode_all_platforms(skin_root: str, work: str, timeout: int = 300,
                         log=print) -> dict[str, dict[str, bytes]]:
    """Every .tga under <skin_root>/textures/trucks, for every platform.

    Returns {build_part: {pct filename: bytes}}. Runs the converter with its cwd
    inside `work`, never inside the game folder: `-o` resolves against the
    working directory, and a half-written prebuild\\ beside Expeditions.exe
    stops the game launching.
    """
    rc = resource_converter()
    run = os.path.abspath(os.path.join(work, "_convscratch"))
    os.makedirs(run, exist_ok=True)
    scratch = os.path.join(run, "prebuild")
    shutil.rmtree(scratch, ignore_errors=True)

    tdir = os.path.join(skin_root, "textures", "trucks")
    tgas = sorted(f for f in os.listdir(tdir) if f.lower().endswith(".tga"))
    out: dict[str, dict[str, bytes]] = {p: {} for p in ALL_PARTS}
    failed: list[str] = []

    try:
        # ---- pass 1: PC + Switch, with headers so the console pass can read them
        for i, f in enumerate(tgas, 1):
            stem = os.path.splitext(f)[0]
            cmd = [rc, "--all-pct", "--make-pct-headers", "-s",
                   "-r", skin_root,
                   "-i", f"textures/trucks/{f}",
                   "-o", f"prebuild/textures/pct/trucks_{stem}.pct"]
            r = subprocess.run(cmd, cwd=run, timeout=timeout,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                failed.append(f"{f} (pc/nx exit {r.returncode})")
            if i % 20 == 0:
                log(f"      pc+nx  {i}/{len(tgas)}")

        for part, sub in (("pc", "pct"), ("nx64", "nx")):
            d = os.path.join(scratch, "textures", sub)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.lower().endswith(".pct"):
                        with open(os.path.join(d, f), "rb") as fh:
                            out[part][f] = fh.read()
        log(f"      pc {len(out['pc'])}, nx64 {len(out['nx64'])}")

        # ---- pass 2: the four consoles, from the PC .pct
        # The converter will only read a .pct that sits under -r, so stage the
        # whole pass-1 output inside the skin root and clean it up afterwards.
        # Stage at exactly prebuild/textures/pct under -r. The converter is
        # fussy about this: the same file under _pcstage/ was refused.
        rel = os.path.join("prebuild", "textures", "pct")
        staged = os.path.join(skin_root, rel)
        shutil.rmtree(os.path.join(skin_root, "prebuild"), ignore_errors=True)
        src = os.path.join(scratch, "textures", "pct")
        if os.path.isdir(src):
            shutil.copytree(src, staged)
        cout = os.path.join(run, "_console")
        shutil.rmtree(cout, ignore_errors=True)

        try:
            names = sorted(f for f in os.listdir(staged)
                           if f.lower().endswith(".pct")) if os.path.isdir(staged) else []
            for i, f in enumerate(names, 1):
                cmd = [rc, "--make-console-pct", "-s",
                       "-r", skin_root,
                       "-i", f"{rel}/{f}".replace("\\", "/"),
                       "-o", f"_console/{f}"]
                r = subprocess.run(cmd, cwd=run, timeout=timeout,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if r.returncode != 0:
                    why = (r.stdout or b"").decode("utf-8", "replace").strip()
                    failed.append(f"{f} (console exit {r.returncode}) {why[:160]}")
                if i % 20 == 0:
                    log(f"      console {i}/{len(names)}")

            for f in names:
                for part in CONSOLE_PARTS:
                    p = os.path.join(cout, f, part, f)
                    if os.path.isfile(p):
                        with open(p, "rb") as fh:
                            out[part][f] = fh.read()
        finally:
            shutil.rmtree(os.path.join(skin_root, "prebuild"), ignore_errors=True)

        for part in CONSOLE_PARTS:
            log(f"      {part} {len(out[part])}")
        return out, failed
    finally:
        shutil.rmtree(scratch, ignore_errors=True)       # never leave it behind
        shutil.rmtree(os.path.join(run, "_console"), ignore_errors=True)


def write_platform_paks(built: dict[str, dict[str, bytes]], out_dir: str,
                        extra: dict[str, bytes] | None = None,
                        log=print) -> list[str]:
    """One pak per build part: pc.pak, nx64.pak, playstation_4.pak, ...

    `extra` is anything that must ride along in every platform pak, such as the
    sounds a mod keeps in pc.pak.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for part in ALL_PARTS:
        files = built.get(part) or {}
        if not files:
            log(f"   {part}: no textures, skipped")
            continue
        members = dict(extra or {})
        for name, data in files.items():
            members[PAK_MEMBER.format(name=name)] = data
        path = os.path.join(out_dir, f"{part}.pak")
        write_pak(path, members)
        log(f"   {part + '.pak':<22} {len(members):>4} entries  "
            f"{os.path.getsize(path):>12,} B  (validated {validate_pak(path)})")
        written.append(path)
    return written


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skin_root", help="folder containing textures/trucks/*.tga")
    ap.add_argument("out_dir", help="where to write the platform paks")
    ap.add_argument("--work", default="_console_build", help="scratch directory")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    built, failed = encode_all_platforms(a.skin_root, a.work)
    for f in failed:
        print("   FAILED " + f)
    write_platform_paks(built, a.out_dir)
    raise SystemExit(1 if failed else 0)
