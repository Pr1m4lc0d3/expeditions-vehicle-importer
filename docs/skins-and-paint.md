
# Skins and paint

A `CustomizationPreset` is the button the player presses in the garage. It looks
like it carries three tint colours, and it does, but it also names a
**`MaterialOverride`** — and an override can replace the albedo outright. That is
the difference between offering a repaint and offering a livery.

```xml
<MaterialOverride AlbedoMap="trucks/carroceria_jungle__d.tga"
                  Name="skin_jungle" TargetMaterialName="carroceria"
                  TintMap="trucks/carroceria_notint__d.tga" />
```

```xml
<CustomizationPreset Id="14" MaterialOverrideName="skin_jungle" TintColor1="..." />
```

## The two rules that make it work properly

### Give a pattern a tint mask with R=0

The red channel of the `TintMap` defines the overall paint zone, so an area with
no red **never tints**. A camouflage or livery then shows exactly as painted
instead of being recoloured by whatever the preset's tint happens to be.

The same mechanism pins a part to a fixed colour. A hard top that should always
be black gets a black albedo and an R=0 mask, and the garage colour picker then
cannot touch it while still recolouring the body around it.

### Mirror the override onto every mesh that has the others

Addons, bumpers and racks carry their own `MaterialOverride` entries. Add a new
skin only to the body and the body goes camouflage while the bumpers stay
factory.

The practical rule: for each mesh, find the materials `skin_00` already targets,
and add the new skin for the same ones.

> **⚠ Preset Ids must be contiguous from 0**
>    A gap in the numbering produces buttons that exist and do nothing. If you
> are adding presets, rebuild the whole list rather than appending.

## Tint colours and what the player actually sees

**measured** `TintMap` has no separate green or blue paint zones on most truck bodies — only
the red channel is a real zone. A preset that sets `TintColor1`, `2` and `3` to
three different colours therefore advertises a two- or three-tone that will not
happen.

If the vehicle has no multi-zone mask, set all three the same so the garage
swatch shows exactly what you get.

## Chrome

An override can also change `ShadingMap`, which is where chrome comes from: very
high metalness, very low roughness. Because the preset still tints it, **one
chrome skin gives you gold, blue and black chrome from three presets** rather
than needing three textures.

> **ℹ Gloss lives in the shading map, not the colour**
>    `ShadingMap` is R metalness, G roughness, B ambient occlusion. A flat
> roughness around 160 reads matte and makes every colour look cheap;
> automotive paint wants roughly 40–60. If your colours look flat and plasticky,
> that is the first thing to check — not the albedo.

## Camouflage from a real pattern

A generated pattern is fine. A real one looks better, and Wikimedia Commons
carries clean swatches.

> **ℹ Licensing is in your favour, but check each file**
>    Images of U.S. military patterns are public domain as works of the U.S.
> Government — no attribution, no share-alike, safe to redistribute inside a
> mod. The same search also returns CC BY-SA uploads whose terms are awkward
> for one. Check the licence on each file rather than the search.

A photographed swatch is not a texture. Three things need fixing, and
`camo_from_source.py` does all three:

**The lighting gradient.** Any photographed fabric is brighter on one side.
Divide by a heavily blurred copy of itself and re-centre on the mean, or the
pattern reads as dirty across one flank of the vehicle.

**The edges do not meet.** Offset the image by half in both axes and blend the
cross seam that exposes. Mirror-tiling is also seamless but produces obvious
symmetry, which camouflage shows badly.

**The scale is wrong.** A swatch photographed at life size is far too coarse once
wrapped onto a body panel. Tile it two or three times across the texture.

> **⚠ A hue shift keeps the original lightness**
>    Recolouring a desert pattern to woodland by rotating hue gives a pale mint
> green, because desert tan is light and a hue rotation preserves that. Pull
> the value down to about 0.6 and raise saturation as well.

## Before you generate anything

Everything on this page writes textures, which means it is downstream of the one
rule that governs every texture in this game:

> **⛔ TGA rows go bottom-up**
>    Write them top-down and every texture is vertically flipped — **invisible**
> on a flat colour and on a tiled camouflage pattern, and catastrophic on a
> real UV atlas.

> A generated-skin vehicle therefore looks perfect while carrying the bug,
> and hands it to you later on the first truck with genuine artwork. See
> [Porting a SnowRunner truck](why-trucks-go-black.md).
