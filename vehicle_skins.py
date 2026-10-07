#!/usr/bin/env python3
"""Give a ported vehicle paint, chrome and camo skins.

A CustomizationPreset names a MaterialOverride, so a "skin" is just another
override on the same material with a different AlbedoMap. That is the mechanism
behind wrap-style options, and it is what makes camo possible without recovering
the original author's paint zones.

    python vehicle_skins.py <mod.pak> <out.pak> --skin-dir <tga dir>
"""

from __future__ import annotations

import argparse
import re

from vehicle_pak import (check_meshes, is_mesh, join_mesh, read_pak, split_mesh,
                         validate_pak, write_pak, write_tga)

# Measured from a mod the game converted itself. ShadingMap is documented as
# R metalness, G roughness, B ambient occlusion.
GLOSSY_PAINT = (38, 48, 235)      # roughness 0.19: automotive. 160 reads matte.
CHROME_SHADING = (250, 26, 240)   # metal, near-mirror
GLASS_SHADING = (10, 30, 240)
FLAT_NORMAL = (128, 128, 255)

PRESET_FILE = "classes/customization_presets/customization_preset.xml"

# 2020 Tundra TRD Pro factory colours. Override with --palette for another truck.
FACTORY_PAINT = [
    ("Super White", 242, 242, 240), ("Silver Sky Metallic", 186, 189, 192),
    ("Cement", 154, 154, 146), ("Magnetic Gray Metallic", 88, 92, 96),
    ("Midnight Black Metallic", 26, 26, 28), ("Voodoo Blue", 99, 183, 214),
    ("Army Green", 106, 110, 85), ("Barcelona Red Metallic", 140, 24, 32),
    ("Quicksand", 198, 178, 148), ("Smoked Mesquite", 92, 74, 64),
]
CHROME = [("Chrome", 225, 228, 232), ("Gold Chrome", 214, 176, 92),
          ("Blue Chrome", 120, 158, 198), ("Black Chrome", 58, 60, 66)]


def make_support_textures(body: str, out_dir: str) -> None:
    """The shading maps and the no-tint mask every skin set needs."""
    from PIL import Image
    flat = lambda rgb, n=1024: Image.new("RGB", (n, n), rgb)      # noqa: E731
    write_tga(f"{out_dir}/{body}__sh_d.tga", flat(GLOSSY_PAINT))
    write_tga(f"{out_dir}/cromo__sh_d.tga", flat(CHROME_SHADING))
    write_tga(f"{out_dir}/glass__sh_d.tga", flat(GLASS_SHADING))
    # R=0 means "no paint zone", so a patterned skin shows unmodified
    write_tga(f"{out_dir}/{body}_notint__d.tga", flat((0, 0, 0), 64))


def skin_defs(body: str, camo: list[str]) -> list[dict]:
    """chrome, then one entry per camo texture found in the skin directory."""
    out = [{"name": "skin_chrome", "albedo": f"trucks/{body}_wt__d.tga",
            "tint": f"trucks/{body}_cc__d.tga", "shading": "trucks/cromo__sh_d.tga"}]
    for c in camo:
        out.append({"name": f"skin_{c}", "albedo": f"trucks/{body}_{c}__d.tga",
                    "tint": f"trucks/{body}_notint__d.tga"})
    return out


def inject_overrides(members: dict[str, bytes], skins: list[dict]) -> tuple[int, int]:
    """Add each skin to every mesh that already carries skin_00.

    Mirror whatever materials skin_00 targets in THAT mesh. Add the skin only to
    the body and the body goes camo while the bumpers and rack stay factory.
    """
    meshes = adds = 0
    for name, blob in list(members.items()):
        if not is_mesh(name):
            continue
        xml, geo = split_mesh(blob)
        if "</MaterialOverrides>" not in xml:
            continue
        targets, seen = [], set()
        for m in re.finditer(r"<MaterialOverride[\s\S]*?/>", xml):
            if not re.search(r'\bName="skin_00"', m.group(0)):
                continue
            t = re.search(r'TargetMaterialName="([^"]+)"', m.group(0))
            if t and t.group(1) not in seen:
                seen.add(t.group(1))
                targets.append(t.group(1))
        if not targets:
            continue
        block = ""
        for s in skins:
            if f'Name="{s["name"]}"' in xml:        # never double-inject
                continue
            for t in targets:
                block += (f'\t\t<MaterialOverride\n\t\t\tAlbedoMap="{s["albedo"]}"\n'
                          f'\t\t\tName="{s["name"]}"\n'
                          + (f'\t\t\tShadingMap="{s["shading"]}"\n' if s.get("shading") else "")
                          + f'\t\t\tTargetMaterialName="{t}"\n'
                          f'\t\t\tTintMap="{s["tint"]}"\n\t\t/>\n')
                adds += 1
        if not block:
            continue
        xml = xml.replace("</MaterialOverrides>", block + "\t</MaterialOverrides>")
        members[name] = join_mesh(xml, geo)
        meshes += 1
    return meshes, adds


def build_presets(truck: str, paint, camo_presets) -> tuple[str, list[str]]:
    """Ids must be unique AND contiguous from 0.

    The docs are explicit: a duplicate Id makes the game ignore that preset, and
    a gap creates superfluous non-functional buttons.
    """
    rows, labels, i = [], [], 0
    g = lambda c: f"g({c[0]}; {c[1]}; {c[2]})"                    # noqa: E731

    def add(name, override, t1, t2, t3):
        nonlocal i
        rows.append(f'\t\t<CustomizationPreset Id="{i}" MaterialOverrideName="{override}" '
                    f'TintColor1="{g(t1)}" TintColor2="{g(t2)}" TintColor3="{g(t3)}" />')
        labels.append(f"{i:>3}  {override:<13} {name}")
        i += 1

    # All three tints the same: only TintColor1 renders unless the tint mask has
    # real green and blue zones, so an honest swatch shows one colour.
    for n, r, gg, b in paint:
        add(n, "skin_00", (r, gg, b), (r, gg, b), (r, gg, b))
    for n, r, gg, b in CHROME:
        add(n, "skin_chrome", (r, gg, b), (r, gg, b), (r, gg, b))
    for n, override, a, b2, c in camo_presets:
        add(n, override, a, b2, c)                 # cue colours; camo never tints

    return ("<TruckSet>\n\t<Truck Name=\"" + truck + "\">\n"
            + "\n".join(rows) + "\n\t</Truck>\n</TruckSet>\n"), labels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pak")
    ap.add_argument("out")
    ap.add_argument("--body", default="carroceria",
                    help="the paintable body material, default carroceria")
    ap.add_argument("--camo", nargs="*", default=["jungle", "digital", "desert"],
                    help="camo suffixes; expects trucks/<body>_<name>__d.tga")
    ap.add_argument("--truck", help="truck name for the preset file; read from the pak if omitted")
    ap.add_argument("--write-textures", metavar="DIR",
                    help="also write the shading maps and no-tint mask as .tga here, "
                         "ready for ResourceConverter. Required for a new vehicle.")
    a = ap.parse_args()

    if a.write_textures:
        make_support_textures(a.body, a.write_textures)
        print(f"support textures written to {a.write_textures}")

    members = read_pak(a.pak)
    original = dict(members)

    truck = a.truck
    if not truck:
        cls = next((n for n in members if re.match(r"classes/trucks/[^/]+\.xml$", n)), None)
        truck = cls.split("/")[-1][:-4] if cls else "truck"

    skins = skin_defs(a.body, a.camo)
    meshes, adds = inject_overrides(members, skins)

    camo_cue = {
        "jungle":  ("Woodland Camo", (106, 108, 74), (74, 78, 52), (62, 54, 40)),
        "digital": ("Woodland Digital", (74, 92, 58), (52, 68, 42), (96, 108, 74)),
        "desert":  ("Desert Digital", (198, 180, 146), (166, 142, 104), (128, 102, 72)),
    }
    camo_presets = [(camo_cue.get(c, (c.title(), (120, 120, 120), (90, 90, 90), (60, 60, 60)))[0],
                     f"skin_{c}", *camo_cue.get(c, (None, (120, 120, 120), (90, 90, 90), (60, 60, 60)))[1:])
                    for c in a.camo]
    xml, labels = build_presets(truck, FACTORY_PAINT, camo_presets)
    members[PRESET_FILE] = xml.encode("utf-8")

    problems = check_meshes(members, original)
    if problems:
        for p in problems:
            print(f"  ! {p}")
        raise SystemExit("mesh integrity check failed; nothing written")

    write_pak(a.out, members)
    print(f"meshes given skins : {meshes}")
    print(f"overrides added    : {adds}")
    print(f"presets            : {len(labels)} (Id 0-{len(labels) - 1})")
    for l in labels:
        print("   " + l)
    print(f"entries {validate_pak(a.out)}  ->  {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
