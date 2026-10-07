#!/usr/bin/env python3
"""Port a SnowRunner vehicle mod into Expeditions: A MudRunner Game.

Both games share the Saber mod format, so a SnowRunner truck's *meshes* load in
Expeditions untouched. Its *textures* do not: the `.pct` payloads are
SnowRunner-encoded and Expeditions cannot decode them, so every material renders
solid black. The container header is identical in both games, so you cannot tell
them apart by inspection -- only by the truck going black.

The fix is to hand Expeditions textures that its own encoder produced. This tool
automates that:

    analyze   report the textures, materials and artwork problems a mod has
    port      textures only: skin, encode, repack, install
    full      port, then store/garage artwork, then chrome and camo skins

Quick start:

    python port_vehicle.py analyze C:\\downloads\\some_truck_pc.zip

    python port_vehicle.py full C:\\downloads\\some_truck_pc.zip --id 5939782 \\
        --name Tundra --shot shot.png --box 1560 900 3700 1790 \\
        --safe 1545 340 3830 1795 --badge TRD --camo jungle digital desert

The artwork step needs an in-game screenshot, so the usual shape is: `port`
first to get the vehicle rendering, take a screenshot in the garage, then `full`
to finish it. Companion tools: vehicle_ui.py, vehicle_skins.py,
camo_from_source.py, all usable on their own.

Then launch the game and look at the truck. See `troubleshooting` in the guide
if it is still black.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

# ---------------------------------------------------------------- game paths

from game_paths import GameNotFound, expeditions_dir, user_dir  # noqa: E402

try:
    GAME = expeditions_dir()
except GameNotFound as _exc:
    # Not fatal at import: --help, analyze and the pak tools all work without
    # the game. The encoder step checks RESOURCE_CONVERTER and reports properly.
    GAME = ""
    _GAME_ERROR = str(_exc)
else:
    _GAME_ERROR = ""
RESOURCE_CONVERTER = (os.path.join(GAME, "Sources", "Bin", "ResourceConverter.exe")
                      if GAME else "")
USER = user_dir()
MODIO = os.path.join(USER, "base", "Mods", ".modio", "mods")
PROFILE_DIR = os.path.join(USER, "base", "storage")

# Flat colours keyed by material name. Spanish names are common because many
# SnowRunner authors are Spanish-speaking; add your own in palette.json.
DEFAULT_PALETTE = {
    "carroceria": [220, 220, 220],   # bodywork: near-white so the garage tint shows
    "negro": [25, 25, 27], "negrochasis": [30, 30, 32], "negrocasis": [30, 30, 32],
    "blanco": [225, 225, 225], "rojo": [170, 25, 25], "azul": [30, 60, 150],
    "verde": [40, 110, 50], "amarillo": [210, 180, 40], "naranja": [210, 120, 30],
    "cromo": [200, 200, 205], "dorado": [190, 150, 60], "plata": [190, 190, 195],
    "gris": [120, 120, 120], "grisclaro": [170, 170, 170], "grisoscuro": [70, 70, 70],
    "madera": [120, 80, 45], "madera1": [120, 80, 45], "cuero": [95, 65, 45],
    "ambar": [210, 130, 20], "interior": [55, 52, 50], "cruce": [235, 230, 200],
    "stop": [160, 20, 20], "faro": [235, 230, 200], "luz": [235, 230, 200],
    "carpadepredador": [70, 75, 55], "pantallita": [20, 25, 30],
    "glass": [60, 65, 70], "vidrio": [60, 65, 70],
    "tacometro": [35, 35, 38], "velocimetro": [35, 35, 38],
    # generic English fallbacks
    "white": [225, 225, 225], "black": [25, 25, 27], "red": [170, 25, 25],
    "chrome": [200, 200, 205], "grey": [120, 120, 120], "gray": [120, 120, 120],
}
# measured off a mod the game itself converted -- do not invent these
FLAT_NORMAL = [128, 128, 255]           # tangent-space normal
FLAT_SHADING = [20, 160, 205]           # R metalness, G roughness, B ambient occlusion
GLASS_ALPHA = 150
DEFAULT_SIZE = 256
TRANSLUCENT = re.compile(r"glass|vidrio|window", re.I)


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str) -> "NoReturn":                       # noqa: F821
    raise SystemExit(f"error: {msg}")


# ------------------------------------------------------------------ pak I/O

def pak_entries(path: str) -> dict[str, bytes]:
    """Every member of a .pak (a plain zip), decompressed."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            out[n] = z.read(n)
    return out


def pak_write(path: str, members: dict[str, bytes]) -> None:
    """Write a .pak with NO extra fields.

    zipfile copies ZipInfo.extra into the local header as well, and the engine
    then fails to read the member. Fresh ZipInfo objects only.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)             # no extra, no timestamps
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            z.writestr(zi, data)


def pak_validate(path: str) -> int:
    """Inflate every member; raise if any fails. Returns the member count."""
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            die(f"corrupt member in {path}: {bad}")
        return len(z.namelist())


# ----------------------------------------------------------- mod inspection

def find_paks(src: str, workdir: str) -> tuple[str, str]:
    """Accept a mod.io .zip or an already-extracted folder; return (main, pc)."""
    if os.path.isfile(src) and src.lower().endswith(".zip"):
        ex = os.path.join(workdir, "_download")
        shutil.rmtree(ex, ignore_errors=True)
        os.makedirs(ex, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(ex)
        src = ex
    paks = []
    for base, _d, files in os.walk(src):
        for f in files:
            if f.lower().endswith(".pak"):
                paks.append(os.path.join(base, f))
    if not paks:
        die(f"no .pak found under {src}")
    pc = next((p for p in paks if os.path.basename(p).lower() in ("pc.pak",)
               or "_pc" in os.path.basename(p).lower()), None)
    main = next((p for p in paks if p != pc), None)
    if not pc or not main:
        die(f"expected a main pak and a pc pak, found: {[os.path.basename(p) for p in paks]}")
    return main, pc


def mesh_xmls(main_pak: str) -> dict[str, str]:
    """The XML header embedded in each compiled mesh: [u32 len][xml][geometry]."""
    out = {}
    for name, data in pak_entries(main_pak).items():
        if not name.startswith("prebuild/meshes/") or len(data) < 8:
            continue
        n = struct.unpack_from("<I", data, 0)[0]
        if 0 < n < len(data):
            out[name] = data[4:4 + n].decode("utf-8", "replace")
    return out


def required_textures(main_pak: str) -> tuple[set[str], list[tuple[str, str]]]:
    """Texture maps every material asks for, and (mesh, material) pairs whose
    name is absent from that mesh's own geometry (the author's own defect)."""
    maps: set[str] = set()
    missing: list[tuple[str, str]] = []
    ents = pak_entries(main_pak)
    for name, xml in mesh_xmls(main_pak).items():
        for m in re.finditer(r'(?:Albedo|Normal|Shading|Emissive|Tint)Map="([^"]+)"', xml):
            maps.add(m.group(1))
        blob = ents[name]
        n = struct.unpack_from("<I", blob, 0)[0]
        geo = blob[4 + n:]
        for m in re.finditer(r'<Material\b[^>]*?\bName="([^"]+)"', xml, re.S):
            if m.group(1).encode() not in geo:
                missing.append((os.path.basename(name), m.group(1)))
    return maps, missing


# ------------------------------------------------------------- TGA authoring

def write_tga(path: str, rgb, alpha=None, size=DEFAULT_SIZE) -> None:
    """A flat colour square, written by the ONE verified writer.

    Row order is a no-op for a flat colour, but this used to be a fourth private
    copy of the TGA format. Copies are how a fix lands in one of them and the
    other three keep shipping the bug.
    """
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from vehicle_pak import write_tga as _write
    if alpha is None:
        img = Image.new("RGB", (size, size), tuple(rgb))
    else:
        img = Image.new("RGBA", (size, size), (rgb[0], rgb[1], rgb[2], alpha))
    _write(path, img, alpha_from_image=alpha is not None)


def material_of(tex: str) -> str:
    """trucks/carroceria__d_a.tga -> carroceria"""
    base = os.path.basename(tex)
    base = re.sub(r"\.(tga|png|dds)$", "", base, flags=re.I)
    return re.split(r"__", base)[0]


def kind_of(tex: str) -> str:
    m = re.search(r"__(d_a|d|n_d|sh_d|em_d)(?:\.\w+)?$", tex)
    return m.group(1) if m else "d"


def make_skin(maps: set[str], out_dir: str, palette: dict, donor: str | None) -> dict:
    """Write a .tga for every required map. Real files from `donor` win."""
    tdir = os.path.join(out_dir, "textures", "trucks")
    os.makedirs(tdir, exist_ok=True)
    donor_files = {}
    if donor and os.path.isdir(donor):
        for f in os.listdir(donor):
            if f.lower().endswith(".tga"):
                donor_files[f.lower()] = os.path.join(donor, f)

    stats = {"reused": 0, "authored": 0, "unknown": []}
    for tex in sorted(maps):
        fn = os.path.basename(tex)
        if not fn.lower().endswith(".tga"):
            fn += ".tga"
        dst = os.path.join(tdir, fn)
        if fn.lower() in donor_files:                     # a genuine texture
            shutil.copyfile(donor_files[fn.lower()], dst)
            stats["reused"] += 1
            continue
        mat, kind = material_of(fn), kind_of(fn)
        if kind == "n_d":
            write_tga(dst, FLAT_NORMAL)
        elif kind == "sh_d":
            write_tga(dst, FLAT_SHADING)
        elif kind == "em_d":
            write_tga(dst, [0, 0, 0])
        else:
            if mat.endswith("_wt"):                       # paint base for tinting
                rgb = [220, 220, 220]
            elif mat.endswith("_cc"):                     # tint mask, layer 1
                rgb = [255, 0, 0]
            else:
                rgb = palette_lookup(palette, mat)
            if rgb is None:
                rgb = [160, 160, 160]
                stats["unknown"].append(mat)
            a = GLASS_ALPHA if (kind == "d_a" and TRANSLUCENT.search(mat)) else (
                255 if kind == "d_a" else None)
            write_tga(dst, rgb, a)
        stats["authored"] += 1
    stats["unknown"] = sorted(set(stats["unknown"]))
    return stats


# -------------------------------------------------------------- encode .pct

def encode_textures(skin_root: str, out_dir: str, timeout: int = 180) -> tuple[int, list[str]]:
    """TGA -> native .pct using the game's own converter.

    The two traps: `-i` is resolved RELATIVE to `-r` (an absolute path fails with
    'Unable to find texture file' on a file that is plainly there), and `-o` is
    resolved against the working directory, so the output lands beside the exe
    and has to be collected.
    """
    if not RESOURCE_CONVERTER or not os.path.isfile(RESOURCE_CONVERTER):
        die(_GAME_ERROR or
            f"ResourceConverter.exe not found at {RESOURCE_CONVERTER}\n"
            "       set EXPEDITIONS_DIR to your game folder")
    # `-o` is resolved against the WORKING DIRECTORY, so the cwd decides where
    # output lands. Never run this from the game's Bin folder: a half-written
    # `prebuild` directory beside Expeditions.exe stops the game launching, and
    # an interrupted run leaves one behind. Verified the converter works fine
    # with its cwd elsewhere; it finds its own DLLs from the exe's directory.
    run_dir = os.path.abspath(os.path.join(out_dir, os.pardir, "_convscratch"))
    os.makedirs(run_dir, exist_ok=True)
    scratch = os.path.join(run_dir, "prebuild")
    shutil.rmtree(scratch, ignore_errors=True)
    tdir = os.path.join(skin_root, "textures", "trucks")
    tgas = sorted(f for f in os.listdir(tdir) if f.lower().endswith(".tga"))

    failed = []
    try:
        for i, f in enumerate(tgas, 1):
            stem = os.path.splitext(f)[0]
            cmd = [RESOURCE_CONVERTER, "--all-pct", "-s",
                   "-r", skin_root,
                   "-i", f"textures/trucks/{f}",
                   "-o", f"prebuild/textures/pct/trucks_{stem}.pct"]
            try:
                # -s is mandatory: without it an assert opens a modal dialog and waits
                r = subprocess.run(cmd, cwd=run_dir, timeout=timeout,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if r.returncode != 0:
                    failed.append(f"{f} (exit {r.returncode})")
            except subprocess.TimeoutExpired:
                failed.append(f"{f} (timeout)")
            if i % 20 == 0:
                log(f"      {i}/{len(tgas)}")

        made = os.path.join(scratch, "textures", "pct")
        os.makedirs(out_dir, exist_ok=True)
        n = 0
        if os.path.isdir(made):
            for f in os.listdir(made):
                if f.lower().endswith(".pct"):
                    shutil.copyfile(os.path.join(made, f), os.path.join(out_dir, f))
                    n += 1
        return n, failed
    finally:
        shutil.rmtree(scratch, ignore_errors=True)      # never leave it in the game dir


def self_test() -> bool:
    """Re-encode a texture the game itself converted and compare byte-for-byte.

    Only runs when the game's sample mod `tundra_test` is present.
    """
    tt = os.path.join(USER, "Media", "Mods", "tundra_test")
    src = os.path.join(tt, "textures", "trucks", "mod_scout__d.tga")
    native = os.path.join(tt, "prebuild", "textures", "pct", "trucks_mod_scout__d.pct")
    if not (os.path.isfile(src) and os.path.isfile(native)):
        log("   self-test skipped (no tundra_test sample mod on this machine)")
        return True
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        os.makedirs(os.path.join(root, "textures", "trucks"))
        shutil.copyfile(src, os.path.join(root, "textures", "trucks", "mod_scout__d.tga"))
        out = os.path.join(tmp, "out")
        n, failed = encode_textures(root, out)
        mine = os.path.join(out, "trucks_mod_scout__d.pct")
        if not os.path.isfile(mine):
            log("   SELF-TEST FAILED: encoder produced nothing")
            return False
        ok = open(mine, "rb").read() == open(native, "rb").read()
        log(f"   self-test: encoder output {'matches' if ok else 'DIFFERS FROM'} the game's own")
        return ok


# ------------------------------------------------------------------ install

def install(mod_id: str, main_pak: str, pc_pak: str, name: str) -> str:
    dest = os.path.join(MODIO, str(mod_id))
    os.makedirs(dest, exist_ok=True)
    shutil.copyfile(main_pak, os.path.join(dest, os.path.basename(main_pak)))
    shutil.copyfile(pc_pak, os.path.join(dest, "pc.pak"))   # must be literally pc.pak
    meta = {
        "id": int(mod_id), "game_id": 5734, "status": 1, "visible": 1,
        "name": name, "name_id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
        "modfile": {"filename": os.path.basename(main_pak), "version": "1.0",
                    "filesize": os.path.getsize(main_pak)},
        "platforms": [{"platform": "windows", "modfile_live": int(mod_id)}],
        "tags": [], "dependencies": False, "metadata_kvp": [],
    }
    with open(os.path.join(dest, "modio.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    register(mod_id)
    return dest


def register(mod_id: str) -> bool:
    """Add the mod to modStateList in user_profile.dat so the game enables it.

    The file is JSON with a trailing NUL. Edits are length-preserving where
    possible; a backup is written to one fixed name, never a timestamped chain.
    """
    prof = None
    for base, _d, files in os.walk(PROFILE_DIR):
        if "user_profile.dat" in files:
            prof = os.path.join(base, "user_profile.dat")
            break
    if not prof:
        log("   ! user_profile.dat not found; enable the mod in-game instead")
        return False
    raw = open(prof, "rb").read()
    txt = raw.decode("ascii", "replace")
    if f'"modId":{mod_id}' in txt:
        return True
    shutil.copyfile(prof, prof + ".bak")                 # one backup, fixed name
    entry = '{"modId":%s,"modState":true}' % mod_id
    if '"modStateList":[' in txt:
        new = txt.replace('"modStateList":[', '"modStateList":[' + entry + ",", 1)
    else:
        log("   ! no modStateList in profile; enable the mod in-game instead")
        return False
    open(prof, "wb").write(new.encode("ascii", "replace"))
    return True


# --------------------------------------------------------------- subcommands

def load_palette(path: str | None) -> dict:
    pal = dict(DEFAULT_PALETTE)
    if path and os.path.isfile(path):
        pal.update(json.load(open(path, encoding="utf-8")))
    return pal


def palette_lookup(pal: dict, mat: str):
    """Exact name, else the name with trailing digits removed (madera1 -> madera)."""
    if mat in pal:
        return pal[mat]
    return pal.get(re.sub(r"\d+$", "", mat))


def default_donor() -> str | None:
    """The game's own sample mod ships genuine template .tga files. Any texture
    whose name matches one of those is better taken verbatim than invented."""
    d = os.path.join(USER, "Media", "Mods", "tundra_test", "textures", "trucks")
    return d if os.path.isdir(d) else None


def check_ui(main_pak: str) -> list[str]:
    """Store and garage artwork problems that survive a successful texture port.

    Both are invisible until you look at the store: a SnowRunner mod routinely
    ships the sample truck's own picture, and routinely omits the large store
    slot that 43 of the game's 44 stock trucks declare.
    """
    warn = []
    ents = pak_entries(main_pak)
    truck = next((v.decode("utf-8", "replace") for k, v in ents.items()
                  if re.match(r"classes/trucks/[^/]+\.xml$", k)), None)
    if not truck:
        return warn
    ui = re.search(r"<UiDesc[\s\S]*?/>", truck)
    if not ui:
        return warn
    decl = dict(re.findall(r'(\w+)="([^"]*)"', ui.group(0)))
    shipped = {k.split("/")[-1].rsplit(".", 1)[0] for k in ents if k.startswith("ui/")}

    if "UiIcon576x640" not in decl:
        warn.append("no UiIcon576x640: the large store preview will be blank "
                    "(43 of 44 stock trucks declare it)")
    for field in ("UiIcon328x458", "UiIcon576x640", "UiIconLogo"):
        val = decl.get(field)
        if val and val not in shipped:
            warn.append(f"{field}=\"{val}\" is not shipped in this mod's ui/ folder")
        if val and re.search(r"modscout|sample", val, re.I):
            warn.append(f"{field}=\"{val}\" is the SAMPLE TRUCK's artwork -- the garage "
                        "list will show the wrong vehicle")
    return warn


def cmd_analyze(a) -> int:
    main, pc = find_paks(a.mod, a.work)
    maps, missing = required_textures(main)
    log(f"main pak : {os.path.basename(main)}")
    log(f"pc pak   : {os.path.basename(pc)}")
    log(f"meshes   : {len(mesh_xmls(main))}")
    log(f"textures required: {len(maps)}")
    mats = sorted({material_of(m) for m in maps})
    pal = load_palette(a.palette)
    donor = a.donor or default_donor()
    have = set()
    if donor and os.path.isdir(donor):
        have = {f.lower() for f in os.listdir(donor) if f.lower().endswith(".tga")}
    covered, unknown = [], []
    for m in mats:
        if m.endswith(("_wt", "_cc")) or palette_lookup(pal, m) is not None:
            covered.append(m)
        elif any(f.startswith(m.lower() + "__") for f in have):
            covered.append(m)                    # a real donor texture exists
        else:
            unknown.append(m)
    log(f"materials: {len(mats)}")
    log(f"  donor           : {donor or '(none)'}")
    log(f"  covered         : {len(covered)}")
    log(f"  NO colour/donor : {len(unknown)}  {' '.join(unknown[:12])}")
    if unknown:
        log("  -> add these to palette.json, or they get mid-grey")
    if missing:
        log(f"\n{len(missing)} material(s) declared in XML but absent from their mesh geometry.")
        log("  These are the mod author's own defect and are cosmetic -- they are NOT")
        log("  why a truck is black. Do not chase them.")
        for mesh, mat in missing[:10]:
            log(f"    {mat}  in {mesh}")

    ui = check_ui(main)
    log(f"\nstore / garage artwork: {len(ui)} problem(s)")
    for w in ui:
        log(f"  ! {w}")
    if not ui:
        log("  looks fine")
    return 0


def cmd_port(a) -> int:
    os.makedirs(a.work, exist_ok=True)
    log("1/6  reading the mod")
    main, pc = find_paks(a.mod, a.work)
    maps, missing = required_textures(main)
    log(f"     {len(maps)} textures required by {len(mesh_xmls(main))} meshes")

    if not a.skip_self_test:
        log("2/6  verifying the encoder against the game's own output")
        if not self_test():
            die("encoder self-test failed; stopping before touching anything")
    else:
        log("2/6  self-test skipped")

    log("3/6  writing source textures")
    skin = os.path.join(a.work, "_skin_src")
    shutil.rmtree(skin, ignore_errors=True)
    donor = a.donor or default_donor()
    st = make_skin(maps, skin, load_palette(a.palette), donor)
    log(f"     authored {st['authored']}, reused {st['reused']} real texture(s)"
        + (f" from {donor}" if st["reused"] else ""))
    if st["unknown"]:
        log(f"     ! no palette colour for: {' '.join(st['unknown'][:12])} (used mid-grey)")

    log("4/6  encoding to native .pct (this is the slow part)")
    pcts = os.path.join(a.work, "_new_pct")
    shutil.rmtree(pcts, ignore_errors=True)
    n, failed = encode_textures(skin, pcts)
    log(f"     produced {n} .pct, {len(failed)} failure(s)")
    for f in failed[:8]:
        log(f"       {f}")
    if n == 0:
        die("no textures were encoded; nothing to install")

    log("5/6  rebuilding pc.pak")
    members = pak_entries(pc)
    replaced = added = 0
    for f in sorted(os.listdir(pcts)):
        if not f.lower().endswith(".pct"):
            continue
        key = f"prebuild/textures/pct/{f}"
        if key in members:
            replaced += 1
        else:
            added += 1
        members[key] = open(os.path.join(pcts, f), "rb").read()
    out_pak = os.path.join(a.work, "_built", "pc.pak")
    pak_write(out_pak, members)
    count = pak_validate(out_pak)
    log(f"     replaced {replaced}, added {added}, {count} entries, all validated")

    if a.no_install:
        log(f"6/6  built, not installed: {out_pak}")
        return 0
    log("6/6  installing")
    dest = install(a.id, main, out_pak, a.name or "Ported vehicle")
    log(f"     {dest}")
    log("\nDone. Launch the game and look at the truck.")
    log("If it is black, read the guide's vehicle-porting troubleshooting section.")
    return 0


def cmd_full(a) -> int:
    """Textures, then artwork, then skins. The whole port in one run.

    Kept as three steps internally because each is independently useful and
    independently verifiable: the texture pass self-tests the encoder, the
    artwork pass needs a screenshot you may want to retake, and the skin pass
    checks mesh integrity before it writes anything.
    """
    import subprocess as sp
    here = os.path.dirname(os.path.abspath(__file__))

    a.no_install = True            # install at the end, after artwork and skins
    a.donor = getattr(a, "donor", None)
    if cmd_port(a) != 0:
        return 1
    current = os.path.join(a.work, "_built", "pc.pak")
    main_pak, _ = find_paks(a.mod, a.work)
    staged = os.path.join(a.work, "_built", os.path.basename(main_pak))
    shutil.copyfile(main_pak, staged)

    if a.shot:
        if not a.box:
            die("--shot needs --box: the box around the vehicle in that screenshot")
        log("\n7/8  store and garage artwork")
        out = staged.replace(".pak", "_ui.pak")
        cmd = [sys.executable, os.path.join(here, "vehicle_ui.py"), staged, out,
               "--shot", a.shot, "--name", a.name.replace(" ", ""),
               "--box", *map(str, a.box)]
        if a.safe:
            cmd += ["--safe", *map(str, a.safe)]
        if a.badge:
            cmd += ["--badge", a.badge]
        if sp.run(cmd).returncode != 0:
            return 1
        staged = out

    if a.camo:
        log("\n8/8  skins")
        # the skin pass references trucks/<body>_<name>__d.tga for each camo, and
        # the texture pass above never generates those -- they come from
        # camo_from_source.py. Refuse rather than ship a mod whose overrides
        # point at textures that are not in the pak.
        missing = [c for c in a.camo
                   if not os.path.exists(os.path.join(
                       a.work, "_new_pct", f"trucks_{a.body}_{c}__d.pct"))]
        if missing:
            die(f"--camo {' '.join(missing)}: no encoded texture for these.\n"
                f"       build them first:\n"
                f"         python camo_from_source.py <swatch> "
                f"<work>/_skin_src/textures/trucks/{a.body}_{missing[0]}__d.tga --tile 2\n"
                f"       then re-run, or drop --camo")
        out = staged.replace(".pak", "_skins.pak")
        cmd = [sys.executable, os.path.join(here, "vehicle_skins.py"), staged, out,
               "--body", a.body, "--camo", *a.camo]
        if sp.run(cmd).returncode != 0:
            return 1
        staged = out

    if a.no_install_final:
        log(f"\nbuilt, NOT installed:\n   {staged}\n   {current}")
        return 0
    dest = install(a.id, staged, current, a.name)
    log(f"\ninstalled to {dest}")
    log("Launch the game. If it was running, restart it: the old paks are loaded.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("mod", help="mod.io .zip, or a folder containing the .pak files")
        p.add_argument("--work", default=os.path.join(os.getcwd(), "_port"),
                       help="scratch directory (default ./_port)")
        p.add_argument("--palette", help="JSON of {material: [r,g,b]} overrides")
        p.add_argument("--donor", help="folder of real .tga files to use where names "
                                       "match (defaults to the game's tundra_test sample)")

    pa = sub.add_parser("analyze", help="report textures, materials and author defects")
    common(pa)
    pa.set_defaults(func=cmd_analyze)

    pf = sub.add_parser("full", help="port, then artwork and skins, in one run")
    common(pf)
    pf.add_argument("--id", required=True)
    pf.add_argument("--name", required=True, help="display name, also the image basename")
    pf.add_argument("--shot", help="screenshot for the store/garage artwork")
    pf.add_argument("--box", type=int, nargs=4, metavar=("L", "T", "R", "B"))
    pf.add_argument("--safe", type=int, nargs=4, metavar=("L", "T", "R", "B"))
    pf.add_argument("--badge")
    pf.add_argument("--body", default="carroceria")
    pf.add_argument("--camo", nargs="*", default=[])
    pf.add_argument("--skip-self-test", action="store_true")
    pf.add_argument("--no-install", dest="no_install_final", action="store_true",
                    help="build and verify, but do not touch the mods folder")
    pf.set_defaults(func=cmd_full)

    pp = sub.add_parser("port", help="full port: skin, encode, repack, install")
    common(pp)
    pp.add_argument("--id", required=True, help="mod id to install under")
    pp.add_argument("--name", help="display name for modio.json")
    pp.add_argument("--no-install", action="store_true", help="build only")
    pp.add_argument("--skip-self-test", action="store_true")
    pp.set_defaults(func=cmd_port)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
