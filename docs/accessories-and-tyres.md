
# Accessories and tyres

A truck is not one object. Its bumpers, side steps, spare wheel and tyre sets are
**separate classes**, referenced by name, and a port loses them in two different
ways that look identical in game: the part is simply not there, and nothing is
logged about it.

This is the second of the three failure kinds in a port — the mod is not broken,
it just depends on something only the donor game has.

## Accessories

Each is an addon class, installed because the truck's `<AddonSockets>` element
names one in `DefaultAddon`:

```xml
<AddonSockets DefaultAddon="jeep_cj7_renegade_bumper_default">
> <Socket Names="CJ7FrontBumper" />
</AddonSockets>
```

Two things go wrong.

### The class lives in the donor game

And you excluded the donor's classes — correctly, because including its **truck**
classes shadows the mod's own rework and produces a mangled vehicle. It is easy
to exclude too much while fixing that.

### The mod dropped the default

Nothing is missing from the pak at all. The socket is there, the class may even
be shipped, and the `DefaultAddon` attribute is simply absent, so nothing is
installed. **Indistinguishable from the first case once you are in game.**

```
python restore_addons.py analyze <main.pak> --pc <pc.pak>
python restore_addons.py fix     <main.pak> <out.pak> --pc <pc.pak>
```

It pairs the mod's truck class to the donor's on **socket names, not
filenames**. A mod renames `jeep_cj7_renegade.xml` to `JTTs_jeep_renegade.xml`
freely, but it cannot rename `CJ7FrontBumper` without breaking its own meshes,
so the sockets are the stable identity.

> **⚠ One missing part is not always one missing class**
>    **measured**     On the CJ7 the **spare wheel rides on the rear bumper addon**. A single
> dropped default cost both parts, and looking for a separate "spare wheel"
> class would have found nothing wrong.

> **⛔ A dangling `DefaultAddon` is not cosmetic**
>    A declared default whose class is absent leaves a reference the game cannot
> resolve — and the save records it too. Fix it rather than shipping it.

If a class exists in neither game, `--synthesize` rebuilds it from the donor's
template for that kind. **Mesh-less addons only**: cloning geometry between
trucks bolts the wrong part on, so the tool refuses.

## Tyres

`<CompatibleWheels Type="...">` names a wheel class, and each class holds the
tyre variants the player can buy:

```xml
<CompatibleWheels OffsetZ="0.10" Scale="0.43" Type="wheels_scout_mudtires" />
```

SnowRunner's names do not exist in Expeditions. The game logs
`Unknown wheels type` for each one and the truck ends up with almost nothing to
buy — which reads in the garage as **"There are no suitable devices for this
truck"**, a message that does not mention wheels at all.

### Choose replacements on scale, not on tyre count

**measured** This is the part that is tempting to get wrong. The richest-looking tyre set is
not the right one; the right one is the one the target game runs **at the scale
your truck is already built for**.

| stock scout class | scale stock trucks use it at |
|---|---|
| `wheels_scout2` | 0.37 – 0.52 |
| `wheels_scout_shiba_dart_srv` | 0.43 – 0.45 |
| `wheels_scout_shiba_dart_srv_2` | 0.43 – 0.45 |
| `wheels_scout_yar_87` | 0.55 – 0.66 |
| `wheels_scout_collie_PUG_293` | 0.63 – 0.65 |

A truck scaled 0.43 given a set stock runs at 0.63 comes out visibly
undersized. Rescaling to compensate is inventing new geometry, not mapping — and
you will be eyeballing wheel diameter against an arch you cannot measure.

> **⚠ Keep the truck's own `OffsetZ`**
>    Offset is **hub geometry**, not tyre geometry. Copy the donor truck's value
> and the wheels sit outside the arches. Reuse the value from the truck's own
> dead entry for the matching tyre category.

### Check before you look for a cause

```
Game| Unknown wheels type 'wheels_scout_offroad'
Game| Unknown wheels type 'wheels_scout_mudtires'
```

Those lines in `base\logs\LegacyLog.txt` are the whole diagnosis. A truck with
no tyre options is nearly always this, and it is cheaper to read than to guess
at.
