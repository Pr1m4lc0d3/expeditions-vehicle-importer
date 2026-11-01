# Expedition gear: giving a port somewhere to carry it

A ported truck drives, renders and sounds right, and still can't be loaded for
an expedition. This page is about the part the importer deliberately leaves to
you: **what carries the batteries, fuel cans and spare parts.**

## What the importer does, and what it won't

`expeditions_features.py` runs on every install and adds what every Expeditions
truck needs, using stock values for the truck's class:

* a gear limit (`<Inventory MaxLimit>`), deploy cost, battery charge, radio range
* the locked `supplies_*` cameras the supplies screen uses
* the mod's own accessories moved out of `frame_addons`, a tab scouts don't have
* a metal-detector mount on the roof (scouts)

What it **won't** do is pick a rack. In Expeditions every battery, fuel can and
parts box names the rack, bumper or box it sits on, and gear without a carrier
shows up in the garage as an ordinary upgrade. Which carrier suits a vehicle,
where it sits, and what holds it up are that vehicle's call, not the
importer's. A truck with a hard roof wants something different from an open
roll cage, so a default would be wrong more often than right.

Until you choose, the install says:

```
! no gear carrier: batteries, fuel and parts need a rack to sit on.
```

## 1. Try several racks side by side

The tool borrows a stock truck's rack straight out of your own game files: its
rack model, its gear models (drawn, and gone as you use them), and its slot
layout. Give it several at once and compare them in the garage:

```
python expeditions_features.py --apply --racks khan_marshall,don,scout "<mod folder>"
```

| `--racks` | donor | needs |
|---|---|---|
| `khan_marshall` | Khan 39 Marshall roof rack | base game |
| `don` | Don 71 roof rack | base game |
| `cotco` | Cotco Canyon roof rack (long) | base game |
| `scout` | Harvester Scout 800 roof rack | DLC 3 |
| `shiba`, `shiba_bed` | Shiba Overlander roof rack, bed rack | DLC 5 |

Each shows under **Roof** as *Expedition Rack (donor)*. A rack from a DLC only
works for players who own that DLC.

## 2. Move the one you like

Each rack starts where the donor's roof lines up with the highest winch points
the mod's author placed. That's a first guess. Move it in metres, X forward and
Y up, and look again:

```
python expeditions_features.py --apply --racks don --offset don=-0.21,1.01,0 "<mod folder>"
```

Take a screenshot from the side each time. A tyre makes a good ruler: you can
measure how far a foot misses a tube in pixels and convert. Expect a few
rounds; centimetres matter.

## 3. Keep one

Run again with just the rack you chose. **Your choices are saved inside the
vehicle**, in its own truck XML, so later runs and reinstalls keep them:

```
python expeditions_features.py --apply --racks don "<mod folder>"
python expeditions_features.py "<mod folder>"          # "up to date"
```

`--racks none` removes the rack again.

## 4. Ground drones (scouts, DLC 6)

Each stock drone carrier mounts on a socket named for its truck, so a port can
borrow one by declaring that socket. Like racks, offer only the ones that fit:

```
python expeditions_features.py --apply --drones don --offset don.drone=-0.29,0.89,0 "<mod folder>"
```

`RACK.drone=` moves the carrier separately from the rack: carriers usually sit
on the cage, racks on the roof.

## 5. When the rack's feet land on nothing

A borrowed rack's feet are made for its donor's roof. On a different body they
can hang in the air. The fix is a small accessory of your own that gives them
something to stand on, for example crossbars across a roll cage. Make the rack
require it, so the rack is never fitted floating:

```
python expeditions_features.py --apply --require don=<your_addon_name> "<mod folder>"
```

Your accessory is an ordinary `TruckAddon` in `classes/trucks/<truck>_tuning/`
with its own socket in the truck XML. Put the socket **outside** the block
marked `expeditions_features`; everything inside that block is regenerated on
every run. Things that cost real time getting the first one right:

* **Sockets with no `ParentFrame` are in the truck's root space.** Build the
  model in truck coordinates and give the socket no offset.
* **Don't add a root object in Blender.** The FBX already has a `RootNode`. An
  extra empty keeps Blender's metre-to-centimetre factor as a x100 scale, and
  the accessory is bought, fitted and invisible: drawn 100 times too big, far
  from the truck. Put the mesh and its `cdt` collider at the top level.
* **Export with no axis conversion** (`axis_forward="Y", axis_up="Z"`,
  `apply_unit_scale=False`). The converter turns Blender's Z-up into Y-up itself.
* **Check what the game reads, not just your model:** every frame's scale must
  be 1 and the bounds in the converted mesh's header must be in metres.

Measure the tubes and the feet from the converted meshes rather than from
screenshots where you can. A mod's own meshes store positions as plain 28-byte
vertices after each material block; stock meshes compress theirs.

## Later

Racks borrowed from stock trucks are a stopgap. The aim is a way to design our
own bumpers, racks and accessories to fit each vehicle properly.
