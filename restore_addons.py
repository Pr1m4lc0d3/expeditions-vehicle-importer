#!/usr/bin/env python3
"""Give a ported truck back the stock accessories it was built with.

A SnowRunner truck carries bumpers, thresholds and a spare wheel that are not
part of the body mesh. Each is a separate addon class, installed because the
truck's `<AddonSockets>` element names it in `DefaultAddon`. Two things then go
wrong in a port, and both are silent -- the truck spawns, drives and looks
almost right:

  * The mod names a `DefaultAddon` whose class lives in the DONOR game, not in
    the mod. Port the mod without that class and the socket resolves to nothing.
    This is the one a port creates: excluding the donor's classes is also what
    stops its truck definitions shadowing the mod's, so it is easy to exclude
    too much.

  * The mod's own class DROPPED a `DefaultAddon` the donor declares. Nothing is
    missing from the pak at all; the socket is simply empty. Indistinguishable
    from the first case in game.

The pairing between a mod's truck class and the donor's is done on SOCKET NAMES,
not filenames: a mod renames `jeep_cj7_renegade.xml` to `JTTs_jeep_renegade.xml`
but cannot rename `CJ7FrontBumper` without breaking its own meshes.

    python restore_addons.py analyze <main.pak> [--pc <pc.pak>]
    python restore_addons.py fix     <main.pak> <out.pak> [--pc <pc.pak>]

`analyze` changes nothing. `fix` ships the missing classes and restores the
dropped defaults, and refuses to enable an addon whose mesh is not in the pak.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vehicle_pak import is_mesh, read_pak, split_mesh, validate_pak, write_pak

from game_paths import GameNotFound, snowrunner_initial_pak  # noqa: E402


def default_donor() -> str:
    """SnowRunner's class library. Resolved late: a machine without
    SnowRunner can still analyse a pak, and --donor overrides anyway."""
    try:
        return snowrunner_initial_pak()
    except GameNotFound:
        return ""


DONOR = default_donor()

SOCKETS = re.compile(r"<AddonSockets\b([^>]*)>([\s\S]*?)</AddonSockets>")
SELFCLOSE = re.compile(r"<AddonSockets\b([^>]*?)/>")


def sockets(xml: str) -> list[tuple[str | None, tuple[str, ...], int, int]]:
    """(DefaultAddon, socket names, start, end) for each AddonSockets element."""
    out = []
    for m in SOCKETS.finditer(xml):
        attrs, body = m.group(1), m.group(2)
        d = re.search(r'DefaultAddon="([^"]+)"', attrs)
        names = tuple(sorted({n for a in re.findall(r'\bNames="([^"]+)"', body)
                              for n in re.split(r"[,\s]+", a) if n}))
        if d or names:
            out.append((d.group(1) if d else None, names, m.start(), m.end()))
    return out


def socket_key(names: tuple[str, ...]) -> frozenset:
    """Socket names ignoring a mod's own prefix, so jtt_X and X pair up."""
    return frozenset(re.sub(r"^(jtt_|jtts_)", "", n, flags=re.I).lower() for n in names)


def truck_classes(members: dict[str, bytes]) -> dict[str, str]:
    return {k: members[k].decode("utf-8", "replace")
            for k in members
            if re.match(r"(\[media\]/)?.*classes/trucks/[^/]+\.xml$", k)}


def pair_trucks(mod_x: str, donor: dict[str, str]) -> tuple[str | None, float]:
    """Best donor class for this mod class, scored on shared socket names."""
    mine = {socket_key(n) for _, n, _, _ in sockets(mod_x) if n}
    if not mine:
        return None, 0.0
    best, score = None, 0.0
    for k, x in donor.items():
        theirs = {socket_key(n) for _, n, _, _ in sockets(x) if n}
        if not theirs:
            continue
        j = len(mine & theirs) / len(mine | theirs)
        if j > score:
            best, score = k, j
    return best, score


def mesh_present(members: dict[str, bytes], mesh: str) -> bool:
    """Pak keys flatten the mesh path: trucks/a/b -> prebuild/meshes/trucks_a_b."""
    flat = mesh.replace("/", "_").lower()
    return any(k[len("prebuild/meshes/"):].lower() == flat
               for k in members if is_mesh(k))


def addon_mesh(xml: str) -> str | None:
    m = re.search(r'<PhysicsModel[^>]*\bMesh="([^"]+)"', xml)
    return m.group(1) if m else None


def missing_pct(members: dict[str, bytes], pc: dict[str, bytes], mesh: str) -> list[str]:
    """Textures this addon's mesh asks for that have no encoded .pct."""
    flat = mesh.replace("/", "_").lower()
    key = next((k for k in members
                if is_mesh(k) and k[len("prebuild/meshes/"):].lower() == flat), None)
    if not key or not pc:
        return []
    mx = split_mesh(members[key])[0]
    have = {k.rsplit("/", 1)[-1].lower() for k in pc if k.lower().endswith(".pct")}
    out = []
    for t in sorted(set(re.findall(
            r'(?:AlbedoMap|TintMap|ShadingMap|NormalMap)="([^"]+)"', mx))):
        base = t.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        if f"trucks_{base}.pct" not in have and f"{base}.pct" not in have:
            out.append(t)
    return out


def survey(members, pc, donor_zip):
    """Everything wrong with this pak's addons, as data."""
    donor = {n: donor_zip.read(n).decode("utf-8", "replace")
             for n in donor_zip.namelist()
             if re.search(r"classes/trucks/[^/]+\.xml$", n)}
    shipped = {k.rsplit("/", 1)[-1][:-4] for k in members if k.endswith(".xml")}
    report = []
    for key, mx in sorted(truck_classes(members).items()):
        dkey, score = pair_trucks(mx, donor)
        entry = {"truck": key, "donor": dkey, "score": score, "items": []}
        # A weak pairing means the donor cannot tell us which defaults were
        # DROPPED. It says nothing about whether a DECLARED default's class is
        # shipped -- that check needs no donor at all. Keeping them separate
        # stops an unpaired truck being reported as fully checked, which is the
        # worse failure: it reads as a clean bill of health.
        entry["paired"] = paired = bool(dkey) and score >= 0.4
        theirs = ({socket_key(n): d for d, n, _, _ in sockets(donor[dkey]) if n}
                  if paired else {})
        for d, names, s, e in sockets(mx):
            if not names:
                continue
            if d:                                   # declared -- is the class here?
                if d not in shipped:
                    entry["items"].append(("missing-class", d, names, s, e))
            elif theirs.get(socket_key(names)):      # dropped a default the donor has
                entry["items"].append(
                    ("dropped-default", theirs[socket_key(names)], names, s, e))
        report.append(entry)
    return report, donor


def describe(report, members, pc, donor_zip):
    n = 0
    for e in report:
        print(f"\n=== {e['truck']}")
        if e["paired"]:
            print(f"    donor {e['donor']}  (socket overlap {e['score']:.0%})")
        else:
            best = f"best was {e['donor']} at {e['score']:.0%}" if e["donor"] else "none"
            print(f"    NO CONFIDENT DONOR ({best}) -- dropped defaults NOT checked;"
                  " only declared ones were verified")
        if not e["items"]:
            print("    every declared default resolves"
                  + ("; nothing to do" if e["paired"] else ""))
            continue
        for kind, addon, names, _, _ in e["items"]:
            cand = [x for x in donor_zip.namelist() if x.endswith(f"/{addon}.xml")]
            mesh = addon_mesh(donor_zip.read(cand[0]).decode("utf-8", "replace")) if cand else None
            bits = [f"socket {', '.join(names)[:46]}"]
            if mesh:
                ok = mesh_present(members, mesh)
                bits.append("mesh in pak" if ok else "MESH ABSENT")
                if ok:
                    miss = missing_pct(members, pc, mesh)
                    if miss:
                        bits.append(f"{len(miss)} texture(s) unencoded")
            elif cand:
                bits.append("no mesh (logic only)")
            else:
                bits.append("NO DONOR CLASS")
            print(f"      {kind:<16} {addon:<42} {' | '.join(bits)}")
            n += 1
    return n


MESHLESS = re.compile(r'<PhysicsModel[^>]*_template="Invisible"')


def synthesize(addon: str, socket: tuple[str, ...], donor_zip):
    """Build a missing addon class from the donor's own template for its kind.

    Some mods name a `DefaultAddon` that was never shipped by anyone -- the
    Tundra asks for `mod_scout_diff_lock_default`, which exists in neither game.
    These are per-truck copies of one boilerplate whose only truck-specific line
    is `InstallSocket Type`, so the class can be rebuilt exactly.

    Restricted to addons with NO MESH, verified by the donor template declaring
    `PhysicsModel _template="Invisible"`. Cloning a mesh-bearing addon between
    trucks would bolt the wrong geometry on, so that case is refused outright.
    """
    # The truck prefix is not separable by rule -- "mod_scout" and "jeep_cj7"
    # are both two tokens, "burlak_6x6" is two, "afim_hornet" is two, and some
    # are one. So try every tail from longest to shortest and take the first
    # that a donor class actually ends with; that finds "_diff_lock_default"
    # without having to know where the truck name stops.
    parts = addon.split("_")
    tried = []
    for i in range(1, len(parts)):
        suffix = "_" + "_".join(parts[i:])
        tried.append(suffix)
        cands = [n for n in donor_zip.namelist() if n.endswith(f"{suffix}.xml")]
        for c in cands:
            x = donor_zip.read(c).decode("utf-8", "replace")
            if not MESHLESS.search(x):
                continue
            if not re.search(r'<InstallSocket\s+Type="[^"]+"\s*/>', x):
                continue
            return re.sub(r'(<InstallSocket\s+Type=")[^"]+(")',
                          rf"\g<1>{socket[0]}\g<2>", x), c
    return None, f"no mesh-less donor template matched any of {', '.join(tried)}"


def apply(report, members, donor_zip, allow_synth: bool = False) -> list[str]:
    notes = []
    for e in report:
        if not e["items"]:
            continue
        key = e["truck"]
        xml = members[key].decode("utf-8", "replace")
        # existing tuning folder for this truck, so new classes land beside its own
        stem = key.rsplit("/", 1)[-1][:-4]
        folders = sorted({k.rsplit("/", 1)[0] for k in members
                          if k.startswith(f"classes/trucks/{stem}_tuning/")})
        tundir = folders[0] if folders else f"classes/trucks/{stem}_tuning"

        # edit from the end so earlier offsets stay valid
        for kind, addon, names, s, epos in sorted(e["items"], key=lambda i: -i[3]):
            cand = [x for x in donor_zip.namelist() if x.endswith(f"/{addon}.xml")]
            if cand:
                cls = donor_zip.read(cand[0]).decode("utf-8", "replace")
            elif allow_synth:
                cls, src = synthesize(addon, names, donor_zip)
                if not cls:
                    notes.append(f"  SKIP {addon}: {src}")
                    continue
                notes.append(f"  ~ synthesized {addon} from {src.rsplit('/', 1)[-1]}")
            else:
                notes.append(f"  SKIP {addon}: no donor class (--synthesize to rebuild it)")
                continue
            mesh = addon_mesh(cls)
            if mesh and not mesh_present(members, mesh):
                notes.append(f"  SKIP {addon}: mesh {mesh} not in pak")
                continue
            ck = f"{tundir}/{addon}.xml"
            if ck not in members:
                members[ck] = cls.encode("utf-8")
                notes.append(f"  + class {ck}")
            if kind == "dropped-default":
                head = xml[s:epos]
                m = re.match(r"<AddonSockets\b([^>]*)>", head)
                new = f'<AddonSockets DefaultAddon="{addon}"{m.group(1)}>'
                xml = xml[:s] + new + xml[s + m.end():]
                notes.append(f"  + DefaultAddon={addon} on socket {', '.join(names)[:40]}")
        members[key] = xml.encode("utf-8")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("analyze")
    a1.add_argument("pak")
    a2 = sub.add_parser("fix")
    a2.add_argument("pak")
    a2.add_argument("out")
    for p in (a1, a2):
        p.add_argument("--pc", help="pc.pak, to check textures are encoded")
        p.add_argument("--donor", default=DONOR)
    a2.add_argument("--synthesize", action="store_true",
                    help="rebuild an addon class nobody ships, from the donor's "
                         "template for its kind. Mesh-less addons only.")
    a = ap.parse_args()

    if not os.path.isfile(a.donor):
        raise SystemExit(f"donor pak not found: {a.donor}")
    members = read_pak(a.pak)
    pc = read_pak(a.pc) if a.pc else {}
    z = zipfile.ZipFile(a.donor)
    try:
        report, _ = survey(members, pc, z)
        n = describe(report, members, pc, z)
        print(f"\n{n} socket(s) need attention")
        if a.cmd == "fix":
            if not n:
                print("nothing to do")
                return 0
            print("\napplying:")
            for note in apply(report, members, z, a.synthesize):
                print(note)
            write_pak(a.out, members)
            print(f"\nentries {validate_pak(a.out)}  ->  {a.out}")
    finally:
        z.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
