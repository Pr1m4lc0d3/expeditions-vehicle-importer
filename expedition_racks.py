#!/usr/bin/env python3
"""Borrow a stock truck's rack, gear and drone carrier for a ported truck.

Expeditions gear is never free-standing. All 471 stock batteries, fuel cans and
parts boxes name the rack, bumper or box that carries them in
``<RequiredAddon>``, and gear without one shows in the garage as an ordinary
upgrade instead of on the supplies screen (measured on the Bronco, 2026-11-01).
So a port needs a carrier, and the cheapest good one is a stock truck's own:
its rack model, its six-odd gear models that disappear as they're used, and its
supply cameras all already exist in the game.

A donor's parts are copied out of the game's ``initial.pak`` verbatim, renamed
so they cannot collide with the stock addons, and fitted to the port with one
socket offset: the donor's roof point (where Saber put its metal detector)
lined up with the port's highest winch points. Ground-drone carriers work the
same way with no copying at all: each stock carrier installs on a socket named
for its truck, so declaring that socket on the port offers it.

Donor parts from a DLC need that DLC. Drone carriers are all DLC content.
"""

from __future__ import annotations

import os
import re
import zipfile

import game_paths as gp

INITIAL_PAK = os.path.join("preload", "paks", "client", "initial.pak")
INVISIBLE_MESH = "trucks/addons/invisible_mesh"

# roof: the donor's metal-detector offset, i.e. its roof in its own model space
DONORS = {
    "khan_marshall": {"dir": "classes/trucks/khan_39_marshall_tuning",
                      "rack": "khan_39_marshall_roofrack_01", "roof": (-0.73, 2.33),
                      "drone": "DroneScoutCarrierKhanMarshall", "dlc": None,
                      "label": "Khan Marshall"},
    "don": {"dir": "classes/trucks/don_71_tuning", "rack": "don_71_roofrack_01",
            "roof": (-0.55, 1.62), "drone": "DroneScoutCarrierDon71", "dlc": None,
            "label": "Don 71"},
    "cotco": {"dir": "classes/trucks/cotco_canyon_tuning", "rack": "cotco_canyon_roofrack_01",
              "roof": (-1.3, 2.055), "drone": "DroneScoutCarrierCotcoCanyon", "dlc": None,
              "label": "Cotco Canyon"},
    "scout": {"dir": "_dlc/EXP_DLC_03/classes/trucks/harvester_scout_800_tuning",
              "rack": "harvester_scout_800_roofrack_01", "roof": (-0.75, 1.75),
              "drone": "DroneScoutCarrierScout", "dlc": "EXP_DLC_03", "label": "Scout 800"},
    "shiba": {"dir": "_dlc/EXP_DLC_05/classes/trucks/shiba_overlander_tuning",
              "rack": "shiba_overlander_roofrack", "roof": (-0.15, 2.05),
              "drone": "DroneScoutCarrierShibaOverlander", "dlc": "EXP_DLC_05",
              "label": "Shiba roof"},
    "shiba_bed": {"dir": "_dlc/EXP_DLC_05/classes/trucks/shiba_overlander_tuning",
                  "rack": "shiba_overlander_backrack", "roof": (-0.15, 2.05),
                  "drone": None, "dlc": "EXP_DLC_05", "label": "Shiba bed"},
}
# No default. A rack, where it sits and what holds it up belong to each vehicle:
# the Bronco needed the Don 71 rack raised onto custom crossbars, and a truck
# with a hard roof needs something else entirely. The importer never guesses;
# docs/expedition-gear.md walks the choice. (Owner, 2026-11-01.)
DEFAULT_RACKS: tuple[str, ...] = ()

SPARE_WHEEL = """<TruckAddon>
\t<PhysicsModel Mesh="{mesh}" />
\t<TruckData WheelRepairsCapacity="1" />
\t<GameData
\t\tCameraPreset="supplies_roof"
\t\tCategory="top"
\t\tIsConsumable="true"
\t\tIsCustomizable="false"
\t\tPrice="1000"
\t\tUnlockByExploration="false"
\t\tUnlockByRank="1"
\t>
\t\t<UiDesc UiDesc="UI_TUNING_SPARE_WHEEL_WHEEL_NAME" UiIcon30x30="" UiIcon40x40="" UiName="UI_TUNING_SPARE_WHEEL_WHEEL_NAME" />
\t\t<RequiredAddon Types="{racks}" />
\t\t<InstallSocket Type="{socket}" />
\t</GameData>
</TruckAddon>
"""

_game_classes: dict[str, bytes] | None = None


def game_classes() -> dict[str, bytes]:
    """Every stock truck tuning XML, keyed by its path under [media]/."""
    global _game_classes
    if _game_classes is None:
        path = os.path.join(gp.expeditions_dir(), INITIAL_PAK)
        with zipfile.ZipFile(path) as z:
            _game_classes = {n[len("[media]/"):]: z.read(n) for n in z.namelist()
                             if n.startswith("[media]/") and "/classes/trucks/" in "/" + n[8:]
                             and n.endswith(".xml")}
    return _game_classes


def _camel(s: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[^A-Za-z0-9]+", s) if p)


def _requires(text: str, rack: str) -> bool:
    m = re.search(r'<RequiredAddon\s+Types="([^"]+)"', text)
    return bool(m) and rack in [t.strip() for t in m.group(1).split(",")]


def donor_groups(key: str) -> list[list[str]]:
    """The donor truck's socket groups, as declared.

    Sockets inside one <AddonSockets> are alternatives: one item fits the group.
    The Don's fuel and repair slots share a spot this way. Split them into
    separate groups and both can be filled, one drawn inside the other.
    """
    truck = DONORS[key]["dir"].rsplit("_tuning", 1)[0] + ".xml"
    xml = game_classes().get(truck, b"").decode("utf-8", "replace")
    groups = []
    for g in re.findall(r"<AddonSockets\b[^>]*>(.*?)</AddonSockets>", xml, re.S):
        names = [n.strip() for s in re.findall(r'<Socket\b[^>]*\bNames="([^"]+)"', g)
                 for n in s.split(",")]
        if names:
            groups.append(names)
    return groups


def donor_parts(key: str) -> dict[str, str]:
    """{stock stem: xml} for a donor's rack and every consumable it carries."""
    d = DONORS[key]
    files = {os.path.basename(n)[:-4]: v.decode("utf-8", "replace")
             for n, v in game_classes().items() if n.startswith(d["dir"] + "/")}
    if d["rack"] not in files:
        raise SystemExit(f"{d['rack']} not found in the game's {INITIAL_PAK}")
    parts = {d["rack"]: files[d["rack"]]}
    for stem, text in files.items():
        if 'IsConsumable="true"' in text and _requires(text, d["rack"]):
            parts[stem] = text
    return parts


def fit(members: dict[str, bytes], cls: str, roof: tuple[float, float] | None,
        racks=DEFAULT_RACKS, offsets: dict | None = None,
        drones: bool = True, requires: dict | None = None) -> tuple[str, list[str]]:
    """Write the donors' parts into `members`; return (socket XML, notes).

    `requires` maps a rack to an addon that must be fitted first, e.g. mounts
    that tie its feet to a port's roll cage. `drones` is the donors whose
    ground-drone carrier the port gets: False for none, True for every rack's.
    """
    if drones is True:
        drones = tuple(racks)
    offsets, requires, notes, sockets = offsets or {}, requires or {}, [], ""
    prefix = os.path.splitext(os.path.basename(cls))[0]
    stem, folder = _camel(prefix), cls[:-4] + "_tuning"
    xml = members[cls].decode("utf-8", "replace")

    def place(key):
        if key in offsets:
            return offsets[key]
        if roof is None:
            return None
        rx, ry = DONORS[key]["roof"]
        return (roof[0] - rx, roof[1] - ry, 0.0)

    def socket(names, off):
        o = "({:.3f}; {:.3f}; {:.3f})".format(*off)
        inner = "".join(f'\t\t\t<Socket Names="{n}" Offset="{o}" />\n' for n in names)
        return f"\t\t<AddonSockets>\n{inner}\t\t</AddonSockets>\n"

    new_racks = []
    for key in racks:
        d, off = DONORS[key], place(key)
        if off is None:
            notes.append(f"! {key}: no winch points to fit the rack; pass an offset")
            continue
        new_rack = f"{prefix}_exp_{key}"
        renamed = {}
        for old, text in donor_parts(key).items():
            for s in re.findall(r'<InstallSocket[^>]*Type="([^"]+)"', text):
                renamed.setdefault(s, f"{stem}Exp{_camel(key)}{s}")
            text = re.sub(r'(<InstallSocket[^>]*Type=")([^"]+)"',
                          lambda m: f'{m.group(1)}{renamed[m.group(2)]}"', text)
            if old == d["rack"]:
                # the donor's own prerequisite (the Shiba rack needs the Shiba's
                # hardtop) means nothing on a port; renamed, it pointed at itself
                text = re.sub(r'\s*<RequiredAddon\b[^>]*/>', "", text)
                if key in requires:
                    text = re.sub(r'(\s*)(<InstallSocket\b)',
                                  rf'\1<RequiredAddon Types="{requires[key]}" />\1\2', text, count=1)
                text = re.sub(r'UiName="[^"]*"', f'UiName="Expedition Rack ({d["label"]})"', text, count=1)
                name = new_rack
            else:
                text = re.sub(r'<RequiredAddon\s+Types="[^"]+"',
                              f'<RequiredAddon Types="{new_rack}"', text)
                name = f"{new_rack}__{old}"
            members[f"{folder}/{name}.xml"] = text.encode("utf-8")
        done, spots = set(), 0
        for group in donor_groups(key) + [[s] for s in renamed]:
            mine = [s for s in group if s in renamed and s not in done]
            if mine:
                sockets += socket([renamed[s] for s in mine], off)
                done.update(mine)
                spots += 1
        new_racks.append(new_rack)
        dlc = f", needs {d['dlc']}" if d["dlc"] else ""
        notes.append(f"rack {d['label']} at ({off[0]:.2f}; {off[1]:.2f}; {off[2]:.2f}): "
                     f"{spots - 1} gear spot(s){dlc}")

        if drones and key in drones and d["drone"] and d["drone"] not in xml:
            doff = offsets.get(f"{key}.drone", off)    # carriers sit on the cage, not the rack
            sockets += socket([d["drone"]], doff)
            notes.append(f"ground-drone carrier {d['label']} at "
                         f"({doff[0]:.2f}; {doff[1]:.2f}; {doff[2]:.2f}) (needs EXP_DLC_06)")

    if new_racks:
        wheel = f"{stem}ExpSpareWheel"
        sockets += f'\t\t<AddonSockets>\n\t\t\t<Socket Names="{wheel}" />\n\t\t</AddonSockets>\n'
        members[f"{folder}/{prefix}_exp_spare_wheel.xml"] = SPARE_WHEEL.format(
            mesh=INVISIBLE_MESH, racks=", ".join(new_racks), socket=wheel).encode("utf-8")
        notes.append("spare-wheel slot on any expedition rack (not drawn)")
    return sockets, notes
