#!/usr/bin/env python3
"""Build every store and garage image a ported vehicle needs, from a screenshot.

A texture port can be flawless and the vehicle still shows the SAMPLE truck's
artwork everywhere, because a mod inherits the sample's image names and nobody
replaces the images. None of it logs anything. The fields, and how many of the
game's 44 stock trucks use each:

    TruckImage       44/44  fleet and loadout strip      380x92   <- most missed
    UiIcon576x640    43/44  large store preview          576x640
    UiIcon328x458    40/44  store list thumbnail         328x458
    UiIconLogo       40/44  manufacturer badge            80x80
    TruckImageSmall    1    compact list variant         124x52
    UiIcon40x40/30x30 44/44 fleet tab glyph               40x40, 30x30

The last pair are SHARED category sprites (scoutVehicleImg x27, offroadVehicleImg
x13, heavyVehicleImg x2) and must stay that way: they resolve for stock trucks
and for every working mod, while a per-vehicle name there renders an EMPTY tab.
--category picks which glyph to inherit.

UiIcon328x458 is absent from the editor's type schema yet used by 42 of 44
trucks: schema absence is not invalidity.

    python vehicle_ui.py mod.pak out.pak --shot shot.png --name Tundra \\
        --box 1560 900 3700 1790 --badge TRD
"""

from __future__ import annotations

import argparse
import io
import re
import sys

from vehicle_pak import read_pak, truck_class, validate_pak, write_pak

# field -> (basename suffix, width, height, greyscale)
SLOTS = [
    ("UiIcon328x458",   "shopImg{n}",      328, 458, False),
    ("UiIcon576x640",   "shopImg{n}Exp",   576, 640, False),
    ("uiIcon576x640Bw", "shopImg{n}ExpBW", 576, 640, True),
]

# Composited into the UI, so they need the vehicle CUT OUT on alpha -- an opaque
# screenshot here renders as nothing. `fill` > 1 zooms in so the card matches the
# stock ones, which crop at the bumper.
#
# 380x92 (4.13:1), NOT the 380x110 that one working mod ships. The widget is
# 768x192 -- exactly 4:1 -- and scales the image to its WIDTH, so a 3.45:1 card
# arrives 222px tall in a 192px box and HANGS OVER THE BOTTOM BORDER. 4.13:1
# lands at 186 and sits inside it.
CUTOUTS = [
    ("TruckImage",      "{n}mchr",         380,  92, 1.4),
    ("TruckImageSmall", "{n}mchrSmall",    124,  52, 1.4),
]

# The fleet/loadout tabs across the top of truck selection.
#
# ⚠ DO NOT give these per-vehicle images. Every one of the 44 stock trucks and
# every mod here points them at a SHARED category glyph -- scoutVehicleImg x27,
# offroadVehicleImg x13, heavyVehicleImg x2 -- and those render. Repointing them
# at a per-vehicle name and shipping the PNG produces an EMPTY tab, which is the
# bug this once tried to fix. The other image fields do resolve shipped files;
# these two evidently do not, so inherit the glyph and leave them alone.
CATEGORY_GLYPH = {"scout": ("scoutVehicleImg", "scoutVehicleImg30"),
                  "offroad": ("offroadVehicleImg", "offroadVehicleImg30"),
                  "heavy": ("heavyVehicleImg", "heavyVehicleImg30")}


HOWTO = """\
COMPOSING THE SCREENSHOTS FOR A VEHICLE'S STORE AND GARAGE ART
==============================================================

You need TWO things from the game, and one of them is easy to get wrong.

1. THE SHOT
   Headquarters -> Truck selection -> select the vehicle, so it is on the
   turntable lit by the garage lights. Take it at your desktop resolution; the
   --box numbers below are in that image's own pixels.

   * THREE-QUARTER FRONT. Not side-on, not nose-on. Every stock card and every
     working mod uses roughly 30-45 degrees off the nose.
   * Fill the frame. The vehicle should be the biggest thing in the shot. You
     cannot zoom in later without losing resolution.
   * Keep it clear of the left-hand truck list and of the button row along the
     bottom right.
   * A SECOND SHOT from Customize (press F) is often better lit and has no
     stats panel over the scene. Either works.

2. THE TWO RECTANGLES YOU PASS IN

   --box  L T R B   a rectangle that CONTAINS the whole vehicle. It does not
                    have to be tight -- the tool mattes the vehicle and measures
                    the real silhouette itself. Being too SMALL is the only real
                    mistake: it clips the roof or the bed and you will not
                    notice until the card is built.

   --safe L T R B   the part of the screenshot with NO HUD in it. The store
                    portraits are cropped from the scene, so any button or
                    label inside this rectangle gets baked into the artwork.
                    THIS IS PER-SHOT. On one truck the nose reaches under the
                    "M Map" row so you must crop above it; on another the
                    vehicle stops short and you can instead cut the right edge.
                    Look at your own screenshot and decide.

   --exclude L T R B   optional, repeatable. A crate, post or panel standing
                    AGAINST the bodywork merges into the silhouette and the
                    matte cannot tell it apart. Paint it out with this.

3. WHAT GETS BUILT, AND WHERE EACH ONE SHOWS UP

   field             size      kind          where you see it
   ---------------------------------------------------------------------------
   TruckImage        380x92    cut-out       the card in the truck list
   TruckImageSmall   124x52    cut-out       compact list variant
   UiIcon328x458     328x458   scene photo   store list thumbnail
   UiIcon576x640     576x640   scene photo   large store preview
   uiIcon576x640Bw   576x640   scene, grey   greyscale variant
   UiIconLogo        80x80     badge         manufacturer badge
   UiIcon40x40 / 30x30         SHARED GLYPH  fleet tabs -- NOT per-vehicle

   The two cut-outs are RGBA on transparency and are ZOOMED so the vehicle
   crops at the bumper, which is what every stock card does. An opaque
   screenshot in those slots renders as nothing at all.

   Do NOT give the fleet tabs their own images. Every stock truck and every
   working mod points them at a shared category glyph; a per-vehicle name
   there produces an empty tab.
"""


def fit_box(box, aspect: float, safe) -> tuple[int, int, int, int]:
    """Grow the vehicle's box to the target aspect, clamped to the SAFE region.

    Letterboxing leaves dead bands and the game may zoom to fill, which clips the
    vehicle. Growing into the surrounding scene fills the frame with real pixels
    instead. Clamping to a safe region matters for the wide strip images: a
    380x92 slot is over 4:1, so it grows a long way sideways and will happily
    swallow the truck-selection panel if you let it reach the screen edge.
    """
    sl, st, sr, sb = safe
    l, t, r, b = box
    cx, cy = (l + r) / 2, (t + b) / 2
    w, h = r - l, b - t
    if w / h < aspect:
        w = h * aspect                       # too tall: widen
    else:
        h = w / aspect                       # too wide: heighten
    w, h = min(w, sr - sl), min(h, sb - st)
    if w / h > aspect:                       # clamping broke it: re-derive
        w = h * aspect
    else:
        h = w / aspect
    l = max(sl, min(sr - w, cx - w / 2))
    t = max(st, min(sb - h, cy - h / 2))
    return int(l), int(t), int(l + w), int(t + h)


def render(im, box, safe, w: int, h: int, bw: bool):
    from PIL import Image
    crop = im.crop(fit_box(box, w / h, safe)).resize((w, h), Image.LANCZOS)
    return crop.convert("L").convert("RGB") if bw else crop


_SESSION = None


def largest_blob(sub):
    """Keep only the biggest connected region of the alpha mask.

    A crop that reaches the vehicle's extremities also reaches HUD text -- the
    "M Map  H Codex" row sits right of the Tundra's front wheel and there is no
    rectangle containing the whole truck that excludes it. Anything the matte
    picks up out there is a separate island, and dropping every island but the
    largest removes it without having to shrink the box and clip the vehicle.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return sub                                 # no scipy: bbox only
    import numpy as np
    a = np.array(sub.getchannel("A"))
    lab, n = ndimage.label(a > 24)
    if n <= 1:
        return sub
    keep = 1 + int(np.argmax(ndimage.sum(a > 24, lab, range(1, n + 1))))
    out = np.array(sub)
    out[..., 3] = np.where(lab == keep, a, 0)
    from PIL import Image
    return Image.fromarray(out, "RGBA")


def paint_out(im, rects):
    """Blank scene objects that touch the vehicle, before the matte runs.

    A crate or post standing against the bodywork merges into the silhouette, so
    it survives both the matte and the largest-blob filter -- they cannot tell it
    is a separate thing when it shares an edge. Filling it with the median colour
    of the strip just below it continues the floor and leaves nothing salient.
    """
    from PIL import Image
    import numpy as np
    im = im.copy()
    for (l, t, r, b) in rects:
        h = max(4, (b - t) // 6)
        below = np.array(im.crop((l, min(b, im.height - h), r, min(b + h, im.height))))
        fill = tuple(int(v) for v in np.median(below.reshape(-1, 3), axis=0))
        patch = Image.new("RGB", (r - l, b - t), fill)
        im.paste(patch, (l, t))
    return im


def vehicle_bbox(im, box):
    """Where the vehicle actually is, in SOURCE coordinates.

    `--box` only has to CONTAIN the vehicle -- being generous there is safe for
    the cut-outs, which re-crop to the matte anyway, but it would throw the
    portrait crops off centre. Measuring the silhouette once removes the need to
    hand-tune the box to the pixel.
    """
    global _SESSION
    from rembg import new_session, remove
    if _SESSION is None:
        _SESSION = new_session("isnet-general-use")
    sub = largest_blob(remove(im.crop(box).convert("RGB"), session=_SESSION))
    bb = sub.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if not bb:
        return tuple(box)
    return (box[0] + bb[0], box[1] + bb[1], box[0] + bb[2], box[1] + bb[3])


def cutout(im, box, w: int, h: int, fill: float = 1.0):
    """Isolate the vehicle on transparency and compose it into w x h.

    The card needs a CUT-OUT on alpha, not a rectangle of scene: an opaque RGB
    screenshot shows nothing at all.

    `fill` is how many frame-heights tall the vehicle is drawn. 1.0 fits it
    whole and looks SMALL next to stock trucks, which are zoomed in far enough
    to crop at the bumper. Measured on FJ Bruiser's card -- the one mod here
    whose images are real files rather than atlas sprites, so the only readable
    reference: its content spans 50% of the width and touches BOTH the top and
    bottom edges, with 109 of 380 pixels filled on the bottom row. That is a
    vehicle overflowing the frame by about half, not one fitted inside it.
    """
    global _SESSION
    from PIL import Image
    from rembg import new_session, remove
    if _SESSION is None:
        _SESSION = new_session("isnet-general-use")
    sub = remove(im.crop(box).convert("RGB"), session=_SESSION)
    sub = largest_blob(sub)

    bbox = sub.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox:
        sub = sub.crop(bbox)                       # drop the empty margin

    # Anchored LEFT and TOP. The overflow must fall entirely off the BOTTOM so
    # the cut lands at the bumper and the roof, windscreen and grille all stay.
    # Centring it instead splits the overflow and crops the windscreen off the
    # top, which is wrong however good the zoom level is.
    scale = (h * fill) / sub.height
    if sub.width * scale > w:                      # a very long vehicle: cap on width
        scale = w / sub.width
    sub = sub.resize((max(1, int(sub.width * scale)), max(1, int(sub.height * scale))),
                     Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(sub, (0, 0), sub)
    return canvas


def badge(text: str, size: int = 80):
    """A simple manufacturer badge, since the sample truck's logo is not ours."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=14,
                        fill=(22, 24, 28, 255), outline=(208, 212, 218, 255), width=3)
    font = None
    for cand in ("arialbd.ttf", "segoeuib.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(cand, int(size * 0.34))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    tb = d.textbbox((0, 0), text, font=font)
    d.text(((size - (tb[2] - tb[0])) / 2 - tb[0], (size - (tb[3] - tb[1])) / 2 - tb[1]),
           text, font=font, fill=(226, 230, 236, 255))
    return img


def put_truckdata_attr(xml: str, field: str, value: str) -> str:
    """Add an attribute to the <TruckData> element that carries the truck images.

    TruckImage and TruckImageSmall live on <TruckData>, not <UiDesc>, and a mod
    that never declared TruckImageSmall needs it INSERTED -- substitution alone
    silently does nothing, which ships the image file with no field pointing at
    it. Anchor on the tag that already holds TruckImage; a class can carry
    several <TruckData> elements and only one of them is the right one.
    """
    m = re.search(r'\bTruckImage="[^"]*"', xml)
    if m:
        return xml[:m.end()] + f' {field}="{value}"' + xml[m.end():]
    m = re.search(r"<TruckData\b", xml)
    if m:
        return xml[:m.end()] + f' {field}="{value}"' + xml[m.end():]
    return xml


def patch_fields(xml: str, name: str, with_badge: bool,
                 category: str = "scout") -> tuple[str, list[str]]:
    """Point every per-vehicle image field at our own names."""
    notes = []
    g40, g30 = CATEGORY_GLYPH[category]
    wanted = {"UiIcon328x458": f"shopImg{name}",
              "UiIcon576x640": f"shopImg{name}Exp",
              "uiIcon576x640Bw": f"shopImg{name}ExpBW",
              "TruckImage": f"{name}mchr",
              "TruckImageSmall": f"{name}mchrSmall",
              # shared glyph, deliberately NOT per-vehicle -- see CATEGORY_GLYPH
              "UiIcon40x40": g40,
              "UiIcon30x30": g30}
    if with_badge:
        wanted["UiIconLogo"] = f"{name}Logo80"

    # TruckImage* live in <TruckData>, the UiIcon* in <UiDesc>; both are plain
    # attributes, so a targeted substitution is enough.
    for field, value in wanted.items():
        pat = re.compile(rf'\b{re.escape(field)}="[^"]*"')
        if pat.search(xml):
            old = pat.search(xml).group(0)
            if old != f'{field}="{value}"':
                xml = pat.sub(f'{field}="{value}"', xml, count=1)
                notes.append(f"{field}: {old.split('=')[1].strip(chr(34))} -> {value}")
        elif field.startswith("TruckImage"):
            xml = put_truckdata_attr(xml, field, value)
            notes.append(f"{field}: added to <TruckData> -> {value}")
        elif field.startswith("UiIcon") or field == "uiIcon576x640Bw":
            m = re.search(r"<UiDesc", xml)
            if m:
                xml = xml[:m.end()] + f'\n\t\t\t{field}="{value}"' + xml[m.end():]
                notes.append(f"{field}: added -> {value}")
    return xml, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--howto", action="store_true",
                    help="print how to compose the screenshots, and what each "
                         "image field is for, then exit")
    if "--howto" in sys.argv:
        print(HOWTO)
        return 0
    ap.add_argument("pak")
    ap.add_argument("out")
    ap.add_argument("--shot", required=True, help="in-game screenshot of the vehicle")
    ap.add_argument("--name", required=True, help="image basename, e.g. Tundra")
    ap.add_argument("--box", type=int, nargs=4, required=True, metavar=("L", "T", "R", "B"),
                    help="box around the VEHICLE only. Keep clear of the UI: on a "
                         "3840x2160 garage shot the truck panel ends near x=1540 and "
                         "the HUD button row starts near y=1790")
    ap.add_argument("--safe", type=int, nargs=4, metavar=("L", "T", "R", "B"),
                    help="region of the screenshot free of game UI. The wide strip "
                         "images grow sideways and will otherwise swallow the "
                         "truck-selection panel. Defaults to the whole image.")
    ap.add_argument("--exclude", type=int, nargs=4, action="append", default=[],
                    metavar=("L", "T", "R", "B"),
                    help="paint out a scene object that touches the vehicle before "
                         "matting, e.g. a crate standing against the bodywork. "
                         "Repeatable. Source-image coordinates.")
    ap.add_argument("--badge", help="short text for an 80x80 manufacturer badge, e.g. TRD")
    ap.add_argument("--category", choices=sorted(CATEGORY_GLYPH), default="scout",
                    help="vehicle class, which picks the SHARED fleet-tab glyph "
                         "(UiIcon40x40/30x30). These are never per-vehicle: a "
                         "per-vehicle image there renders as an empty tab.")
    a = ap.parse_args()

    from PIL import Image
    im = Image.open(a.shot).convert("RGB")
    cut_src = paint_out(im, [tuple(r) for r in a.exclude]) if a.exclude else im
    safe = tuple(a.safe) if a.safe else (0, 0, im.width, im.height)
    members = read_pak(a.pak)
    cls = truck_class(members)
    if not cls:
        raise SystemExit("no classes/trucks/*.xml in that pak")

    frame = vehicle_bbox(cut_src, tuple(a.box))
    print(f"vehicle found at {frame} (box given: {tuple(a.box)})")

    made = []
    for field, tmpl, w, h, bw in SLOTS:
        fname = tmpl.format(n=a.name) + ".png"
        buf = io.BytesIO()
        render(im, frame, safe, w, h, bw).save(buf, "PNG")
        members[f"ui/textures/{fname}"] = buf.getvalue()
        made.append(f"{fname:<26} {w}x{h}")
    for field, tmpl, w, h, fill in CUTOUTS:
        fname = tmpl.format(n=a.name) + ".png"
        buf = io.BytesIO()
        img = cutout(cut_src, tuple(a.box), w, h, fill)
        img.save(buf, "PNG")
        members[f"ui/textures/{fname}"] = buf.getvalue()
        lo, hi = img.getchannel("A").getextrema()
        made.append(f"{fname:<26} {w}x{h}  fill {fill}x  RGBA alpha {lo}-{hi}")
    if a.badge:
        buf = io.BytesIO()
        badge(a.badge).save(buf, "PNG")
        members[f"ui/textures/{a.name}Logo80.png"] = buf.getvalue()
        made.append(f"{a.name + 'Logo80.png':<26} 80x80   badge {a.badge!r}")

    xml, notes = patch_fields(members[cls].decode("utf-8", "replace"), a.name,
                              bool(a.badge), a.category)
    members[cls] = xml.encode("utf-8")

    # a previous build shipped per-vehicle glyphs; they are inert now, drop them
    for dead in (f"ui/textures/{a.name}VehicleImg.png",
                 f"ui/textures/{a.name}VehicleImg30.png"):
        if members.pop(dead, None) is not None:
            made.append(f"{dead.rsplit('/', 1)[-1]:<26} REMOVED (fleet tab uses the "
                        f"shared {CATEGORY_GLYPH[a.category][0]})")

    write_pak(a.out, members)
    print("images written:")
    for m in made:
        print("   " + m)
    print("class fields repointed:")
    for n in notes:
        print("   " + n)
    print(f"entries {validate_pak(a.out)}  ->  {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
