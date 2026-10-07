
# Porting runbook, start to finish

Expeditions and SnowRunner share one mod format, so a SnowRunner vehicle can be
brought across. Meshes port untouched. Almost nothing else does, and **every
single failure in this process is silent** — the truck spawns, drives, and looks
nearly right while being wrong.

This page is the order to do it in. [Why each thing breaks](why-trucks-go-black.md)
is a separate read.

> **⛔ The one rule that governs all of this**
>    **Nothing here reports an error.** Not a missing addon class, not a dead
> wheel set, not an undeclared image field, not a flipped texture. The game
> logs almost nothing and falls back to nothing. If you do not verify a step,
> you will not find out until you are looking at it in game — or until someone
> else is.

## 0. Decide what you are porting

| you have | result |
|---|---|
| a full vehicle mod (meshes + textures + classes) | ports; textures must be re-encoded |
| a **tuning rework** (classes only, expects the base game's DLC assets) | you must also lift the meshes and textures out of SnowRunner |
| the author's source `.fbx` / `.tga` | not required. The packed route works. |

**measured** "Needs the author's FBX" is wrong — a packed mod ports with re-encoded textures
alone.

## 1. Analyse before you build

```
python port_vehicle.py analyze <mod.zip|mod.pak>
```

Reports the materials, which ones it has colours for, which ones the author
declared but never put in the mesh, and what artwork the mod ships. Read it
before anything else.

## 2. Classes: ship the mod's own, never the donor's truck classes

> **⛔ Injecting the donor game's truck classes shreds the vehicle**
>    A SnowRunner truck class shadows the mod's rework of the same vehicle. The
> symptom is a mangled, wrong-looking truck and `Not found engine for truck
> <name>_<modid>` in the log.

> Ship **the mod's** gameplay classes. Take meshes and textures from
> SnowRunner, not class XML.

## 3. Addons: put back the stock accessories

The previous step creates this problem. Bumpers, side steps and the spare wheel
are **separate addon classes**, installed only because the truck's
`<AddonSockets>` names one in `DefaultAddon`. Two ways that breaks, both silent:

* the mod names a `DefaultAddon` whose class lives in the **donor game** — and
  you just excluded the donor's classes;
* the mod's own class **dropped** a `DefaultAddon` the donor declares, so the
  socket is simply empty with nothing missing from the pak at all.

```
python restore_addons.py analyze <main.pak> --pc <pc.pak>
python restore_addons.py fix     <main.pak> <out.pak> --pc <pc.pak>
```

It pairs the mod's truck class to the donor's on **socket names, not
filenames** — a mod renames `jeep_cj7_renegade.xml` but cannot rename
`CJ7FrontBumper` without breaking its own meshes. It refuses to enable an addon
whose mesh is absent, and reports textures with no encoded `.pct`.

> **⚠ A spare wheel can ride on another addon**
>    On the CJ7 the spare is part of the **rear bumper** addon, so one dropped
> default costs both parts. Do not assume one missing item is one missing
> class.

> **⚠ A dangling DefaultAddon is not cosmetic**
>    A declared `DefaultAddon` whose class is absent leaves a reference the game
> cannot resolve, and the save records it too. Fix it; do not ship it.

If a class exists in neither game, `--synthesize` rebuilds it from the donor's
template for that kind — **mesh-less addons only**, because cloning geometry
between trucks bolts on the wrong part.

## 4. Wheels: map dead tyre sets by SCALE

`<CompatibleWheels Type="...">` names a wheel class. SnowRunner's names do not
exist in Expeditions, so the game logs `Unknown wheels type` for each one and the
truck ends up with almost no tyres to buy — which also reads in game as
*"There are no suitable devices for this truck"*.

**Choose replacements on the scale the target game runs them at, not on how many
tyres they carry.** A set stock trucks run at 0.55–0.66 will be visibly
undersized on a truck scaled 0.43, and rescaling is inventing geometry rather
than mapping.

> **⚠ Keep the truck's own `OffsetZ`**
>    Offset is hub geometry. Copying the donor truck's value pushes the wheels
> outside the arches. Reuse the value from the dead entry for the matching
> tyre category on the **same truck**.

## 5. Textures: re-encode with the game's own converter

A ported truck renders **solid black** because its `.pct` files were encoded by
SnowRunner's converter and Expeditions cannot decode them. The container header
is byte-identical between the games, so you cannot tell by looking.

Do not try to decode `.pct`. Re-encode instead, with
`Sources\Bin\ResourceConverter.exe`.

```
ResourceConverter.exe --all-pct -s -r <modRoot> -i textures/trucks/X.tga \
> -o prebuild/textures/pct/trucks_X.pct
```

* **`-i` is relative to `-r`.** An absolute path gives `Unable to find texture
  file` about a file that is plainly there.
* **`-o` is relative to the working directory**, not `-r`. Never run it from the
  game's `Bin` folder — a half-written `prebuild\` beside `Expeditions.exe`
  stops the game launching.
* **`-s` is mandatory.** Without it an assert can open a modal dialog and wait
  forever.

> **ℹ Source TGAs you may already have**
>    SnowRunner's `mod.pak` ships the modding-template assets uncompressed — 49
> real `.tga` files, including the shared scout rims and tyres. Better input
> than a DDS decode. Take DDS from `editor.pak`, never `.pct` from
> `shared_textures.pak`.

### Always test the encoder first

The game's sample mod ships both the source `.tga` and the `.pct` the game made
from it. Re-encode one and compare: it should be **byte-identical**. The toolkit
does this automatically and refuses to continue if it fails.

> **⚠ One failure is not proof**
>    This self-test produced a single unreproducible failure that passed twice
> immediately afterwards, with all 50 sample textures re-encoding
> byte-identical. Re-run before believing it.

## 6. TGA rows go bottom-up. This one costs days.

The engine's `.tga` files store row 0 as the **bottom** row. Write them top-down
and every texture is vertically flipped.

That is **invisible** on a flat colour and on a tiled camo pattern, and it
**completely scrambles a real UV atlas**. A generated-skin vehicle looks perfect
and hides the bug until you port one with genuine artwork.

```
tga read as-stored vs its own dds : MAE 52.4   wrong
tga read flipped   vs its own dds : MAE  0.3   correct
```

Check orientation **first** when a texture looks wrong. It is one comparison, and
`test_texture_format.py` guards it.

## 7. Repack without extra fields

`pc.pak` is a plain zip, but Python's `zipfile` copies `ZipInfo.extra` into the
**local** header as well as the central directory, and the engine then fails to
read that member. Build fresh `ZipInfo` objects and inflate every member
afterwards to validate.

## 8. Artwork

Full detail in [Store and garage artwork](artwork.md). The two
that cost the most:

* `TruckImage` / `TruckImageSmall` must be **RGBA cut-outs**, zoomed ~1.4
  frame-heights and anchored **top** so the crop lands at the bumper. An opaque
  screenshot renders as nothing.
* `TruckImageSmall` lives on `<TruckData>`, and 43 of 44 stock trucks omit it —
  so it must be **inserted**, not substituted. Tooling that only substitutes
  ships the PNG with no field pointing at it.
* `UiIcon40x40` / `UiIcon30x30` stay on the **shared** category glyph. A
  per-vehicle name there renders an empty tab.

## 9. Install

Three files go to `.modio\mods\<id>\`: `<Name>.pak`, a file named literally
`pc.pak`, and `modio.json`.

> **⚠ The game deletes hand-planted mods while signed out of mod.io**
>    With `user.id = 0` in `authentication.json` it reconciles `.modio\mods`
> against the subscriptions it knows about and removes anything it cannot
> account for, then drops the vehicle from the garage and saves.
> `restore_mods.ps1` puts them back.

Never swap a pak while the game is running, and never remove a mod a save
references.

## 10. Verify, because nothing will tell you

```
python restore_addons.py analyze <installed.pak> --pc <installed pc.pak>
```

Then launch and check, in this order:

1. the truck renders in colour, not black
2. its bumpers, side steps and spare are on it
3. the tyre list in Customize is populated
4. the store thumbnail and large preview are **this** truck
5. the card in the truck list is zoomed like the stock ones
6. the fleet tab at the top of truck selection is not empty

Then read `base\logs\LegacyLog.txt`. `Failed to load texture` should be zero, and
`Unknown wheels type` should be absent.

> **ℹ A clean log proves nothing on its own**
>    If you are comparing against a mod that works, check it is mentioned in the
> log **at all**. A short launch-and-quit may never have loaded it, and its
> silence then means nothing.

## 11. When something is wrong

**The logs are wiped at every launch.** So are the crash dumps. If something
fails, **quit the game and do not relaunch** before looking.

| artefact | what it is good for |
|---|---|
| `base\ssl_crash_dump\ssl_dump_*.json` | `callstack[0]` names the exact script function, class and arguments. The `objects` section carries the game's **live loaded data**, which is the only readable copy of stock values that ship compiled. |
| `base\logs\LegacyLog.txt` | often 0 bytes while running; written on exit |
| `base\CrashScreenshot.jpg` | shows which screen it died on |

A dump with **zero callstack frames** is a native crash, not a script one, and
`dxdiag.txt` appearing beside it means the game's own reporter fired.

> **⚠ Verify the artefact you are actually running**
>    Hash the installed pak against your build before reasoning about it. A
> conclusion drawn from a stale file is worse than no conclusion, and it has
> happened here more than once.
