# Expeditions Vehicle Importer

**Ports SnowRunner trucks into Expeditions: A MudRunner Game.** Point it at a
mod and you get a vehicle that renders properly, keeps its bumpers and tyres,
and sits in the truck store with artwork that looks like it belongs there.

```
python port_vehicle.py port truck_mod.zip --id 12345 --name "My Truck"
```

The two games share one Saber mod format, so the meshes come across as they are.
Everything wrapped around them needs converting, and that's the part this does
for you:

| | |
|---|---|
| **Textures** | re-encoded with the game's own converter, so the truck isn't a black silhouette |
| **Accessories** | bumpers, side steps and spare wheels put back, including the ones that live in SnowRunner |
| **Tyres** | dead wheel sets swapped for Expeditions ones that fit, matched on scale |
| **Store artwork** | cards, thumbnails and previews built from one screenshot |
| **Skins** | extra paint schemes, chrome, and camouflage from a real swatch |
| **Consoles** | textures built for PlayStation, Xbox and Switch, not just Windows |

It ships no game content. **You need Expeditions. You do not need SnowRunner**
to port a mod you downloaded, because the mod zip carries its own meshes and
textures. SnowRunner is only required when the mod leans on its base game: see
*Do I need SnowRunner?* below. Three mods have been through it so far: a Toyota
Tundra, a two-vehicle Jeep pack, and a 1969 Bronco.

## Personal use only. Read this before you upload anything.

**This tool exists to get trucks into your own game. It is not a way to
republish other people's work, and I don't endorse using it that way.**

A SnowRunner truck belongs to whoever built it. **Only the original author has
permission to publish a port of their own vehicle.** If that's you, I'd
genuinely encourage it, and this is here to make it straightforward. Bring your
work across.

If it isn't you, keep the port on your own machine. Asking the author first and
crediting them is not a courtesy, it's the condition.

## Install

```
git clone https://github.com/Pr1m4lc0d3/expeditions-vehicle-importer
cd expeditions-vehicle-importer
pip install -r requirements.txt
```

Python 3.10 or newer, on Windows, because that's where the games and their
converter live.

The tools go looking for your installs on their own. Environment variable first,
then Steam's library list, then the usual folders, and a candidate only counts if
a marker file proves it's really that game. Check what it found:

```
python game_paths.py
```

If it comes up empty, tell it and it'll stop guessing:

```
set EXPEDITIONS_DIR=D:\Games\ExpeditionsAMudRunnerGame
set SNOWRUNNER_DIR=D:\Games\SnowRunner
```

### Do I need SnowRunner?

**For a normal port, no.** You download a truck from mod.io without owning the
game it was made for, and the zip contains everything the port needs. The
converter that does the re-encoding ships with Expeditions, not SnowRunner.

SnowRunner has to be installed for exactly two jobs, and both are optional:

| | |
|---|---|
| `restore_addons.py` | bumpers, side steps and spare wheels that live in SnowRunner's own files rather than in the mod |
| `extract_snowrunner.py` | tuning-only mods, which ship class XML and reuse base-game meshes and textures |

If a port comes out missing its accessories, or `analyze` reports a mod with no
meshes of its own, that is when you need the game. Not before.

## Use

```
python port_vehicle.py analyze <mod.zip>
python port_vehicle.py port    <mod.zip> --id <modid> --name "My Truck"
```

`analyze` changes nothing. It tells you what you're holding: meshes, materials,
which textures have no colour to draw from, and which artwork fields the author
left out. `port` re-encodes the textures with the game's own converter, repacks,
and installs.

Then take a screenshot in the garage and finish the artwork:

```
python vehicle_ui.py --howto
python vehicle_ui.py mod.pak out.pak --shot shot.png --name MyTruck \
    --box 1500 760 3830 2010 --safe 1560 330 3830 1808
```

Read [docs/runbook.md](docs/runbook.md) before your first port. It's the whole
process in order, with each trap sitting at the step where it actually bites you.

## The tools

| | |
|---|---|
| `port_vehicle.py` | the port itself: analyse, re-encode, repack, install |
| `port_sounds.py` | gives a ported truck its engine back. Runs automatically on install |
| `expeditions_features.py` | inventory limit, supplies cameras, metal detector, garage tabs, and the gear carrier you choose. Runs automatically on install |
| `expedition_racks.py` | borrows a stock truck's rack, gear and drone carrier, when you choose one for a vehicle |
| `protect_mods.ps1` | stops the mod.io client deleting locally-installed ports |
| `restore_addons.py` | gives a truck back the bumpers, side steps and spare wheel it lost |
| `vehicle_ui.py` | store and garage artwork from a screenshot. `--howto` explains the shot |
| `vehicle_skins.py` | extra paint schemes via `MaterialOverride` and a preset rebuild |
| `camo_from_source.py` | turns a photographed camouflage swatch into a tiling texture |
| `extract_snowrunner.py` | lifts meshes and textures out of SnowRunner, for tuning-only mods |
| `dds_to_tga.py` | DDS to TGA, in the row order the engine expects |
| `vehicle_pak.py` | pak and mesh-container format. The only thing here that writes TGA bytes |
| `console_build.py` | textures for all six platforms, and a pak for each |
| `game_paths.py` | finds your installs |
| `test_texture_format.py` | regression guard on row order, with a negative control |

## Reaching console players

mod.io hosts a separate upload per platform and hands each player the matching
one. That's why a published mod can list PlayStation, Xbox and Switch while the
folder on your PC only ever contains `pc.pak`. Build Windows only and you reach
Windows players.

```
python console_build.py <skin_root> <out_dir>
```

That writes six paks: `pc`, `nx64`, `playstation_4`, `playstation_5`,
`xbox_one`, `xbox_series`. The textures are the real thing, produced by the
game's own converter, and they genuinely differ per platform: on one 4096-wide
texture PlayStation 4 and Xbox One come out byte-identical at 354,446 while
Switch lands at 158,438 against Windows' 349,694.

One honest caveat. The texture generation is measured. The **pak naming is
inferred** from the Windows convention and from the build-part names in the
engine's own `os_build_part_manager.cpp`. Confirming it needs one real console
vehicle mod to inspect, and you can't download one onto a PC. If you have a
console build to compare against, I'd like to see it.

## Two things that'll save you time

You can't decode a `.pct`. The payload is proprietary, and every byte offset in
the file scores as noise against a known source image. So don't try. You
re-encode instead, using `ResourceConverter.exe`, which ships with Expeditions.
`port_vehicle.py` checks that encoder against a file the game itself produced
before it touches anything of yours.

One file owns the TGA format, and that's deliberate. Row order is the bug that
costs days: invisible on a flat colour and on tiled camo, catastrophic on a real
UV atlas. Eight separate writers existed here once, and fixing one of them left
seven. There's one now, and `test_texture_format.py` fails if another shows up.

## Your ported truck will be silent, and nothing will tell you

A port carries SnowRunner's truck XML across unchanged, so its `Sound="..."`
references still name SnowRunner banks — `trucks/jeep_cj7/...`. Expeditions has
40 truck sound banks and none of those is among them. Every reference resolves
to nothing, the XML is perfectly well formed, and the vehicle makes no noise at
all. Three vehicles shipped that way here before anyone noticed.

`port_sounds.py` fixes it and `install()` runs it on every port, so you get this
for free. To check or repair an existing mod by hand:

```
python port_sounds.py "<mod folder>"            # audit, changes nothing
python port_sounds.py --apply "<mod folder>"    # convert and install
```

It pulls the original audio out of SnowRunner, converts it, ships it inside your
`pc.pak` and repoints the references. Two things worth knowing:

**Those `.pcm` files are not raw PCM.** They're RIFF/WAVE holding MS ADPCM at
4 bits. Read one as linear 16-bit and you get a lag-1 correlation of about
-0.03, which is noise — real audio sits near +0.9. The conversion target is
PCM, mono, 48 kHz, 16-bit, which is what the one mod already proven to have
working sound uses.

**Don't put sound in the engine's own `[sound]/` namespace.** That system runs
off `sound.sound_list`, a bare length-prefixed list of paths, and a mod can't
add to it. A file that isn't in that index doesn't exist to the game. Ship
`.wav` under `sounds/<folder>/` in your `pc.pak` instead — that's what every
mod with working audio does.

## Your ported truck can't carry gear, and nothing will tell you that either

SnowRunner has no expeditions, so a ported truck arrives with none of the
systems they run on. It has no `<Inventory MaxLimit>`, so it has no gear
capacity, and it has no consumable addons, so there's no battery, fuel can,
spare parts or spare wheel to load. Its accessories are filed under
`Category="frame_addons"`, a tab stock scouts don't have, so the garage
doesn't show them either.

`expeditions_features.py` adds what's missing, using stock values for the
truck's class, and `install()` runs it on every port. To check or repair an
existing mod by hand:

```
python expeditions_features.py "<mod folder>"            # audit, changes nothing
python expeditions_features.py --apply "<mod folder>"    # patch and write
```

It also adds the locked `supplies_*` cameras stock trucks use and a
metal-detector mount on scouts.

**One thing it leaves to you: what carries the gear.** Every one of the game's
471 batteries, fuel cans and parts boxes names the rack, bumper or box it sits
on, and gear without one shows up in the garage as an ordinary upgrade. Which
carrier suits a vehicle, where it sits and what holds it up are that vehicle's
call, so the importer never picks one. It tells you instead:

```
! no gear carrier: batteries, fuel and parts need a rack to sit on.
```

[docs/expedition-gear.md](docs/expedition-gear.md) walks the choice. In short,
`expedition_racks.py` borrows a stock truck's rack, gear models and drone
carrier straight out of your own game files. You compare several in the garage,
move the one you like into place, and the choice is saved inside the vehicle so
later runs keep it:

```
python expeditions_features.py --apply --racks don --offset don=-0.21,1.01,0 "<mod folder>"
```

If a borrowed rack's feet land on nothing, the guide covers building a small
accessory of your own for them to stand on, and making the rack require it.

## Documentation

* [docs/runbook.md](docs/runbook.md) is the whole port in order. Start there.
* [docs/expedition-gear.md](docs/expedition-gear.md) covers giving a port
  somewhere to carry batteries, fuel and spare parts: borrowing a stock rack,
  placing it, drone carriers, and mounts of your own.
* [docs/why-trucks-go-black.md](docs/why-trucks-go-black.md) covers the texture
  encoding problem, the eighteen things that aren't causing it, and how to tell
  whether you need to re-encode at all.
* [docs/accessories-and-tyres.md](docs/accessories-and-tyres.md) covers bumpers,
  side steps, spare wheels and tyre sets: everything a port loses to the game it
  came from.
* [docs/artwork.md](docs/artwork.md) covers every image field, its size, which
  ones have to be cut-outs, and how to frame the screenshot.
* [docs/skins-and-paint.md](docs/skins-and-paint.md) covers material overrides,
  tint masks, chrome, and camouflage built from a real swatch.
* [docs/diagnosing.md](docs/diagnosing.md) covers what to read when there's no
  error, and why the evidence is gone if you relaunch.

## Other things I've built

I write AI tooling, and a fair bit of this toolkit was built alongside an agent
rather than by hand.

* **[Deliberon](https://github.com/Pr1m4lc0d3/deliberon-releases)** runs a
  council of AI specialists that argue a decision out and sign the record.
  Windows, local.
* **[KiSYSTEM](https://github.com/Pr1m4lc0d3/KiSYSTEM)** keeps AI-written code
  modular and readable, enforced from the base of a project.
* **[Peitho](https://github.com/Pr1m4lc0d3/peitho)** is a writing skill built on
  classical rhetoric and the studies that contradict most hook advice.
* **[Ekphrasis](https://github.com/Pr1m4lc0d3/ekphrasis)** does the same job for
  image prompts.

Everything else is indexed at
[ryan-heltemes.com](https://ryan-heltemes.com).

## Scope

Written against Expeditions: A MudRunner Game and SnowRunner, both Saber
Interactive. Unaffiliated with Saber and with Focus Entertainment. Ships no game
content and redistributes nobody's mod.

**Porting someone else's work is their call, not yours.** Only the original
author has permission to publish a port of their vehicle. See *Personal use
only* above; it is the condition, not a suggestion.

MIT licensed. See [LICENSE](LICENSE).

## Why this exists

Saber walked away from this game and from the people who bought it. I'm not
going to.

Look at the gap: **SnowRunner has 533 community maps. Expeditions has ten.** Of
its 177 public mods, 144 are vehicles. The number of real custom base modules is
zero. That isn't for lack of interest, it's that everything outside a vehicle
swap took weeks of reverse engineering before a single file would load, and the
studio that could have written it down never did.

People buy these games for the modding. That's the main attraction, it's what
the community was promised at purchase, and being abandoned doesn't cancel the
promise. It just means somebody else has to do the work.

So every format gets written down and published free, so the next person starts
from something instead of nothing. The goal is a community that can build
whatever it wants, the way SnowRunner and MudRunner players always could.

## Support this

Free, and it stays free. Saber documented almost none of this and then ended
support for the game, so every trap in these docs was found the slow way. If it
saved you an afternoon, a dollar covers it: **https://ko-fi.com/ryanheltemes**
