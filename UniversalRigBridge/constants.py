"""Shared constants and small helpers for Universal Rig Bridge."""

from __future__ import annotations

PROJECT_VERSION = "1.0.0"
PACKAGE_FORMAT = "UniversalRigPackage"
PACKAGE_SCHEMA_VERSION = 1
ANIMATION_FORMAT = "URB-ANIM"
ANIMATION_VERSION = 1

UNREAL_VERSIONS = (
    ("5.8", "Unreal Engine 5.8", "Primary target"),
    ("5.7", "Unreal Engine 5.7", ""),
    ("5.6", "Unreal Engine 5.6", ""),
    ("5.5", "Unreal Engine 5.5", ""),
    ("5.4", "Unreal Engine 5.4", ""),
)

EXPORT_FORMATS = (
    ("URB", "URB Package (.urb)", "Compressed exchange package with metadata and binary animation"),
    ("JSON", "JSON Only (.json)", "Human readable skeleton and animation data"),
    ("FOLDER", "Uncompressed Folder", "URB package tree written to disk"),
)

COORDINATE_SYSTEMS = (
    ("UNREAL", "Unreal Compatible", "Blender Z-up metres to Unreal Z-up centimetres"),
    ("BLENDER", "Blender Native", "Keep Blender axes and units"),
)

SAMPLE_MODES = (
    ("EVERY_FRAME", "Every Frame", "Sample every scene frame (most accurate)"),
    ("CUSTOM_FPS", "Custom FPS", "Resample at a fixed rate"),
    ("CUSTOM_INTERVAL", "Frame Interval", "Sample every Nth frame"),
    ("ADAPTIVE", "Adaptive", "Keep only keys needed to stay within tolerance"),
)

BONE_TYPES = (
    ("ROOT", "Root", "Skeleton root / motion bone"),
    ("DEFORM", "Deform", "Skinning bone"),
    ("CONTROL", "Control", "Rig manipulation bone"),
    ("MECHANISM", "Mechanism", "Intermediate rig calculation bone"),
    ("HELPER", "Helper", "Secondary or technical bone"),
    ("UNKNOWN", "Unknown", "Function could not be determined"),
)

ANIMATION_SOURCES = (
    ("ACTION", "Action", "Action clip"),
    ("NLA", "NLA Strip", "NLA strip"),
    ("SCENE", "Scene Range", "Scene frame range"),
)

CONSTRAINT_CATEGORIES = (
    ("SUPPORTED", "Supported", "Result is reproduced by the skeleton"),
    ("BAKED", "Baked", "Result is evaluated into animation samples"),
    ("UNSUPPORTED", "Unsupported", "Result cannot be guaranteed"),
)

# Unreal skeletons do not normally exceed four influences per vertex by default.
DEFAULT_MAX_INFLUENCES = 4


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
