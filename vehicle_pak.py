#!/usr/bin/env python3
"""Reading and writing Expeditions vehicle .pak files, and the mesh container.

A .pak is a plain zip. A compiled mesh inside it is [u32 xmlLen][xml][geometry],
where the XML is plain text you can edit and the geometry is opaque. Everything
here is shared by the vehicle tools; it is deliberately the only place that
knows those two formats.
"""

from __future__ import annotations

import os
import re
import struct
import zipfile

GEOMETRY_MAGIC = bytes.fromhex("63ef3301")


def read_pak(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def write_pak(path: str, members: dict[str, bytes]) -> None:
    """Write a .pak with NO extra fields.

    zipfile copies ZipInfo.extra into the local header as well as the central
    directory, and the engine then fails to read that member. Fresh ZipInfo
    objects only -- this is the single most expensive mistake in pak surgery.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            z.writestr(zi, data)


def validate_pak(path: str) -> int:
    """Inflate every member. Returns the count; raises if any member is bad."""
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"corrupt member in {path}: {bad}")
        return len(z.namelist())


# ----------------------------------------------------------- mesh container

def split_mesh(blob: bytes) -> tuple[str, bytes]:
    """[u32 len][xml][geometry] -> (xml, geometry)"""
    n = struct.unpack_from("<I", blob, 0)[0]
    return blob[4:4 + n].decode("utf-8", "replace"), blob[4 + n:]


def join_mesh(xml: str, geometry: bytes) -> bytes:
    xb = xml.encode("utf-8")
    return struct.pack("<I", len(xb)) + xb + geometry


def is_mesh(name: str) -> bool:
    return name.startswith("prebuild/meshes/")


def balanced_tags(xml: str) -> bool:
    """Minimal well-formedness: every element closes, in order.

    Do NOT test with `xml.strip().endswith('</CombineXMesh>')` -- these end with
    a trailing NUL that strip() leaves in place, so that check fails on files the
    game ships and happily loads.
    """
    stack: list[str] = []
    for m in re.finditer(r"<(/?)([A-Za-z_][\w.-]*)([^>]*?)>", xml):
        close, tag, attrs = m.group(1), m.group(2), m.group(3)
        if attrs.rstrip().endswith("/"):
            continue
        if close:
            if not stack or stack.pop() != tag:
                return False
        else:
            stack.append(tag)
    return not stack


def check_meshes(new: dict[str, bytes], original: dict[str, bytes]) -> list[str]:
    """Every mesh must keep byte-identical geometry, its magic, and valid XML."""
    problems = []
    for name, blob in new.items():
        if not is_mesh(name):
            continue
        xml, geo = split_mesh(blob)
        if not geo.startswith(GEOMETRY_MAGIC):
            problems.append(f"{name}: geometry magic lost")
        if not balanced_tags(xml):
            problems.append(f"{name}: XML tags do not balance")
        if name in original:
            _, old_geo = split_mesh(original[name])
            if geo != old_geo:
                problems.append(f"{name}: geometry changed")
    return problems


# ------------------------------------------------------------------ TGA I/O

def write_tga(path: str, image, alpha_from_image: bool = False) -> None:
    """Uncompressed TGA with the 26-byte footer the converter expects.

    24-bit unless alpha_from_image, which the __d_a postfix calls for. Writing
    32-bit where the engine wants 24 wastes memory on every mip level.

    🚨 ROWS ARE WRITTEN BOTTOM-UP. The descriptor's origin bit (0x20) is clear,
    which means row 0 of the file is the BOTTOM row of the image -- that is what
    the game's own .tga files do, verified against the .dds the game converted
    from one (MAE 0.3 flipped vs 52.4 as-stored).

    Emitting rows top-down instead produces a vertically flipped texture. That
    is INVISIBLE on a flat colour or a tiled pattern and completely scrambles a
    real UV atlas, so it will pass every test you throw at a generated skin and
    then wreck the first vehicle that has genuine artwork.
    """
    from PIL import Image as _Image
    image = image.transpose(_Image.FLIP_TOP_BOTTOM)
    if alpha_from_image:
        image = image.convert("RGBA")
        px_size, depth, descriptor = 4, 32, 0x08
    else:
        image = image.convert("RGB")
        px_size, depth, descriptor = 3, 24, 0x00
    w, h = image.size
    hdr = bytearray(18)
    hdr[2] = 2                                   # uncompressed true-colour
    struct.pack_into("<HH", hdr, 12, w, h)
    hdr[16] = depth
    hdr[17] = descriptor
    # bytes() of the raw image is far faster than a per-pixel loop on a 2048^2
    raw = image.tobytes()
    body = bytearray(len(raw))
    body[0::px_size] = raw[2::px_size]           # B <- R
    body[1::px_size] = raw[1::px_size]           # G
    body[2::px_size] = raw[0::px_size]           # R <- B
    if px_size == 4:
        body[3::px_size] = raw[3::px_size]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "wb") as f:
        # footer: u32 extension offset, u32 developer offset, then the signature
        f.write(bytes(hdr) + bytes(body) + b"\0" * 8 + b"TRUEVISION-XFILE.\0")


def truck_class(members: dict[str, bytes]) -> str | None:
    for name in members:
        if re.match(r"classes/trucks/[^/]+\.xml$", name):
            return name
    return None
