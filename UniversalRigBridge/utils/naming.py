"""Naming helpers for Unreal-friendly identifiers."""

from __future__ import annotations

import re

_INVALID = re.compile(r"[^A-Za-z0-9_]+")
_MULTI = re.compile(r"_+")


def sanitize(value, fallback="Asset"):
    """Convert a Blender name into a stable Unreal-friendly identifier."""
    if not value:
        return fallback
    text = _INVALID.sub("_", str(value)).strip("_")
    text = _MULTI.sub("_", text)
    if not text:
        return fallback
    if text[0].isdigit():
        text = "N_" + text
    return text


def sanitize_animation(value, fallback="Anim"):
    return sanitize(value, fallback)


def unique_name(base, used):
    """Return base, base_1, base_2... guaranteed unused in the set."""
    candidate = base
    index = 1
    while candidate in used:
        candidate = f"{base}_{index:02d}"
        index += 1
    used.add(candidate)
    return candidate


def side_from_name(name):
    lowered = name.lower()
    if lowered.endswith(("_l", ".l", "_left")) or lowered.startswith(("l_", "left_")):
        return "L"
    if lowered.endswith(("_r", ".r", "_right")) or lowered.startswith(("r_", "right_")):
        return "R"
    return ""


def strip_side(name):
    side = side_from_name(name)
    if not side:
        return name
    for suffix in ("_left", "_right", ".l", ".r", "_l", "_r"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    for prefix in ("left_", "right_", "l_", "r_"):
        if name.lower().startswith(prefix):
            return name[len(prefix):]
    return name
