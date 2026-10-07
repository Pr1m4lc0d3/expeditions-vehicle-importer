#!/usr/bin/env python3
"""Find the Expeditions and SnowRunner installs on this machine.

Every tool here needs one or both, and hard-coding them is what stops the
toolkit running anywhere but the machine it was written on. Resolution order:

  1. the environment variable, which always wins
  2. Steam's own library list, parsed from libraryfolders.vdf
  3. the usual places, across every fixed drive

A candidate is only accepted if a MARKER FILE is present, so a half-installed
or wrongly-named folder is rejected rather than silently used.

    from game_paths import expeditions_dir, snowrunner_dir, resource_converter

Each raises GameNotFound with the env var to set, rather than returning a path
that does not exist and failing somewhere less obvious later.
"""

from __future__ import annotations

import os
import re
import string

# marker -> proof the folder really is that game
EXPEDITIONS_MARKER = os.path.join("Sources", "Bin", "ResourceConverter.exe")
SNOWRUNNER_MARKER = os.path.join("en_us", "preload", "paks", "client", "initial.pak")

STEAM_NAMES = {
    "expeditions": ["Expeditions A MudRunner Game", "ExpeditionsAMudRunnerGame",
                    "Expeditions"],
    "snowrunner": ["SnowRunner"],
}


class GameNotFound(RuntimeError):
    pass


def _fixed_drives() -> list[str]:
    out = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(root):
            out.append(root)
    return out


def _steam_libraries() -> list[str]:
    """Every Steam library root, from libraryfolders.vdf."""
    libs, seen = [], set()
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, "Steam"))
    for d in _fixed_drives():
        candidates.append(os.path.join(d, "Steam"))
        candidates.append(os.path.join(d, "SteamLibrary"))

    for steam in candidates:
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if not os.path.isfile(vdf):
            continue
        try:
            text = open(vdf, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s*"([^"]+)"', text):
            p = m.group(1).replace("\\\\", "\\")
            if p.lower() not in seen:
                seen.add(p.lower())
                libs.append(p)
    return libs


def _search(marker: str, names: list[str], extra: list[str]) -> str | None:
    tried = []
    for lib in _steam_libraries():
        for n in names:
            tried.append(os.path.join(lib, "steamapps", "common", n))
    for d in _fixed_drives():
        for parent in ("Games", os.path.join("Program Files", "Epic Games"),
                       os.path.join("Program Files (x86)"), ""):
            for n in names:
                tried.append(os.path.join(d, parent, n) if parent
                             else os.path.join(d, n))
    tried.extend(extra)
    for cand in tried:
        if cand and os.path.isfile(os.path.join(cand, marker)):
            return os.path.abspath(cand)
    return None


def _resolve(env_var: str, marker: str, names: list[str], label: str,
             extra: list[str] | None = None) -> str:
    override = os.environ.get(env_var)
    if override:
        if not os.path.isfile(os.path.join(override, marker)):
            raise GameNotFound(
                f"{env_var} is set to {override!r} but {marker} is not there, so "
                f"that is not a {label} install.")
        return os.path.abspath(override)
    found = _search(marker, names, extra or [])
    if found:
        return found
    raise GameNotFound(
        f"could not find {label}. Set {env_var} to the folder containing "
        f"{marker}\n       e.g.  set {env_var}=D:\\Games\\{names[0]}")


def expeditions_dir() -> str:
    """Root of the Expeditions install (the folder holding Sources\\Bin)."""
    return _resolve("EXPEDITIONS_DIR", EXPEDITIONS_MARKER,
                    STEAM_NAMES["expeditions"], "Expeditions")


def snowrunner_dir() -> str:
    """Root of the SnowRunner install. Only needed when porting FROM it."""
    return _resolve("SNOWRUNNER_DIR", SNOWRUNNER_MARKER,
                    STEAM_NAMES["snowrunner"], "SnowRunner")


def resource_converter() -> str:
    """The game's own texture encoder. Nothing else can produce loadable .pct."""
    return os.path.join(expeditions_dir(), EXPEDITIONS_MARKER)


def snowrunner_initial_pak() -> str:
    """SnowRunner's class library, the donor for stock addon classes."""
    return os.path.join(snowrunner_dir(), SNOWRUNNER_MARKER)


def expeditions_initial_pak() -> str:
    return os.path.join(expeditions_dir(), "preload", "paks", "client", "initial.pak")


def user_dir() -> str:
    """Where the game keeps saves, logs, mods and crash dumps."""
    return os.path.join(os.path.expanduser("~"), "Documents", "My Games", "Expeditions")


if __name__ == "__main__":
    for label, fn in (("Expeditions", expeditions_dir),
                      ("SnowRunner", snowrunner_dir),
                      ("ResourceConverter", resource_converter),
                      ("user folder", user_dir)):
        try:
            print(f"{label:<18} {fn()}")
        except GameNotFound as exc:
            print(f"{label:<18} NOT FOUND -- {exc}")
