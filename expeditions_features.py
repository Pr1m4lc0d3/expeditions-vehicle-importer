#!/usr/bin/env python3
"""Switch on the Expeditions game systems a SnowRunner truck has never heard of.

THE BUG THIS EXISTS FOR
-----------------------
A port drives, renders and sounds right, and still cannot be outfitted for an
expedition: no batteries, no spare parts, no fuel cans, no spare wheel. Its own
accessories are missing from the garage too. Nothing errors. Measured on the
Bronco 2026-11-01 against the six stock scouts:

* **No gear capacity.** Every stock truck declares ``<Inventory MaxLimit=N/>``
  and ``<DeployCost Cost="1"/>`` inside ``<TruckData>``, plus
  ``ElectricChargeCapacity`` and ``SignalRadius``. SnowRunner has none of these.
* **Nothing to carry gear on.** Each supply is a consumable ``TruckAddon`` that
  sits in a slot on a rack, and names that rack in ``<RequiredAddon>`` (all 471
  stock ones do). Gear without a carrier lists as an ordinary upgrade. See
  expedition_racks.py, which borrows a stock truck's rack and drone carrier.
* **Accessories in a tab scouts don't have.** SnowRunner authors file their
  addons under ``Category="frame_addons"``. No stock scout uses that category;
  in Expeditions it belongs to frame modules on bigger trucks. Scouts list
  ``top``, ``rear``, ``fender_front``, ``miscellenious`` (the game's spelling)
  and ``snorkel``.
* **No supplies cameras.** Stock trucks clone ``roof``/``rear``/``default``/
  ``side_l`` as ``supplies_*`` cameras with rotation locked; ports have none.
* **Metal detector.** Five of six stock scouts carry a ``ScoutMetalDetector``
  socket; the detector itself is a shared addon, so a socket is all it needs.

Truck fields, tabs and cameras are added only where missing. A gear carrier is
NEVER chosen for you: which rack suits a vehicle, where it sits and what holds
it up are the vehicle's call (owner, 2026-11-01), so a fresh port gets none and
the tool says so. Whatever is chosen with ``--racks``/``--drones``/``--offset``/
``--require`` is saved inside the vehicle's own truck XML and reused, and
everything generated from it is regenerated on every run, so changing a choice
swaps parts rather than piling them up. See docs/expedition-gear.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import expedition_racks as er
import vehicle_pak as vp

# Stock values per class, read off the game's own trucks (median, rounded).
CLASS_DEFAULTS = {
    "SCOUT":   {"inventory": 4, "charge": 10, "signal": 90,  "recovery": 1500},
    "OFFROAD": {"inventory": 6, "charge": 16, "signal": 135, "recovery": 3400},
    "HEAVY":   {"inventory": 8, "charge": 30, "signal": 200, "recovery": 5000},
}

# frame_addons -> the scout tab that matches where the camera looks
CATEGORY_BY_CAMERA = {"roof": "top", "rear": "rear", "hoods": "fender_front"}
FRAME_MODULE_SOCKET = re.compile(r"^Frame(Module|Addon)", re.I)
SUPPLY_CAMERAS = ("default", "roof", "rear", "side_l")

# A vehicle's gear choices. Empty unless someone chooses for that vehicle; they
# are stored in its own truck XML, on the marked block's opening comment, and
# reused on every run.
GEAR_FIELDS = {"racks": [], "drones": [], "offsets": {}, "requires": {}}

BEGIN_TAG, END = "<!-- expeditions_features: begin", "<!-- expeditions_features: end -->"
GENERATED_FILE = re.compile(r"_tuning/[^/]+_(supply_|expedition_rack|exp_)[^/]*\.xml$")
# sockets the first two versions wrote before the marked block existed
LEGACY_SOCKET = re.compile(r'[ \t]*<AddonSockets>\s*(<Socket Names="\w+(SupplySlot\d+|'
                           r'SpareWheelSlot|ExpeditionRack\w*)"[^>]*/>|<Socket InCockpit="true" '
                           r'Names="ScoutMetalDetector" Offset="\([-\d.]+; [-\d.]+; 0\)" />)'
                           r'\s*</AddonSockets>\r?\n')


def _truckdata_open(xml: str) -> re.Match | None:
    """The <TruckData ...> open tag that declares the truck, not an addon's."""
    for m in re.finditer(r"<TruckData\b[^>]*>", xml):
        if "TruckType=" in m.group(0):
            return m
    return None


def _main_gamedata(xml: str) -> tuple[re.Match, int] | None:
    """(open tag, index of its </GameData>) for the truck's own <GameData>."""
    m = re.search(r"<GameData\b[^>]*>", xml)
    if not m:
        return None
    end = xml.find("</GameData>", m.end())
    return (m, end) if end >= 0 else None


def truck_type(xml: str) -> str:
    m = re.search(r'TruckType="(\w+)"', xml)
    return m.group(1).upper() if m and m.group(1).upper() in CLASS_DEFAULTS else "SCOUT"


# --------------------------------------------------------------- truck fields

def fix_truck_fields(xml: str, kind: str) -> tuple[str, list[str]]:
    d, notes = CLASS_DEFAULTS[kind], []
    m = _truckdata_open(xml)
    if not m:
        return xml, ["! no <TruckData TruckType=...>; truck fields left alone"]
    tag = m.group(0)
    new_tag = tag
    for field, val in (("ElectricChargeCapacity", d["charge"]),
                       ("SignalRadius", f'{d["signal"]}.0')):
        if not re.search(rf"\b{field}\s*=", new_tag):
            new_tag = re.sub(r"\s*/?>$", f'\n\t\t{field}="{val}"\n\t>', new_tag)
            notes.append(f'TruckData {field}="{val}"')
    xml = xml[:m.start()] + new_tag + xml[m.end():]

    children = ""
    if not re.search(r"<Inventory\b", xml):
        children += f'\n\t\t<Inventory MaxLimit="{d["inventory"]}" />'
        notes.append(f'<Inventory MaxLimit="{d["inventory"]}"/> ({kind.lower()} stock)')
    if not re.search(r"<DeployCost\b", xml):
        children += '\n\t\t<DeployCost Cost="1" />'
        notes.append('<DeployCost Cost="1"/>')
    if children:
        at = m.start() + len(new_tag)
        xml = xml[:at] + children + xml[at:]

    g = _main_gamedata(xml)
    if g and "RecoveryPrice=" not in g[0].group(0):
        open_tag = g[0].group(0)
        patched = re.sub(r"\s*>$", f'\n\t\tRecoveryPrice="{d["recovery"]}"\n\t>', open_tag)
        xml = xml[:g[0].start()] + patched + xml[g[0].end():]
        notes.append(f'GameData RecoveryPrice="{d["recovery"]}"')
    return xml, notes


# ---------------------------------------------------------------- accessories

def fix_categories(members: dict[str, bytes]) -> list[str]:
    """frame_addons -> a tab the truck has. Real frame modules keep theirs."""
    notes = []
    for name, data in members.items():
        if not re.match(r"classes/trucks/[^/]+_tuning/[^/]+\.xml$", name):
            continue
        text = data.decode("utf-8", "replace")
        if 'Category="frame_addons"' not in text:
            continue
        sock = re.search(r'<InstallSocket[^>]*Type="([^"]+)"', text)
        if sock and FRAME_MODULE_SOCKET.match(sock.group(1)):
            continue
        cam = re.search(r'CameraPreset="([^"]+)"', text)
        cat = CATEGORY_BY_CAMERA.get(cam.group(1).lower() if cam else "", "miscellenious")
        members[name] = text.replace('Category="frame_addons"',
                                     f'Category="{cat}"').encode("utf-8")
        notes.append(f"{os.path.basename(name)}: frame_addons -> {cat}")
    return notes


def add_supply_cameras(xml: str) -> tuple[str, list[str]]:
    """supplies_<x> = the truck's own <x> camera with rotation and zoom locked."""
    added = []
    for name in SUPPLY_CAMERAS:
        if re.search(rf'Name="supplies_{name}"', xml):
            continue
        m = re.search(rf'<CameraPos\b[^>]*\bName="{name}"[^>]*/>', xml)
        if not m:
            continue
        cam = m.group(0).replace(f'Name="{name}"', f'Name="supplies_{name}"')
        cam = re.sub(r'\b(MaxXRotation|MaxYRotation|MaxZoom)="[^"]*"', r'\1="0"', cam)
        xml = xml[:m.end()] + "\n\t\t\t" + cam + xml[m.end():]
        added.append(f"supplies_{name}")
    return xml, ([f"supplies cameras: {', '.join(added)}"] if added else [])


# ------------------------------------------------------------ generated parts

def drop_generated(members: dict[str, bytes], cls: str) -> dict:
    """Remove everything an earlier run generated, so this run starts clean.

    Returns the vehicle's saved gear settings from the marked block, so the
    choices made for it (rack, offsets, mounts) survive the regeneration.
    """
    for n in [n for n in members if GENERATED_FILE.search(n)]:
        del members[n]
    xml = members[cls].decode("utf-8", "replace")
    m = re.search(rf"{re.escape(BEGIN_TAG)}\s*(\{{.*?\}})\s*-->", xml)
    saved = json.loads(m.group(1)) if m else {}
    xml = re.sub(rf"[ \t]*{re.escape(BEGIN_TAG)}.*?{re.escape(END)}\r?\n", "", xml, flags=re.S)
    xml = LEGACY_SOCKET.sub("", xml)
    members[cls] = xml.encode("utf-8")
    return saved


def roof_point(xml: str) -> tuple[float, float] | None:
    """(x, y) of the roof: the highest winch points the author placed.

    On stock scouts that sits within a few centimetres of where Saber put the
    metal detector. None when the author placed no winch points.
    """
    pts = [tuple(float(v) for v in p.split(";"))
           for p in re.findall(r'<WinchSocket\s+Pos="\(([^)]+)\)"', xml)]
    if not pts:
        return None
    top_y = max(p[1] for p in pts)
    roof = [p for p in pts if p[1] >= top_y - 0.05]
    return sum(p[0] for p in roof) / len(roof), top_y


def add_generated(members: dict[str, bytes], cls: str, kind: str, gear: dict) -> list[str]:
    xml = members[cls].decode("utf-8", "replace")
    g = _main_gamedata(xml)
    if not g:
        return ["! no <GameData>; no racks or sockets added"]
    roof, sockets, notes = roof_point(xml), "", []
    racks = gear["racks"]

    has_gear = any(n.startswith("classes/trucks/") and b'IsConsumable="true"' in v
                   for n, v in members.items())
    if has_gear:
        notes.append("mod ships its own gear slots; no rack added")
    elif not racks:
        notes.append("! no gear carrier: batteries, fuel and parts need a rack to sit on. "
                     "Pick one for this vehicle: docs/expedition-gear.md")
    else:
        # drone carriers are scout addons, and only the ones asked for: where a
        # carrier sits is as vehicle-specific as the rack
        offsets = {k: tuple(v) for k, v in gear["offsets"].items()}
        s, n = er.fit(members, cls, roof, racks, offsets,
                      drones=tuple(gear["drones"]) if kind == "SCOUT" else False,
                      requires=gear["requires"])
        sockets += s
        notes += n

    if kind == "SCOUT" and "ScoutMetalDetector" not in xml:
        if roof:
            sockets += (f'\t\t<AddonSockets>\n\t\t\t<Socket InCockpit="true" '
                        f'Names="ScoutMetalDetector" Offset="({roof[0]:.2f}; {roof[1]:.2f}; 0)" />'
                        f'\n\t\t</AddonSockets>\n')
            notes.append("ScoutMetalDetector socket on the roof")
        else:
            notes.append("! no winch points to place the metal detector; skipped")

    if sockets:
        at = xml.rfind("\n", 0, g[1]) + 1           # start of the </GameData> line
        saved = json.dumps(gear, sort_keys=True, separators=(",", ":"))
        if "--" in saved:                           # would end the XML comment early
            raise SystemExit(f"gear settings can't be stored in an XML comment: {saved}")
        xml = (xml[:at] + f"\t\t{BEGIN_TAG} {saved} -->\n" + sockets
               + f"\t\t{END}\n" + xml[at:])
        members[cls] = xml.encode("utf-8")
    return notes


# ------------------------------------------------------------------- entry

def apply_to_members(members: dict[str, bytes], update: dict | None = None) -> list[str]:
    """Patch a main pak's members in place. Returns what it did.

    `update` changes this vehicle's gear settings field by field; anything not
    given is what the vehicle already had saved (see GEAR_FIELDS).
    """
    cls = vp.truck_class(members)
    if not cls:
        return ["! no classes/trucks/<truck>.xml in this pak"]
    gear = {**GEAR_FIELDS, **drop_generated(members, cls), **(update or {})}
    xml = members[cls].decode("utf-8", "replace")
    crlf = "\r\n" in xml
    kind = truck_type(xml)
    xml, notes = fix_truck_fields(xml, kind)
    xml, cam_notes = add_supply_cameras(xml)
    members[cls] = xml.encode("utf-8")
    notes += cam_notes + fix_categories(members)
    notes += add_generated(members, cls, kind, gear)
    xml = members[cls].decode("utf-8", "replace")
    if crlf:                                        # keep the author's line endings
        xml = re.sub(r"(?<!\r)\n", "\r\n", xml)
        members[cls] = xml.encode("utf-8")
    if not vp.balanced_tags(xml):
        raise SystemExit(f"{cls}: XML no longer balances after patching -- not writing")
    return notes


def repair(mod_dir: str, apply: bool = False, update: dict | None = None) -> int:
    """Audit, or with apply=True patch, an installed mod folder's main pak."""
    from port_sounds import mod_paks
    main_path, _ = mod_paks(mod_dir)
    original = vp.read_pak(main_path)
    members = dict(original)
    notes = apply_to_members(members, update)
    changed = members != original
    print(f"   {os.path.basename(mod_dir)} ({os.path.basename(main_path)}): "
          f"{'needs patching' if changed else 'up to date'}")
    for n in notes:
        print(f"      {n}")
    if not changed:
        return 0
    if not apply:
        print("      (dry run; pass --apply to write)")
        return 0
    vp.write_pak(main_path, members)
    vp.validate_pak(main_path)
    print(f"      wrote {os.path.basename(main_path)}")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mod_dir", nargs="+", help="installed mod folder(s)")
    ap.add_argument("--apply", action="store_true",
                    help="patch and write. Without it, nothing is modified.")
    ap.add_argument("--racks", default=None,
                    help=f"donor racks, comma-separated: {', '.join(er.DONORS)}; "
                         "'none' to remove. Saved in the vehicle, so later runs keep "
                         "it. Nothing by default: which rack suits a vehicle is the "
                         "vehicle's call (docs/expedition-gear.md)")
    ap.add_argument("--offset", action="append", default=[], metavar="RACK=X,Y,Z",
                    help="move one rack, metres: X forward, Y up. RACK.drone=X,Y,Z "
                         "moves that donor's drone carrier instead. Repeatable; "
                         "replaces the saved offsets.")
    ap.add_argument("--drones", default=None,
                    help="ground-drone carriers to offer, comma-separated donors "
                         "from --racks, or 'none'. Saved in the vehicle.")
    ap.add_argument("--require", action="append", default=[], metavar="RACK=ADDON",
                    help="the rack can't be fitted without ADDON, e.g. mounts built "
                         "for this truck's roll cage. Repeatable.")
    a = ap.parse_args(argv)

    def names(s):
        return [] if s == "none" else [r.strip() for r in s.split(",") if r.strip()]

    update: dict = {}                               # only what was given; the rest is saved
    if a.racks is not None:
        update["racks"] = names(a.racks)
        bad = [r for r in update["racks"] if r not in er.DONORS]
        if bad:
            ap.error(f"unknown rack(s): {', '.join(bad)}")
    if a.drones is not None:
        update["drones"] = names(a.drones)
    if a.offset:
        update["offsets"] = {k: [float(v) for v in xyz.split(",")]
                             for k, _, xyz in (o.partition("=") for o in a.offset)}
    if a.require:
        update["requires"] = dict(r.split("=", 1) for r in a.require)
    for d in a.mod_dir:
        repair(d, apply=a.apply, update=update)
    return 0


if __name__ == "__main__":
    sys.exit(main())
