"""High-level scene analysis orchestration.

This module owns the single analysis pass that feeds the UI, the exporters and
the validation report.  It never mutates scene data or the classification of
bones; UI overrides live in the addon properties.
"""

from __future__ import annotations

import bpy

from ..utils.logging import Report, info
from . import (
    animation_analyzer,
    bone_analyzer,
    compatibility_checker,
    constraint_analyzer,
    dependency_analyzer,
    mesh_analyzer,
    rig_analyzer,
)


def analyse_scene(context, selected_only=False, check_weights=True, max_influences=4):
    scene = context.scene
    settings = scene.urb
    report = Report()
    armatures = rig_analyzer.collect_armatures(context, selected_only)
    result = {
        "armatures": [],
        "bones": [],
        "constraints": [],
        "drivers": [],
        "meshes": [],
        "animations": [],
        "summary": {},
        "validation": None,
    }

    if not armatures:
        report.warn("No armature found" + (" in the selection" if selected_only else " in the scene"))

    for armature_obj in armatures:
        if not compatibility_checker.check_armature(armature_obj, report):
            continue
        armature_info = rig_analyzer.armature_object_record(armature_obj)
        armature_info["summary"] = rig_analyzer.armature_summary(armature_obj)
        meshes = rig_analyzer.associated_meshes(armature_obj)
        armature_info["meshes"] = [mesh.name for mesh in meshes]
        armature_info["animation"] = animation_analyzer.detect_animation_properties(armature_obj)
        result["armatures"].append(armature_info)

        weighted_names = bone_analyzer.weighted_bone_names(armature_obj, meshes)
        referenced_bones = _constraint_target_bones(armature_obj)
        for bone, depth, _index in bone_analyzer.walk_bones(armature_obj):
            result["bones"].append(
                bone_analyzer.bone_record(
                    armature_obj,
                    bone,
                    depth,
                    weighted_names=weighted_names,
                    referenced_bones=referenced_bones,
                )
            )
        exported_bones = {bone.name for bone in armature_obj.data.bones if bone.use_deform}
        constraints = constraint_analyzer.collect_constraints(armature_obj, exported_bones)
        result["constraints"].extend(constraints)
        compatibility_checker.check_constraints(constraints, report)

        drivers = dependency_analyzer.collect_drivers(armature_obj, extra_objects=meshes)
        result["drivers"].extend(drivers)
        compatibility_checker.check_drivers(drivers, report)

        for obj in meshes:
            result["meshes"].append(mesh_analyzer.mesh_record(obj, armature_obj))
            compatibility_checker.check_meshes(
                armature_obj, [obj], max_influences, report, check_weights=check_weights
            )

    animations = animation_analyzer.animation_records(context)
    result["animations"] = animations
    compatibility_checker.check_animation(
        animations, report, [armature["name"] for armature in result["armatures"]]
    )
    compatibility_checker.check_project(settings, report)

    result["summary"] = build_summary(result, report)
    result["validation"] = report.as_dict()
    return result


def _constraint_target_bones(armature_obj):
    """Bones that other bones constrain against (IK targets, poles, track targets)."""
    names = set()
    for bone in armature_obj.pose.bones:
        for constraint in bone.constraints:
            target = getattr(constraint, "target", None)
            if target is armature_obj:
                subtarget = getattr(constraint, "subtarget", "")
                if subtarget:
                    names.add(subtarget)
            pole = getattr(constraint, "pole_target", None)
            if pole is armature_obj and getattr(constraint, "pole_subtarget", ""):
                names.add(constraint.pole_subtarget)
    for constraint in armature_obj.constraints:
        target = getattr(constraint, "target", None)
        if target is armature_obj and getattr(constraint, "subtarget", ""):
            names.add(constraint.subtarget)
    return names


def build_summary(result, report):
    bones = result["bones"]
    armatures = result["armatures"]
    animations = result["animations"]
    constraints = result["constraints"]
    nla_strips = sum(len(track.strips) for armature in armatures for track in _nla_tracks(armature["name"]))
    return {
        "armatures": len(armatures),
        "bones": len(bones),
        "deform_bones": sum(1 for bone in bones if bone["use_deform"]),
        "control_bones": sum(1 for bone in bones if bone["auto_type"] == "CONTROL"),
        "mechanism_bones": sum(1 for bone in bones if bone["auto_type"] == "MECHANISM"),
        "helper_bones": sum(1 for bone in bones if bone["auto_type"] == "HELPER"),
        "root_bones": sum(1 for bone in bones if bone["auto_type"] == "ROOT"),
        "meshes": len(result["meshes"]),
        "constraints": len(constraints),
        "supported_constraints": sum(1 for record in constraints if record["category"] == "SUPPORTED"),
        "baked_constraints": sum(1 for record in constraints if record["category"] == "BAKED"),
        "unsupported_constraints": sum(1 for record in constraints if record["category"] == "UNSUPPORTED"),
        "drivers": len(result["drivers"]),
        "actions": len({record["action"] for record in animations}),
        "animation_clips": len(animations),
        "nla_tracks": sum(len(_nla_tracks(armature["name"])) for armature in armatures),
        "nla_strips": nla_strips,
        "warnings": len(report.warnings),
        "errors": len(report.errors),
    }


def _nla_tracks(object_name):
    obj = bpy.data.objects.get(object_name)
    if obj is None or obj.animation_data is None:
        return []
    return list(obj.animation_data.nla_tracks)


def apply_analysis_to_settings(context, result):
    """Copy a plain analysis result into the UI property cache."""
    settings = context.scene.urb
    previous_animations = {
        item.key: {
            "name": item.name,
            "export_enabled": item.export_enabled,
            "start": item.start,
            "end": item.end,
            "sample_rate": item.sample_rate,
            "sample_mode": item.sample_mode,
            "looping": item.looping,
            "root_motion": item.root_motion,
            "compression": item.compression,
        }
        for item in settings.animations
    }
    settings.summary.analysed = True
    settings.summary.analysed_at = _now()
    summary = result["summary"]
    for key in (
        "armatures", "bones", "deform_bones", "control_bones", "mechanism_bones",
        "helper_bones", "meshes", "constraints", "drivers", "actions", "warnings", "errors",
    ):
        if hasattr(settings.summary, key):
            setattr(settings.summary, key, int(summary.get(key, 0)))
    settings.summary.status = (
        f"{summary['armatures']} armature(s), {summary['bones']} bones, "
        f"{summary['animation_clips']} clip(s)"
    )

    _replace_collection(settings.armatures)
    for armature in result["armatures"]:
        item = settings.armatures.add()
        item.name = armature["name"]
        item.data_name = armature.get("summary", {}).get("data_name", "")
        item.bone_count = armature.get("summary", {}).get("bone_count", 0)
        item.mesh_count = armature.get("summary", {}).get("mesh_count", 0)
        item.deform_count = armature.get("summary", {}).get("deform_count", 0)
        item.action_hint = armature.get("summary", {}).get("action_hint", "")

    previous_types = {
        (item.armature, item.name): (item.bone_type, item.override)
        for item in settings.bones
    }
    _replace_collection(settings.bones)
    for bone in result["bones"]:
        item = settings.bones.add()
        item.name = bone["name"]
        item.armature = bone["armature"]
        item.parent = bone["parent"]
        item.children = ", ".join(bone["children"])
        item.auto_type = bone["auto_type"]
        item.deform = bone["use_deform"]
        item.connected = bone["connected"]
        item.depth = bone["depth"]
        item.collections = ", ".join(bone["collections"])
        item.head = bone["head"]
        item.tail = bone["tail"]
        item.length = bone["length"]
        item.rest_display = _format_matrix(bone["rest_matrix"])
        item.pose_display = _format_matrix(bone["pose_matrix"])
        stored = previous_types.get((item.armature, item.name))
        if stored and stored[1]:
            item.bone_type = stored[0]
            item.override = True
        else:
            item.bone_type = bone["auto_type"]
            item.override = False

    _replace_collection(settings.constraints)
    for record in result["constraints"]:
        item = settings.constraints.add()
        item.name = record["name"]
        item.armature = record["armature"]
        item.owner = record["owner"]
        item.owner_kind = record["owner_kind"]
        item.constraint_type = record["type"]
        item.target = record["target"]
        item.influence = record["influence"]
        item.enabled = record["enabled"]
        item.category = record["category"]
        item.channels = ", ".join(record["channels"])
        item.dependencies = ", ".join(record["dependencies"])
        item.note = record["reason"]

    _replace_collection(settings.animations)
    project = settings.project
    for record in result["animations"]:
        item = settings.animations.add()
        item.key = record["key"]
        item.name = record["name"]
        item.source = record["source"]
        item.armature = record.get("armature", "")
        item.action = record["action"]
        item.slot_identifier = record.get("slot_identifier", "")
        item.nla_track = record.get("nla_track", "")
        item.nla_strip = record.get("nla_strip", "")
        item.start = record["start"]
        item.end = record["end"]
        item.sample_rate = 0.0
        item.sample_mode = settings.samples.sample_mode
        item.frame_count = record["frame_count"]
        item.animated_bones = record["animated_bones"]
        item.animated_objects = str(record["animated_objects"])
        fps = max(1, project.resolved_fps)
        item.duration_seconds = round(record["frame_count"] / fps, 6)
        previous = previous_animations.get(record["key"])
        if previous:
            item.name = previous["name"]
            item.export_enabled = previous["export_enabled"]
            item.start = previous["start"]
            item.end = previous["end"]
            item.sample_rate = previous["sample_rate"]
            item.sample_mode = previous["sample_mode"]
            item.looping = previous["looping"]
            item.root_motion = previous["root_motion"]
            item.compression = previous["compression"]

    _replace_collection(settings.issues)
    for issue in result["validation"]["issues"]:
        item = settings.issues.add()
        item.severity = issue["severity"]
        item.message = issue["message"]
        item.context = issue["context"]

    settings.last_export_status = "Analysis complete"
    info(settings.summary.status)


def _replace_collection(collection):
    collection.clear()


def _format_matrix(rows):
    if not rows:
        return ""
    return " | ".join(" ".join(f"{value:+.3f}" for value in row) for row in rows)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
