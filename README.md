# Expeditions Vehicle Importer

**Bring a SnowRunner vehicle into Expeditions: A MudRunner Game — and find the
six things that break silently when you do.**

The two games share one Saber mod format, so a SnowRunner truck's meshes load in
Expeditions untouched. Almost nothing else does. The truck spawns, drives, and
looks nearly right while being wrong, and **not one of these failures reports an
error**:

| what you see | what it actually is |
|---|---|
| the truck is **solid black** | its `.pct` textures were encoded by SnowRunner's converter |
| a real livery comes out **scrambled** | `.tga` rows are stored bottom-up; writing them top-down flips every texture |
| **no front bumper, no spare wheel** | addon classes live in the donor game, or the mod dropped the socket default |
| **"no suitable devices for this truck"** | its tyre sets name wheel classes Expeditions does not ship |
| the **fleet tab is empty** | a per-vehicle image was put where a shared glyph belongs |
| the card **hangs over its border** | the image is 380×110 in a 4:1 widget |

This repo is the tooling and the written-down answers. It ships **no game
assets** — you need your own copy of each game.

---

## Install

```
git clone https://github.com/Pr1m4lc0d3/expeditions-vehicle-importer
cd expeditions-vehicle-importer
pip install -r requirements.txt
```

Python 3.10+. Windows, because the games and their converter are.

The tools find your installs themselves — environment variable first, then
Steam's library list, then the usual folders, and a candidate is only accepted
if a marker file proves it really is that game. Check what it found:

```
python game_paths.py
```

If it cannot find them, set them and it will stop guessing:

```
set EXPEDITIONS_DIR=D:\Games\ExpeditionsAMudRunnerGame
set SNOWRUNNER_DIR=D:\Games\SnowRunner
```

SnowRunner is only needed when you are porting *from* it.

## Use

```
python port_vehicle.py analyze <mod.zip>
python port_vehicle.py port    <mod.zip> --id <modid> --name "My Truck"
```

`analyze` changes nothing and tells you what you are dealing with: meshes,
materials, which textures have no colour source, and which artwork fields the
mod forgot. `port` re-encodes the textures with the game's own converter,
repacks and installs.

Then take a screenshot in the garage and finish the artwork:

```
python vehicle_ui.py --howto
python vehicle_ui.py mod.pak out.pak --shot shot.png --name MyTruck \
    --box 1500 760 3830 2010 --safe 1560 330 3830 1808
```

**Read [docs/runbook.md](docs/runbook.md) before your first port.** It is the
whole process in order with each trap at the step where it bites.

## The tools

| | |
|---|---|
| `port_vehicle.py` | the port itself: analyse, re-encode, repack, install |
| `restore_addons.py` | give a truck back the bumpers, side steps and spare wheel it lost |
| `vehicle_ui.py` | store and garage artwork from a screenshot; `--howto` explains the shot |
| `vehicle_skins.py` | extra paint schemes via `MaterialOverride` + preset rebuild |
| `camo_from_source.py` | turn a photographed camouflage swatch into a tiling texture |
| `extract_snowrunner.py` | lift meshes and textures out of SnowRunner, for tuning-only mods |
| `dds_to_tga.py` | DDS → TGA in the row order the engine expects |
| `vehicle_pak.py` | pak and mesh-container format. The only thing that writes TGA bytes |
| `game_paths.py` | finds your installs |
| `test_texture_format.py` | regression guard on the row order, with a negative control |

## Two things worth knowing before you start

**The encoder is the game's own.** `.pct` cannot be decoded — the payload is
proprietary and every byte offset scores as noise against a known source. You do
not decode it, you re-encode. `ResourceConverter.exe` ships with Expeditions, and
`port_vehicle.py` verifies it against a file the game itself produced before
touching anything.

**One writer owns the TGA format.** Row order is the bug that costs days: it is
invisible on a flat colour and on tiled camo, and it completely scrambles a real
UV atlas. Eight separate writers existed here once and fixing one left seven.
There is one now, and `test_texture_format.py` fails if another appears.

## Documentation

* **[docs/runbook.md](docs/runbook.md)** — the whole port in order. Start here.
* [docs/artwork.md](docs/artwork.md) — every image field, its size, which must be
  cut-outs, and how to compose the screenshot.
* [docs/why-trucks-go-black.md](docs/why-trucks-go-black.md) — the texture
  encoding problem in full, and the eighteen things that are *not* causing it.

## Credits and scope

Written against Expeditions: A MudRunner Game and SnowRunner, both Saber
Interactive. This project is unaffiliated with Saber and with Focus
Entertainment, ships no game content, and does not redistribute anyone's mod.

Porting someone else's mod to another game is their call, not yours. Ask first,
and credit them.

MIT licensed — see [LICENSE](LICENSE).
