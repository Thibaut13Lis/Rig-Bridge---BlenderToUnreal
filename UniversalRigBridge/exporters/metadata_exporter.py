"""Rig metadata, validation and manifest construction."""

from __future__ import annotations

from ..constants import PACKAGE_FORMAT, PACKAGE_SCHEMA_VERSION, PROJECT_VERSION
from ..core.constraint_analyzer import constraint_type_support
from ..core.mesh_analyzer import weight_report
from ..utils.file_utils import utc_now_iso


def manifest_payload(settings, armature_names, mesh_references, animation_references, skeletons, report, unit_scale):
    project = settings.project
    import bpy

    return {
        "package_name": project.project_name,
        "package_version": PACKAGE_SCHEMA_VERSION,
        "format": PACKAGE_FORMAT,
        "exporter": "Universal Rig Bridge",
        "exporter_version": PROJECT_VERSION,
        "blender_version": bpy.app.version_string,
        "export_date": utc_now_iso(),
        "target_unreal_version": project.unreal_version,
        "unit_scale": unit_scale,
        "unit_scale_mode": "automatic" if project.auto_unit_scale else "manual",
        "coordinate_system": project.coordinate_system,
        "framerate": project.resolved_fps,
        "export_format": project.export_format,
        "armatures": list(armature_names),
        "meshes": list(mesh_references),
        "animations": list(animation_references),
        "skeletons": [skeleton["armature"] for skeleton in skeletons],
        "summary": {
            "armatures": len(armature_names),
            "meshes": len(mesh_references),
            "animations": len(animation_references),
            "errors": report.get("errors", 0) if report else 0,
            "warnings": report.get("warnings", 0) if report else 0,
        },
        "notes": [
            "Blender axis conversion: X_unreal=-Y_blender, Y_unreal=X_blender, Z is unchanged",
            "Translations are stored in centimetres when Unreal Compatible is selected",
            "Animation rotations are quaternions ordered w,x,y,z",
        ],
    }


def bones_payload(analysis, settings):
    classifications = {(item.armature, item.name): item.bone_type for item in settings.bones}
    overrides = {(item.armature, item.name): item.override for item in settings.bones}
    records = []
    for bone in analysis["bones"]:
        key = (bone["armature"], bone["name"])
        records.append(
            {
                "armature": bone["armature"],
                "name": bone["name"],
                "parent": bone["parent"],
                "children": bone["children"],
                "auto_type": bone["auto_type"],
                "exported_type": classifications.get(key, bone["auto_type"]),
                "user_override": bool(overrides.get(key, False)),
                "classification_reason": bone["classification_reason"],
                "use_deform": bone["use_deform"],
                "connected": bone["connected"],
                "inherit_scale": bone["inherit_scale"],
                "collections": bone["collections"],
                "depth": bone["depth"],
                "head": bone["head"],
                "tail": bone["tail"],
                "length": bone["length"],
                "roll": bone["roll"],
                "rest_matrix": bone["rest_matrix"],
                "local_matrix": bone["local_matrix"],
                "rotation_mode": bone["rotation_mode"],
            }
        )
    return {"bones": records, "bone_types": _type_counts(records)}


def _type_counts(records):
    counts = {}
    for record in records:
        counts[record["exported_type"]] = counts.get(record["exported_type"], 0) + 1
    return counts


def constraints_payload(analysis, settings):
    records = []
    override = {(item.armature, item.owner, item.name): item.category for item in settings.constraints}
    for record in analysis["constraints"]:
        key = (record["armature"], record["owner"], record["name"])
        stored = override.get(key)
        records.append(
            {
                "armature": record["armature"],
                "name": record["name"],
                "type": record["type"],
                "owner": record["owner"],
                "owner_kind": record["owner_kind"],
                "target": record["target"],
                "subtarget": record["subtarget"],
                "influence": record["influence"],
                "enabled": record["enabled"],
                "category": stored or record["category"],
                "reason": record["reason"],
                "channels": record["channels"],
                "dependencies": record["dependencies"],
            }
        )
    return {
        "constraints": records,
        "capability_matrix": constraint_type_support(),
        "category_counts": _count_categories(records),
    }


def _count_categories(records):
    counts = {"SUPPORTED": 0, "BAKED": 0, "UNSUPPORTED": 0}
    for record in records:
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    return counts


def rig_analysis_payload(analysis, settings):
    return {
        "summary": analysis["summary"],
        "armatures": analysis["armatures"],
        "drivers": analysis["drivers"],
        "meshes": analysis["meshes"],
        "settings": {
            "coordinate_system": settings.project.coordinate_system,
            "deform_only": settings.export.export_deform_only,
            "max_influences": settings.export.max_influences,
        },
    }


def mesh_references_payload(meshes, armature_names):
    references = []
    for mesh in meshes:
        references.append(
            {
                "name": mesh["name"],
                "vertex_count": mesh["vertex_count"],
                "triangle_count": mesh["triangle_count"],
                "materials": mesh["material_slots"],
                "uv_maps": mesh["uv_maps"],
                "vertex_groups": mesh["vertex_groups"],
                "armature_modifier": mesh["armature_modifier"],
            }
        )
    return references


def validation_payload(analysis, settings, extra_issues=(), export_notes=None):
    report = {"issues": list(analysis["validation"]["issues"])}
    for message in extra_issues:
        report["issues"].append({"severity": "error", "message": message, "context": "export"})
    weights = []
    for mesh in analysis["meshes"]:
        armature_obj = None
        import bpy
        for candidate in bpy.data.objects:
            if candidate.type == "ARMATURE" and candidate.name in analysis.get("armature_names", []):
                from ..core.rig_analyzer import associated_meshes
                if mesh["name"] in [item.name for item in associated_meshes(candidate)]:
                    armature_obj = candidate
                    break
        if armature_obj is None:
            continue
        weights.append(weight_report(bpy.data.objects[mesh["name"]], armature_obj, settings.export.max_influences))
    report["weight_validation"] = weights
    report["export_notes"] = list(export_notes or [])
    report["summary"] = {
        "errors": sum(1 for issue in report["issues"] if issue["severity"] == "error"),
        "warnings": sum(1 for issue in report["issues"] if issue["severity"] == "warning"),
        "weights_checked": len(weights),
    }
    return report
