"""Per-bone inspection and evidence-based classification."""

from __future__ import annotations

import bpy
from mathutils import Matrix

from ..utils.naming import side_from_name, strip_side

# These suffixes are hints only; classification always uses structural evidence.
_CONTROL_HINTS = ("ctrl", "control", "ik", "fk", "pole", "target", "tgt", "master")
_MECHANISM_HINTS = ("mch", "mech", "mechanism", "driver", "drv", "twist", "roll", "corrective")
_HELPER_HINTS = ("helper", "hook", "offset", "buffer", "attach", "socket", "prop", "jnt")


def _name_tokens(name):
    import re
    return set(token for token in re.split(r"[^a-z0-9]+", name.lower()) if token)


def _name_hint(name):
    tokens = _name_tokens(name)
    lowered = name.lower()
    for token in _CONTROL_HINTS:
        if token in tokens or lowered.endswith(token):
            return "CONTROL"
    for token in _MECHANISM_HINTS:
        if token in tokens:
            return "MECHANISM"
    for token in _HELPER_HINTS:
        if token in tokens:
            return "HELPER"
    return ""


def bone_has_constant_influence(armature_obj, bone_name, cache=None):
    if cache is not None and bone_name in cache:
        return cache[bone_name]
    result = False
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        modifier = None
        for candidate in obj.modifiers:
            if candidate.type == "ARMATURE" and candidate.object == armature_obj:
                modifier = candidate
                break
        if modifier is None:
            continue
        group = obj.vertex_groups.get(bone_name)
        if group is None:
            continue
        for vertex in obj.data.vertices:
            for membership in vertex.groups:
                if membership.group == group.index and membership.weight > 0.0:
                    result = True
                    break
            if result:
                break
        if result:
            break
    if cache is not None:
        cache[bone_name] = result
    return result


def weighted_bone_names(armature_obj, meshes=None):
    """Collect bone names that actually carry non-zero weights (single pass)."""
    names = set()
    meshes = meshes if meshes is not None else [obj for obj in bpy.data.objects if obj.type == "MESH"]
    for obj in meshes:
        modifier = None
        for candidate in obj.modifiers:
            if candidate.type == "ARMATURE" and candidate.object == armature_obj:
                modifier = candidate
                break
        if modifier is None:
            continue
        index_to_name = {group.index: group.name for group in obj.vertex_groups}
        bone_names = {bone.name for bone in armature_obj.data.bones}
        for vertex in obj.data.vertices:
            for membership in vertex.groups:
                if membership.weight > 0.0:
                    name = index_to_name.get(membership.group)
                    if name in bone_names:
                        names.add(name)
    return names


def bone_collections(bone):
    try:
        return [collection.name for collection in bone.collections]
    except AttributeError:
        return []


def bone_children(bone):
    return sorted((child.name for child in bone.children), key=str.lower)


def classify_bone(armature_obj, bone, child_constraint_index=None, weighted_names=None, referenced_bones=None):
    """Classify a bone from deformation, use, hierarchy and constraint evidence."""
    if armature_obj.data is None:
        return "UNKNOWN", "armature has no data"

    children = list(bone.children)
    deform = bool(bone.use_deform)
    is_root = bone.parent is None
    constraints = []
    if armature_obj.pose and bone.name in armature_obj.pose.bones:
        constraints = list(armature_obj.pose.bones[bone.name].constraints)
    constrained = len(constraints) > 0
    referenced = bool(referenced_bones and bone.name in referenced_bones)
    hint = _name_hint(bone.name)

    if deform and not is_root:
        return "DEFORM", "deform enabled and parented"

    if is_root and not deform:
        return "ROOT", "top-level non-deforming bone"

    if is_root and deform:
        if len(children) > 0:
            return "ROOT", "top-level deform bone with children"
        return "DEFORM", "standalone deform bone"

    if deform:
        return "DEFORM", "deform enabled"

    if weighted_names is not None:
        has_skinned_influence = bone.name in weighted_names
    else:
        has_skinned_influence = bone_has_constant_influence(armature_obj, bone.name)
    if has_skinned_influence:
        return "DEFORM", "vertex group weights reference this bone"

    if constrained:
        return "CONTROL", "bone owns constraints that drive the rig"
    if referenced:
        return "CONTROL", "bone is a target of another bone's constraint"

    child_bones = [child for child in children]
    if any(child.use_deform for child in child_bones):
        if hint == "MECHANISM":
            return "MECHANISM", "non-deforming parent of deform bones with mechanism role"
        return "CONTROL", "non-deforming parent of deform bones"

    if hint == "MECHANISM":
        return "MECHANISM", "non-deforming intermediary identified by naming convention"
    if hint == "HELPER":
        return "HELPER", "non-deforming technical bone identified by naming convention"

    if len(children) == 0:
        return "UNKNOWN", "unused leaf bone without deformation or constraint use"

    return "UNKNOWN", "no conclusive structural evidence"


def bone_roll(bone):
    """Bone roll in radians (Bone has no roll attribute in the data API)."""
    try:
        _axis, roll = bpy.types.Bone.AxisRollFromMatrix(bone.matrix_local.to_3x3())
        return float(roll)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def bone_record(armature_obj, bone, depth=0, weighted_names=None, referenced_bones=None):
    pose_bone = armature_obj.pose.bones.get(bone.name) if armature_obj.pose else None
    auto_type, reason = classify_bone(
        armature_obj, bone, weighted_names=weighted_names, referenced_bones=referenced_bones
    )
    pose_matrix = pose_bone.matrix.copy() if pose_bone else Matrix.Identity(4)
    rest_matrix = bone.matrix_local.copy()
    local_matrix = bone.matrix_local.copy()
    if bone.parent is not None:
        local_matrix = (bone.parent.matrix_local.inverted() @ bone.matrix_local)

    collections = bone_collections(bone)
    return {
        "name": bone.name,
        "armature": armature_obj.name,
        "parent": bone.parent.name if bone.parent else "",
        "children": bone_children(bone),
        "auto_type": auto_type,
        "classification_reason": reason,
        "use_deform": bool(bone.use_deform),
        "connected": bool(bone.use_connect),
        "inherit_scale": bone.inherit_scale,
        "inherit_rotation": bool(bone.use_inherit_rotation),
        "depth": depth,
        "collections": collections,
        "head": list(bone.head_local),
        "tail": list(bone.tail_local),
        "length": float(bone.length),
        "roll": bone_roll(bone),
        "rest_matrix": [list(row) for row in bone.matrix_local],
        "local_matrix": [list(row) for row in local_matrix],
        "pose_matrix": [list(row) for row in pose_matrix],
        "matrix_basis": [list(row) for row in pose_bone.matrix_basis] if pose_bone else None,
        "rotation_mode": pose_bone.rotation_mode if pose_bone else "QUATERNION",
        "local_location": list(pose_bone.location) if pose_bone else [0.0, 0.0, 0.0],
        "local_rotation_quaternion": list(pose_bone.rotation_quaternion) if pose_bone else [1.0, 0.0, 0.0, 0.0],
        "local_scale": list(pose_bone.scale) if pose_bone else [1.0, 1.0, 1.0],
        "side": side_from_name(bone.name),
        "base_name": strip_side(bone.name),
        "constraint_count": len(pose_bone.constraints) if pose_bone else 0,
    }


def walk_bones(armature_obj):
    """Depth-first walk returning (bone, depth, order_index)."""
    if armature_obj.data is None:
        return []
    roots = [bone for bone in armature_obj.data.bones if bone.parent is None]
    roots.sort(key=lambda item: item.name.lower())
    result = []

    def visit(bone, depth):
        result.append((bone, depth, len(result)))
        for child in sorted(bone.children, key=lambda item: item.name.lower()):
            visit(child, depth + 1)

    for root in roots:
        visit(root, 0)
    return result


def hierarchy_index(armature_obj):
    return {bone.name: index for bone, _depth, index in walk_bones(armature_obj)}
