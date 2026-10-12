#!/usr/bin/env python3
"""Give a ported vehicle its engine sound back.

THE BUG THIS EXISTS FOR
-----------------------
A port carries SnowRunner's truck XML across unchanged, so its ``Sound=``
references still name SnowRunner banks -- ``trucks/jeep_cj7/...``,
``trucks/tuz_166/...``. Expeditions has 40 truck banks and NONE of those is
among them, so every reference resolves to nothing and the vehicle is silent.
Nothing errors. The XML is perfectly well formed and points at empty space.

Measured 2026-10-11: the Jeeps and the Tundra shipped no audio at all. The
Bronco works only because it ships its own ``sounds/engine/Bronco_V8_*.wav``
inside its ``pc.pak``.

THE PATTERN THAT WORKS, 4 OF 4 MODS THAT HAVE SOUND
---------------------------------------------------
Ship ``.wav`` under ``sounds/<folder>/`` in the mod's **pc.pak** and reference
it as ``Sound="<folder>/<name>"``. Goliath uses ``sounds/mack/``, FJ Bruiser
``sounds/engine_NASCAR_V8/``, RosenRot's Buggy ``sounds/ls/``, the Bronco
``sounds/engine/``.

⛔ Do NOT drop raw files into the engine's own ``[sound]/`` namespace. That
system is driven by ``sound.sound_list``, which is a bare length-prefixed list
of paths (``<len:u64><path>``) with no format data. A file that is not in that
index does not exist as far as the game is concerned, and a mod cannot add to
it. That is precisely why every working mod takes the wav route.

FORMATS, MEASURED -- NOT GUESSED
--------------------------------
SnowRunner's ``.pcm`` files are **not raw PCM despite the extension**. They are
RIFF/WAVE containers holding **MS ADPCM** (format tag 2), mono, 4-bit, ~44100 Hz.
Reading one as linear int16 yields a lag-1 correlation of about -0.03, which is
noise; real audio sits near +0.9. Check the header before running statistics on
a payload.

The target is whatever the game is already proven to accept from a mod, which is
the Bronco's: **PCM (tag 1), mono, 48000 Hz, 16-bit**.
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

import game_paths as gp
import vehicle_pak as vp

SOUND_REF = re.compile(r'Sound\s*=\s*"([^"]+)"')
BANK_MEMBER = re.compile(r"\[sound\]/trucks/([^/]+)/(.+)\.pcm$", re.I)

TARGET_RATE = 48000          # the Bronco's, and the only format proven accepted
TARGET_BITS = 16
FFMPEG_TIMEOUT = 120


# --------------------------------------------------------------- the games

def _banks_in(root: str) -> dict[str, dict[str, str]]:
    """``{bank: {stem: "pak!member"}}`` for every ``[sound]/trucks`` bank."""
    out: dict[str, dict[str, str]] = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".pak"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                z = zipfile.ZipFile(path)
            except Exception:
                continue
            for member in z.namelist():
                m = BANK_MEMBER.match(member)
                if m:
                    out.setdefault(m.group(1), {})[m.group(2)] = f"{path}!{member}"
    return out


def expeditions_banks() -> set[str]:
    return set(_banks_in(gp.expeditions_dir()))


def snowrunner_banks() -> dict[str, dict[str, str]]:
    return _banks_in(gp.snowrunner_dir())


# ------------------------------------------------------------------ audit

def sound_refs(members: dict[str, bytes]) -> dict[str, list[str]]:
    """``{class member: [sound refs]}`` for every truck/engine class in a pak."""
    out = {}
    for name, blob in members.items():
        if not (name.startswith("classes/") and name.endswith(".xml")):
            continue
        refs = sorted({r for r in SOUND_REF.findall(blob.decode("utf-8", "replace")) if r})
        if refs:
            out[name] = refs
    return out


def sound_index(root: str) -> set[str]:
    """Every sound path a game provides, as the stem the XML would reference.

    ``[sound]/trucks/common/truck_awd_rnd_set/truck_awd_rnd__3.pcm`` is reachable
    as ``trucks/common/truck_awd_rnd_set/truck_awd_rnd`` -- the ``__N`` suffix is
    a random-set variant, not part of the reference.
    """
    out: set[str] = set()
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".pak"):
                continue
            try:
                z = zipfile.ZipFile(os.path.join(dirpath, fn))
            except Exception:
                continue
            for member in z.namelist():
                if not member.lower().startswith("[sound]/"):
                    continue
                stem = member[len("[sound]/"):]
                if stem.lower().endswith(".pcm"):
                    stem = stem[:-4]
                out.add(stem)
                out.add(re.sub(r"__\d+$", "", stem))
    return out


def classify(refs: list[str], index: set[str], shipped: set[str]) -> dict[str, str]:
    """Each ref -> 'shipped' | 'in-game' | 'MISSING'.

    ⛔ An earlier version guessed from folder prefixes and reported 14 refs of
    the WORKING Bronco as missing, including `trucks/common/truck_awd_rnd_set`
    which the game plainly ships. Calibrate against the Bronco: if it reports a
    missing bank for a vehicle that is audibly fine, the classifier is wrong,
    not the vehicle.
    """
    verdict = {}
    for ref in refs:
        folder = ref.rsplit("/", 1)[0] if "/" in ref else ref
        top = folder.split("/", 1)[0]
        if folder in shipped or top in shipped:
            verdict[ref] = "shipped"
        elif ref in index:
            verdict[ref] = "in-game"
        else:
            verdict[ref] = "MISSING"
    return verdict


def shipped_folders(pc_members: dict[str, bytes]) -> set[str]:
    out = set()
    for n in pc_members:
        m = re.match(r"sounds/([^/]+)/", n)
        if m:
            out.add(m.group(1))
    return out


# -------------------------------------------------------------- conversion

def adpcm_to_wav(data: bytes) -> bytes:
    """MS ADPCM -> PCM s16le mono at TARGET_RATE, through ffmpeg.

    shell=False so the timeout actually bounds wall clock.
    """
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.wav")
        dst = os.path.join(td, "out.wav")
        with open(src, "wb") as f:
            f.write(data)
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
               "-ac", "1", "-ar", str(TARGET_RATE),
               "-c:a", f"pcm_s{TARGET_BITS}le", dst]
        r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT)
        if r.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError(f"ffmpeg failed: {r.stderr.decode('utf-8', 'replace')[:300]}")
        with open(dst, "rb") as f:
            return f.read()


def wav_format(data: bytes) -> tuple[int, int, int, int]:
    """``(format_tag, channels, rate, bits)`` from a RIFF/WAVE header."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    i = 12
    while i < len(data) - 8:
        cid = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        if cid == b"fmt ":
            tag, ch, rate, _byr, _align, bits = struct.unpack("<HHIIHH", data[i + 8:i + 24])
            return tag, ch, rate, bits
        i += 8 + size + (size & 1)
    raise ValueError("no fmt chunk")


def read_member(locator: str) -> bytes:
    path, member = locator.split("!", 1)
    with zipfile.ZipFile(path) as z:
        return z.read(member)


# ------------------------------------------------------------------- repair

def mod_paks(mod_dir: str) -> tuple[str, str]:
    """``(main pak, pc.pak)`` for an installed mod folder."""
    pc = os.path.join(mod_dir, "pc.pak")
    mains = [os.path.join(mod_dir, f) for f in sorted(os.listdir(mod_dir))
             if f.lower().endswith(".pak") and f.lower() != "pc.pak"]
    if not mains:
        raise SystemExit(f"no main .pak in {mod_dir}")
    return mains[0], pc


def repair(mod_dir: str, apply: bool = False) -> int:
    main_path, pc_path = mod_paks(mod_dir)
    main = vp.read_pak(main_path)
    pc = vp.read_pak(pc_path) if os.path.exists(pc_path) else {}

    index = sound_index(gp.expeditions_dir())
    shipped = shipped_folders(pc)
    refs_by_class = sound_refs(main)

    missing: dict[str, set[str]] = {}
    for cls, refs in refs_by_class.items():
        for ref, verdict in classify(refs, index, shipped).items():
            if verdict == "MISSING" and ref.startswith("trucks/"):
                bank = ref.split("/", 2)[1]
                missing.setdefault(bank, set()).add(ref)

    if not missing:
        print(f"   {os.path.basename(mod_dir)}: no missing sound banks")
        return 0

    sr = snowrunner_banks()
    print(f"   {os.path.basename(mod_dir)}: {len(missing)} missing bank(s)")
    new_pc = dict(pc)
    converted = 0
    for bank, refs in sorted(missing.items()):
        if bank not in sr:
            print(f"      {bank:<18} ** NOT IN SNOWRUNNER EITHER -- cannot repair **")
            continue
        # Only the files the XML actually asks for, plus their __N random-set
        # variants. Converting a whole bank put 171 `common` files into a pak
        # to satisfy a single reference.
        wanted = {r.split("/", 2)[2] for r in refs}
        files = {stem: loc for stem, loc in sr[bank].items()
                 if re.sub(r"__\d+$", "", stem) in wanted}
        print(f"      {bank:<18} {len(refs)} ref(s) -> {len(files)} of "
              f"{len(sr[bank])} source file(s)")
        for stem, locator in sorted(files.items()):
            raw = read_member(locator)
            tag, ch, rate, bits = wav_format(raw)
            if not apply:
                continue
            wav = adpcm_to_wav(raw)
            new_pc[f"sounds/{bank}/{stem}.wav"] = wav
            converted += 1
        if apply:
            print(f"         converted {len(files)} file(s) "
                  f"(src tag={tag} {rate}Hz {bits}b -> PCM {TARGET_RATE}Hz {TARGET_BITS}b)")

    if not apply:
        print("      (dry run; pass --apply to convert and write)")
        return 0

    # rewrite the references: trucks/<bank>/<x> -> <bank>/<x>
    new_main = dict(main)
    edits = 0
    for cls in refs_by_class:
        text = new_main[cls].decode("utf-8", "replace")
        before = text
        for bank in missing:
            text = text.replace(f'"trucks/{bank}/', f'"{bank}/')
        if text != before:
            new_main[cls] = text.encode("utf-8")
            edits += 1

    vp.write_pak(pc_path, new_pc)
    vp.validate_pak(pc_path)
    vp.write_pak(main_path, new_main)
    vp.validate_pak(main_path)
    print(f"      wrote {converted} wav(s) into {os.path.basename(pc_path)}; "
          f"repointed {edits} class file(s)")
    return converted


def audit(mod_dir: str) -> None:
    main_path, pc_path = mod_paks(mod_dir)
    main = vp.read_pak(main_path)
    pc = vp.read_pak(pc_path) if os.path.exists(pc_path) else {}
    index = sound_index(gp.expeditions_dir())
    shipped = shipped_folders(pc)
    print(f"=== {os.path.basename(mod_dir)} ({os.path.basename(main_path)}) ===")
    if shipped:
        print(f"    ships its own audio under sounds/: {', '.join(sorted(shipped))}")
    total = {"shipped": 0, "in-game": 0, "MISSING": 0}
    bad = set()
    for cls, refs in sorted(sound_refs(main).items()):
        verdicts = classify(refs, index, shipped)
        for ref, v in verdicts.items():
            total[v] += 1
            if v == "MISSING":
                bad.add(ref.rsplit("/", 1)[0])
    print("    refs: %d shipped, %d in-game, %d MISSING" %
          (total["shipped"], total["in-game"], total["MISSING"]))
    for folder in sorted(bad):
        print(f"      MISSING folder: {folder}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mod_dir", nargs="+", help="installed mod folder(s)")
    ap.add_argument("--apply", action="store_true",
                    help="convert and write. Without it, nothing is modified.")
    a = ap.parse_args(argv)
    for d in a.mod_dir:
        if a.apply:
            repair(d, apply=True)
        else:
            audit(d)
            repair(d, apply=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
