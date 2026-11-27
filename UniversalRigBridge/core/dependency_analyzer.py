"""Discovery of drivers on armatures, pose bones and associated objects."""

from __future__ import annotations

import bpy


def _iter_anim_data(id_block):
    animation_data = getattr(id_block, "animation_data", None)
    if animation_data is None:
        return []
    return list(animation_data.drivers)


def _iter_collections(id_block):
    """Yield (data_path, index, fcurve) for drivers on common collections."""
    results = []
    for driver in _iter_anim_data(id_block):
        results.append((driver.data_path, driver.array_index, driver))
    return results


def driver_record(id_block, owner_label, owner_kind, fcurve):
    driver = fcurve.driver
    variables = []
    for variable in driver.variables:
        variable_targets = []
        for target in variable.targets:
            variable_targets.append(
                {
                    "id_type": target.id_type,
                    "id": target.id.name if target.id else "",
                    "bone_target": getattr(target, "bone_target", ""),
                    "data_path": target.data_path,
                    "transform_type": getattr(target, "transform_type", ""),
                    "transform_space": getattr(target, "transform_space", ""),
                }
            )
        variables.append({"name": variable.name, "type": variable.type, "targets": variable_targets})
    return {
        "owner": owner_label,
        "owner_kind": owner_kind,
        "data_path": fcurve.data_path,
        "array_index": fcurve.array_index,
        "expression": driver.expression,
        "type": driver.type,
        "is_valid": bool(driver.is_valid),
        "is_simple_expression": bool(getattr(driver, "is_simple_expression", False)),
        "variables": variables,
        "has_python_expression": any(token in driver.expression for token in ("import ", "__", "exec(", "eval(")),
    }


def collect_drivers(armature_obj, extra_objects=()):
    records = []
    for fcurve in _iter_anim_data(armature_obj):
        records.append(driver_record(armature_obj, armature_obj.name, "OBJECT", fcurve))
    if armature_obj.data is not None:
        for fcurve in _iter_anim_data(armature_obj.data):
            records.append(driver_record(armature_obj.data, armature_obj.data.name, "ARMATURE_DATA", fcurve))
    for bone in armature_obj.pose.bones:
        for fcurve in _iter_anim_data(bone):
            records.append(driver_record(bone, bone.name, "BONE", fcurve))
    for obj in extra_objects:
        for fcurve in _iter_anim_data(obj):
            records.append(driver_record(obj, obj.name, "OBJECT", fcurve))
    records.sort(key=lambda item: (item["owner"].lower(), item["data_path"], item["array_index"]))
    return records


def driver_summary(records):
    invalid = sum(1 for record in records if not record["is_valid"])
    python = sum(1 for record in records if record["has_python_expression"])
    return {
        "count": len(records),
        "invalid": invalid,
        "python_expressions": python,
        "records": records,
    }
