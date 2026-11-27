"""Armature discovery and hierarchy analysis."""

from __future__ import annotations

import bpy

from ..constants import BONE_TYPES


def bone_roll(bone):
    """Roll in radians from the bone's rest matrix (Bone has no roll attribute)."""
    try:
        _axis, roll = bpy.types.Bone.AxisRollFromMatrix(bone.matrix_local.to_3x3())
        return float(roll)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def iter_scene_objects(context):
    return list(context.scene.objects)


def is_armature(obj):
    return obj is not None and obj.type == "ARMATURE"


def is_selected_or_child(obj, selected):
    if obj in selected:
        return True
    parent = obj.parent
    while parent is not None:
        if parent in selected:
            return True
        parent = parent.parent
    return False


def collect_armatures(context, selected_only=False):
    """Return armature objects in deterministic name order."""
    selected = {obj for obj in context.selected_objects}
    armatures = []
    for obj in iter_scene_objects(context):
        if not is_armature(obj):
            continue
        if selected_only and not is_selected_or_child(obj, selected):
            continue
        armatures.append(obj)
    armatures.sort(key=lambda item: item.name.lower())
    return armatures


def associated_meshes(armature_obj):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        modifier = None
        for candidate in obj.modifiers:
            if candidate.type == "ARMATURE" and candidate.object == armature_obj:
                modifier = candidate
                break
        if modifier is not None:
            meshes.append(obj)
        elif obj.parent == armature_obj:
            meshes.append(obj)
    meshes.sort(key=lambda item: item.name.lower())
    return meshes


def armature_object_record(armature_obj):
    return {
        "name": armature_obj.name,
        "data_name": armature_obj.data.name if armature_obj.data else "",
        "matrix_world": [list(row) for row in armature_obj.matrix_world],
        "location": list(armature_obj.location),
        "rotation_mode": armature_obj.rotation_mode,
        "rotation_euler": list(armature_obj.rotation_euler),
        "rotation_quaternion": list(armature_obj.rotation_quaternion),
        "scale": list(armature_obj.scale),
        "pose_position": armature_obj.data.pose_position if armature_obj.data else "",
        "display_type": armature_obj.data.display_type if armature_obj.data else "",
        "hide_viewport": bool(armature_obj.hide_viewport),
        "hide_render": bool(armature_obj.hide_render),
        "selected": bool(armature_obj.select_get()),
    }


def armature_summary(armature_obj):
    meshes = associated_meshes(armature_obj)
    if armature_obj.data is None:
        return {
            "name": armature_obj.name,
            "data_name": "",
            "bone_count": 0,
            "mesh_count": len(meshes),
            "deform_count": 0,
            "action_hint": "",
        }
    data = armature_obj.data
    action = None
    if armature_obj.animation_data and armature_obj.animation_data.action:
        action = armature_obj.animation_data.action.name
    return {
        "name": armature_obj.name,
        "data_name": data.name,
        "bone_count": len(data.bones),
        "mesh_count": len(meshes),
        "deform_count": sum(1 for bone in data.bones if bone.use_deform),
        "action_hint": action or "",
    }


def bone_type_label(value):
    for key, label, _description in BONE_TYPES:
        if key == value:
            return label
    return value
