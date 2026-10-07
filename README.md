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

It ships no game content, so you'll need your own copy of each game. Three mods
have been through it so far: a Toyota Tundra, a two-vehicle Jeep pack, and a
1969 Bronco.

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

You only need SnowRunner if you're porting from it.

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
| `restore_addons.py` | gives a truck back the bumpers, side steps and spare wheel it lost |
| `vehicle_ui.py` | store and garage artwork from a screenshot. `--howto` explains the shot |
| `vehicle_skins.py` | extra paint schemes via `MaterialOverride` and a preset rebuild |
| `camo_from_source.py` | turns a photographed camouflage swatch into a tiling texture |
| `extract_snowrunner.py` | lifts meshes and textures out of SnowRunner, for tuning-only mods |
| `dds_to_tga.py` | DDS to TGA, in the row order the engine expects |
| `vehicle_pak.py` | pak and mesh-container format. The only thing here that writes TGA bytes |
| `game_paths.py` | finds your installs |
| `test_texture_format.py` | regression guard on row order, with a negative control |

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

## Documentation

* [docs/runbook.md](docs/runbook.md) is the whole port in order. Start there.
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

Porting someone else's work is their call, not yours. Ask first, and credit them.

MIT licensed. See [LICENSE](LICENSE).
