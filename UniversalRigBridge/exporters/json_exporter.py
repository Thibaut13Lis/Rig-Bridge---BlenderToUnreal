"""JSON sidecars and a single-file JSON representation of the package."""

from __future__ import annotations

import json
import os

from ..utils.file_utils import ensure_directory, write_json
from .binary_exporter import decode_animation


def write_json_animations(staging_directory, clips):
    """Write a readable animation summary next to the binary clips."""
    directory = ensure_directory(os.path.join(staging_directory, "animations"))
    summary = []
    for clip in clips:
        summary.append(
            {
                "name": clip["name"],
                "fps": clip["fps"],
                "start_frame": clip["start_frame"],
                "end_frame": clip["end_frame"],
                "sample_count": clip["sample_count"],
                "timestamps": clip["timestamps"],
                "source_frames": clip["source_frames"],
                "bone_order": clip["bone_order"],
                "root_motion_bone": clip["root_motion"]["bone"],
                "looping": clip.get("looping", False),
                "reconstruction": clip.get("reconstruction", {}),
            }
        )
    write_json(os.path.join(directory, "animations_index.json"), {"animations": summary})
    return summary


def read_package_json(staging_directory):
    """Read all JSON documents from a staging folder (used by tests/tools)."""
    payload = {}
    for root, _directories, files in os.walk(staging_directory):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            full = os.path.join(root, filename)
            relative = os.path.relpath(full, staging_directory).replace(os.sep, "/")
            with open(full, "r", encoding="utf-8") as handle:
                payload[relative] = json.load(handle)
    return payload


def write_single_json(staging_directory, destination):
    """Bundle every JSON document plus decoded animation headers into one file."""
    payload = {"documents": read_package_json(staging_directory), "animations": []}
    animation_directory = os.path.join(staging_directory, "animations")
    if os.path.isdir(animation_directory):
        for filename in sorted(os.listdir(animation_directory)):
            if not filename.endswith(".urbanim"):
                continue
            with open(os.path.join(animation_directory, filename), "rb") as handle:
                decoded = decode_animation(handle.read())
            payload["animations"].append(
                {
                    "file": filename,
                    "header": decoded["header"],
                    "bones": decoded["bones"],
                    "samples": decoded["samples"],
                    "root_motion": decoded["root_motion"],
                }
            )
    ensure_directory(os.path.dirname(destination))
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return destination
