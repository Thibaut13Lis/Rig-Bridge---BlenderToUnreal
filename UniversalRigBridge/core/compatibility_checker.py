"""Cross-module compatibility checks and the final pre-export validation."""

from __future__ import annotations

import bpy

from ..utils.logging import Report
from .constraint_analyzer import dependency_cycles
from .mesh_analyzer import weight_report


def check_armature(armature_obj, report):
    if armature_obj.data is None:
        report.fail("Armature has no armature data", armature_obj.name)
        return False
    if len(armature_obj.data.bones) == 0:
        report.fail("Armature contains no bones", armature_obj.name)
        return False
    duplicate_bones = _duplicate_names(armature_obj)
    if duplicate_bones:
        report.fail(f"Duplicate bone names: {', '.join(duplicate_bones)}", armature_obj.name)
    if armature_obj.data.pose_position != "POSE":
        report.warn("Armature is in REST position; sampling will not see the rig result", armature_obj.name)
    root_bones = [bone for bone in armature_obj.data.bones if bone.parent is None]
    if len(root_bones) == 0:
        report.warn("No root bone found", armature_obj.name)
    elif len(root_bones) > 1:
        report.info(f"{len(root_bones)} root bones form independent chains", armature_obj.name)
    return True


def _duplicate_names(armature_obj):
    seen = set()
    duplicates = set()
    for bone in armature_obj.data.bones:
        if bone.name in seen:
            duplicates.add(bone.name)
        seen.add(bone.name)
    return sorted(duplicates)


def check_meshes(armature_obj, meshes, max_influences, report, check_weights=True):
    for obj in meshes:
        if obj.data is None:
            report.fail("Mesh has no data", obj.name)
            continue
        if len(obj.data.vertices) == 0:
            report.warn("Mesh has no vertices", obj.name)
        modifier = None
        for candidate in obj.modifiers:
            if candidate.type == "ARMATURE" and candidate.object == armature_obj:
                modifier = candidate
                break
        if modifier is None and obj.parent == armature_obj:
            report.warn("Mesh is parented but has no Armature modifier", obj.name)
        unsupported = sorted({modifier.type for modifier in obj.modifiers if modifier.type != "ARMATURE"})
        if unsupported:
            report.info(
                "Non-armature modifiers must be applied before export: " + ", ".join(unsupported),
                obj.name,
            )
        if not obj.vertex_groups:
            report.warn("Mesh has no vertex groups; it will not deform", obj.name)
        if check_weights:
            weights = weight_report(obj, armature_obj, max_influences)
            if weights["invalid_vertex_groups"]:
                report.warn(
                    "Vertex groups without matching bones: " + ", ".join(weights["invalid_vertex_groups"][:8]),
                    obj.name,
                )
            if weights["unweighted_vertices"]:
                report.warn(f"{weights['unweighted_vertices']} unweighted vertices", obj.name)
            if weights["vertices_over_influence_limit"]:
                report.warn(
                    f"{weights['vertices_over_influence_limit']} vertices exceed {max_influences} influences "
                    f"(maximum seen: {weights['max_influences_seen']})",
                    obj.name,
                )
            if weights["non_normalised_vertices"]:
                report.warn(f"{weights['non_normalised_vertices']} vertices have non-normalised weights", obj.name)
            if weights["invalid_weight_values"]:
                report.warn(f"{weights['invalid_weight_values']} vertices have weights outside 0..1", obj.name)


def check_constraints(records, report):
    unsupported = [record for record in records if record["category"] == "UNSUPPORTED"]
    baked = [record for record in records if record["category"] == "BAKED"]
    for record in unsupported:
        report.warn(f"Unsupported constraint {record['type']} ({record['name']}): {record['reason']}", record["owner"])
    for cycle in dependency_cycles(records):
        report.warn("Constraint dependency cycle: " + " -> ".join(cycle), "constraints")
    if baked:
        report.info(f"{len(baked)} constraints will be baked into animation samples")


def check_animation(records, report, armature_names):
    if not records:
        report.warn("No animation data detected in the scene")
        return
    for record in records:
        if record["end"] <= record["start"]:
            report.warn(f"Animation has an invalid range ({record['start']}..{record['end']})", record["name"])
        if record["source"] == "ACTION" and not record.get("armature"):
            # Actions are not armature bound; that is normal for the manager but
            # the target armature is chosen at export time.
            continue
    armatures_without_animation = [
        name for name in armature_names if not any(record.get("armature") == name for record in records)
    ]
    if armatures_without_animation:
        report.info("Armatures without a directly assigned animation: " + ", ".join(armatures_without_animation))


def check_drivers(records, report):
    for record in records:
        if not record["is_valid"]:
            report.warn(f"Invalid driver on {record['data_path']}", record["owner"])
        if record["has_python_expression"]:
            report.warn("Driver uses a Python expression; bake results instead of copying expressions", record["owner"])


def check_project(settings, report):
    project = settings.project
    if not project.project_name.strip():
        report.fail("Project name is empty")
    if not project.export_directory.strip():
        report.fail("Export directory is empty")
    if settings.export.export_animations and settings.samples.sample_mode == "CUSTOM_FPS":
        if settings.samples.custom_fps < 1:
            report.fail("Custom FPS must be at least 1")


def runtime_checks():
    """Capabilities required by the exporter."""
    missing = []
    if not hasattr(bpy.ops.export_scene, "fbx"):
        missing.append("FBX exporter")
    if hasattr(bpy.types.Action, "slots") is False and not hasattr(bpy.types.Scene, "urb"):
        pass
    return missing


def compatibility_report(scene_settings):
    """Return a compatibility summary for the current scene settings."""
    project = scene_settings.project
    return {
        "target_unreal": project.unreal_version,
        "coordinate_system": project.coordinate_system,
        "unit_scale": project.unit_scale if not project.auto_unit_scale else "automatic",
        "max_influences": scene_settings.export.max_influences,
        "deform_only": scene_settings.export.export_deform_only,
        "sample_mode": scene_settings.samples.sample_mode,
        "bake_object_transforms": scene_settings.export.bake_object_transforms,
    }
