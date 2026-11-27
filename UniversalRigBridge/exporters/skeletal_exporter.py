"""Skeleton export: reference transforms and the exported hierarchy."""

from __future__ import annotations

from ..baking.animation_baker import exported_bone_order, reference_skeleton
from ..utils.coordinate_conversion import convert_matrix
from ..utils.matrix_utils import round_matrix


def bone_metadata_index(bones):
    return {bone["name"]: bone for bone in bones}


def skeleton_payload(armature_obj, bones_metadata, unit_scale=1.0, deform_only=True, classifications=None):
    """Build skeleton.json content for one armature."""
    classifications = classifications or {}
    order = exported_bone_order(armature_obj, deform_only=deform_only)
    ordered_set = set(order)
    references = {record["name"]: record for record in reference_skeleton(armature_obj, order, unit_scale)}
    records = []
    for index, name in enumerate(order):
        bone = armature_obj.data.bones.get(name)
        reference = references[name]
        metadata = bones_metadata.get(name, {})
        classification = classifications.get(name) or metadata.get("auto_type") or "UNKNOWN"
        parent = reference["parent"]

        # Local rest transform relative to the nearest exported ancestor.
        ancestor = bone.parent
        while ancestor is not None and ancestor.name not in ordered_set:
            ancestor = ancestor.parent
        if ancestor is not None:
            local_rest = ancestor.matrix_local.inverted() @ bone.matrix_local
        else:
            local_rest = bone.matrix_local.copy()
        records.append(
            {
                "name": name,
                "parent": parent,
                "bone_type": classification,
                "use_deform": bool(bone.use_deform),
                "connected": bool(bone.use_connect),
                "inherit_scale": bone.inherit_scale,
                "hierarchy_index": index,
                "depth": _depth(bone),
                "reference_transform": round_matrix(reference["reference_local"]),
                "rest_local": round_matrix(convert_matrix(local_rest, unit_scale)),
                "rest_world": round_matrix(reference["world"]),
                "head": [round(value, 7) for value in bone.head_local],
                "tail": [round(value, 7) for value in bone.tail_local],
                "length": round(float(bone.length), 7),
                "roll": round(_bone_roll(bone), 7),
                "collections": metadata.get("collections", []),
                "classification_reason": metadata.get("classification_reason", ""),
            }
        )
    return {
        "armature": armature_obj.name,
        "armature_data": armature_obj.data.name if armature_obj.data else "",
        "bone_count": len(records),
        "deform_only": deform_only,
        "object_matrix": round_matrix(convert_matrix(armature_obj.matrix_world.copy(), unit_scale)),
        "bones": records,
    }


def _depth(bone):
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _bone_roll(bone):
    try:
        import bpy
        _axis, roll = bpy.types.Bone.AxisRollFromMatrix(bone.matrix_local.to_3x3())
        return float(roll)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def skeletons_payload(armatures, analysis, settings):
    """Skeleton payloads for every exported armature."""
    metadata_index = {}
    for bone in analysis["bones"]:
        metadata_index.setdefault(bone["armature"], {})[bone["name"]] = bone
    classifications = {}
    for item in settings.bones:
        classifications.setdefault(item.armature, {})[item.name] = item.bone_type
    unit_scale = _unit_scale(settings)
    skeletons = []
    for armature_obj in armatures:
        skeletons.append(
            skeleton_payload(
                armature_obj,
                metadata_index.get(armature_obj.name, {}),
                unit_scale=unit_scale,
                deform_only=settings.export.export_deform_only,
                classifications=classifications.get(armature_obj.name, {}),
            )
        )
    return {"skeletons": skeletons}


def _unit_scale(settings):
    from ..utils.coordinate_conversion import unit_scale_from_scene
    import bpy
    project = settings.project
    if project.coordinate_system == "BLENDER":
        return 1.0
    return unit_scale_from_scene(bpy.context.scene, project.auto_unit_scale, project.unit_scale)
