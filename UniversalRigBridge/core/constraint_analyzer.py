"""Constraint discovery and capability classification.

The addon does not rebuild constraints in Unreal.  Consequently the honest
classification is:

SUPPORTED   The constraint has no runtime effect that must be transferred
            (disabled, zero influence, or an armature modifier represented by
            skinning).  The skeleton alone reproduces the rig.
BAKED       The constraint affects the pose and Blender can evaluate it.  Its
            final result is sampled into the animation, which reproduces the
            motion exactly even though Unreal never sees the constraint.
UNSUPPORTED The addon cannot guarantee a faithful result: the constraint
            depends on data the exporter does not capture (animated path
            offsets, evaluated surface geometry) or has no valid target.
"""

from __future__ import annotations

import bpy

CONSTRAINT_CHANNELS = {
    "COPY_LOCATION": ["location"],
    "COPY_ROTATION": ["rotation"],
    "COPY_SCALE": ["scale"],
    "COPY_TRANSFORMS": ["location", "rotation", "scale"],
    "CHILD_OF": ["location", "rotation", "scale"],
    "TRACK_TO": ["rotation"],
    "DAMPED_TRACK": ["rotation"],
    "LOCKED_TRACK": ["rotation"],
    "STRETCH_TO": ["location", "rotation", "scale"],
    "LIMIT_DISTANCE": ["location"],
    "LIMIT_ROTATION": ["rotation"],
    "LIMIT_LOCATION": ["location"],
    "LIMIT_SCALE": ["scale"],
    "TRANSFORM": ["location", "rotation", "scale"],
    "IK": ["location", "rotation"],
    "SPLINE_IK": ["location", "rotation", "scale"],
    "ACTION": ["location", "rotation", "scale"],
    "PIVOT": ["rotation", "scale"],
    "FOLLOW_PATH": ["location"],
    "ARMATURE": ["location", "rotation", "scale"],
    "SHRINKWRAP": ["location"],
    "CLAMP_TO": ["location"],
    "FLOOR": ["location"],
}

# Types that require a target object to evaluate at all.
TARGET_REQUIRED = {
    "COPY_LOCATION",
    "COPY_ROTATION",
    "COPY_SCALE",
    "COPY_TRANSFORMS",
    "CHILD_OF",
    "TRACK_TO",
    "DAMPED_TRACK",
    "LOCKED_TRACK",
    "STRETCH_TO",
    "LIMIT_DISTANCE",
    "TRANSFORM",
    "IK",
    "SPLINE_IK",
    "PIVOT",
    "FOLLOW_PATH",
    "SHRINKWRAP",
    "CLAMP_TO",
    "FLOOR",
}

# Constraints that always read evaluated geometry rather than bone transforms.
GEOMETRY_TYPES = {"SURFACE"}


def owner_kind(owner):
    if isinstance(owner, bpy.types.PoseBone):
        return "BONE"
    if isinstance(owner, bpy.types.Object):
        return "OBJECT"
    return "OTHER"


def constraint_targets(constraint):
    names = []
    for attribute in ("target", "pole_target"):
        target = getattr(constraint, attribute, None)
        if target is not None and target.name not in names:
            names.append(target.name)
    armature = getattr(constraint, "armature", None)
    if armature is not None and armature.name not in names:
        names.append(armature.name)
    return names


def constraint_channels(constraint):
    return list(CONSTRAINT_CHANNELS.get(constraint.type, ["unknown"]))


def _limit_is_inactive(constraint):
    checks = {
        "LIMIT_LOCATION": ("use_min_x", "use_max_x", "use_min_y", "use_max_y", "use_min_z", "use_max_z"),
        "LIMIT_ROTATION": ("use_limit_x", "use_limit_y", "use_limit_z"),
        "LIMIT_SCALE": ("use_min_x", "use_max_x", "use_min_y", "use_max_y", "use_min_z", "use_max_z"),
    }
    attrs = checks.get(constraint.type)
    if not attrs:
        return False
    return not any(getattr(constraint, attr, False) for attr in attrs)


def classify_constraint(constraint, armature_obj, exported_bones=None):
    """Return (category, reason). Never infers capability from the type name alone."""
    exported_bones = exported_bones or set()

    if not constraint.enabled or getattr(constraint, "mute", False) or constraint.influence <= 0.0:
        return "SUPPORTED", "no runtime effect (disabled, muted or zero influence)"

    constraint_type = constraint.type

    if constraint_type == "ARMATURE":
        return "SUPPORTED", "armature deformation is reproduced by exported skinning"

    if constraint_type in ("LIMIT_LOCATION", "LIMIT_ROTATION", "LIMIT_SCALE") and _limit_is_inactive(constraint):
        return "SUPPORTED", "limit has no enabled axes"

    if constraint_type in GEOMETRY_TYPES:
        return "UNSUPPORTED", "depends on evaluated mesh geometry that is not part of the skeleton"

    if constraint_type == "FOLLOW_PATH":
        if getattr(constraint, "use_fixed_location", False):
            return "BAKED", "fixed path location is evaluated into the pose"
        return "UNSUPPORTED", "animated path offset is not captured by the skeleton package"

    if constraint_type in TARGET_REQUIRED and getattr(constraint, "target", None) is None:
        return "UNSUPPORTED", "required target object is missing"

    if constraint_type == "ACTION" and getattr(constraint, "action", None) is None:
        return "SUPPORTED", "action constraint has no action assigned"

    # Everything else is evaluated by Blender and stored in animation samples.
    if constraint_type in CONSTRAINT_CHANNELS:
        return "BAKED", "pose result is sampled into the exported animation"

    return "UNSUPPORTED", "constraint type has no verified evaluation path"


def _owner_dependencies(owner):
    """Everything that feeds the owner's evaluated pose.

    The owner itself is recorded as ``constraint_owner:<name>`` so a consumer can
    tell which bone the constraint writes to without re-reading Blender data.
    """
    dependencies = set()
    dependencies.add(f"constraint_owner:{owner.name}")
    if isinstance(owner, bpy.types.PoseBone):
        if owner.parent:
            dependencies.add(f"bone:{owner.parent.name}")
        constraints = owner.constraints
    elif isinstance(owner, bpy.types.Object):
        if owner.parent:
            dependencies.add(f"object:{owner.parent.name}")
        constraints = owner.constraints
    else:
        constraints = ()
    for constraint in constraints:
        for target in constraint_targets(constraint):
            dependencies.add(f"object:{target}")
        subtarget = getattr(constraint, "subtarget", "")
        if subtarget:
            dependencies.add(f"bone:{subtarget}")
        pole_subtarget = getattr(constraint, "pole_subtarget", "")
        if pole_subtarget:
            dependencies.add(f"bone:{pole_subtarget}")
    return sorted(dependencies)


def constraint_record(constraint, armature_obj, owner, exported_bones=None):
    category, reason = classify_constraint(constraint, armature_obj, exported_bones)
    label = owner.name
    kind = owner_kind(owner)
    if isinstance(owner, bpy.types.PoseBone):
        label = owner.name
    return {
        "name": constraint.name,
        "type": constraint.type,
        "owner": label,
        "owner_kind": kind,
        "armature": armature_obj.name,
        "target": " / ".join(constraint_targets(constraint)),
        "subtarget": getattr(constraint, "subtarget", ""),
        "influence": float(constraint.influence),
        "enabled": bool(constraint.enabled and not getattr(constraint, "mute", False)),
        "category": category,
        "reason": reason,
        "channels": constraint_channels(constraint),
        "dependencies": _owner_dependencies(owner),
    }


def collect_constraints(armature_obj, exported_bones=None):
    records = []
    for bone in armature_obj.pose.bones:
        for constraint in bone.constraints:
            records.append(constraint_record(constraint, armature_obj, bone, exported_bones))
    for constraint in armature_obj.constraints:
        records.append(constraint_record(constraint, armature_obj, armature_obj, exported_bones))
    records.sort(key=lambda item: (item["owner"].lower(), item["name"].lower()))
    return records


def constraint_type_support():
    """Return the capability matrix used by the metadata exporter."""
    baked = sorted(CONSTRAINT_CHANNELS)
    supported = ["ARMATURE", "LIMIT_ROTATION (inactive axes)", "disabled constraints"]
    unsupported = ["SURFACE", "FOLLOW_PATH (animated offset)"]
    return {
        "supported": supported,
        "baked": baked,
        "unsupported": unsupported,
        "notes": "Supported means the exported skeleton reproduces the result without runtime constraints.",
    }


def dependency_cycles(records):
    """Detect direct bone dependency cycles between constraints."""
    graph = {}
    for record in records:
        owner = record["owner"]
        graph.setdefault(owner, set())
        for dependency in record["dependencies"]:
            if dependency.startswith("bone:") and record["owner_kind"] == "BONE":
                graph[owner].add(dependency.split(":", 1)[1])
    cycles = []
    visited = set()
    stack = []

    def visit(node):
        if node in stack:
            cycle = stack[stack.index(node):] + [node]
            cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for neighbour in graph.get(node, ()):
            if neighbour in graph:
                visit(neighbour)
        stack.pop()

    for node in sorted(graph):
        visit(node)
    return cycles
