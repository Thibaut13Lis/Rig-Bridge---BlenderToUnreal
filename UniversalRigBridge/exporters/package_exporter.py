"""Exporter orchestration and .urb package assembly."""

from __future__ import annotations

import math
import os
import shutil
import tempfile
from contextlib import contextmanager

import bpy

from ..core import rig_analyzer
from ..core.validation import analyse_scene
from ..utils.file_utils import ensure_directory, sha256_file, write_json, zip_directory
from ..utils.naming import sanitize
from . import animation_exporter, json_exporter, metadata_exporter, skeletal_exporter


class ExportError(RuntimeError):
    pass


def _armature_objects(analysis):
    objects = {}
    for record in analysis["armatures"]:
        obj = bpy.data.objects.get(record["name"])
        if obj is not None and obj.type == "ARMATURE":
            objects[obj.name] = obj
    return objects


def _keep_temporary():
    try:
        from ..preferences import get_preferences
        preferences = get_preferences()
        return bool(preferences and preferences.keep_temporary_packages)
    except Exception:
        return False


def export_package(context, settings, progress=None):
    """Perform a full export.  Returns a result dictionary."""
    project = settings.project
    report_progress = progress or (lambda message, fraction: None)
    report_progress("Analysing rig", 0.02)
    analysis = analyse_scene(
        context,
        selected_only=project.export_selected_only,
        check_weights=settings.export.check_weights,
        max_influences=settings.export.max_influences,
    )
    analysis["armature_names"] = [record["name"] for record in analysis["armatures"]]

    if not analysis["armatures"]:
        raise ExportError("No armature to export" + (" in the selection" if project.export_selected_only else ""))

    export = settings.export
    if not export.export_skeleton and not export.export_skeletal_mesh and not export.export_animations:
        raise ExportError("Every export section is disabled")

    directory = bpy.path.abspath(project.export_directory or "//")
    if not directory:
        raise ExportError("Export directory is not set")
    ensure_directory(directory)

    package_name = sanitize(project.project_name, "UniversalRig")
    staging = tempfile.mkdtemp(prefix=".urb-staging-", dir=directory)
    try:
        result = _build_package(context, settings, analysis, staging, package_name, report_progress)
    finally:
        if not _keep_temporary():
            shutil.rmtree(staging, ignore_errors=True)
    return result


def _build_package(context, settings, analysis, staging, package_name, report_progress):
    project = settings.project
    armature_objects = _armature_objects(analysis)
    unit_scale = animation_exporter.resolve_unit_scale(settings)

    report_progress("Writing skeleton metadata", 0.15)
    if settings.export.export_skeleton:
        skeletons = skeletal_exporter.skeletons_payload(list(armature_objects.values()), analysis, settings)
    else:
        skeletons = {"skeletons": []}

    report_progress("Baking animations", 0.25)
    clips = []
    animation_errors = []
    if settings.export.export_animations:
        clips, animation_errors = animation_exporter.bake_selected_animations(context, settings, armature_objects)
    animation_references = animation_exporter.write_animation_files(staging, clips) if clips else []
    json_exporter.write_json_animations(staging, clips)

    report_progress("Exporting meshes", 0.6)
    mesh_references = []
    if settings.export.export_skeletal_mesh:
        mesh_references = _export_meshes(staging, analysis, armature_objects, package_name, settings)

    report_progress("Writing metadata", 0.75)
    if settings.export.export_bone_metadata:
        write_json(os.path.join(staging, "metadata", "bones.json"), metadata_exporter.bones_payload(analysis, settings))
    write_json(
        os.path.join(staging, "metadata", "constraints.json"),
        metadata_exporter.constraints_payload(analysis, settings),
    )
    write_json(
        os.path.join(staging, "metadata", "rig_analysis.json"),
        metadata_exporter.rig_analysis_payload(analysis, settings),
    )
    write_json(os.path.join(staging, "metadata", "drivers.json"), {"drivers": analysis["drivers"]})
    write_json(os.path.join(staging, "skeleton.json"), skeletons)

    report_progress("Validating package", 0.85)
    notes = list(animation_errors)
    for clip in clips:
        reconstruction = clip.get("reconstruction") or {}
        translation_error = reconstruction.get("max_translation_error", 0.0)
        rotation_error = reconstruction.get("max_rotation_error_radians", 0.0)
        if translation_error > 0.001 or rotation_error > 1e-4:
            notes.append(
                f"Reconstruction error in '{clip['name']}': "
                f"{translation_error:.6f} units, {math.degrees(rotation_error):.6f} deg"
            )
    validation = metadata_exporter.validation_payload(analysis, settings, animation_errors, notes)
    write_json(os.path.join(staging, "validation", "export_report.json"), validation)

    report_progress("Writing manifest", 0.92)
    manifest = metadata_exporter.manifest_payload(
        settings,
        [record["name"] for record in analysis["armatures"]],
        mesh_references,
        animation_references,
        skeletons.get("skeletons", []),
        validation["summary"],
        unit_scale,
    )
    manifest["validation"] = {
        "errors": validation["summary"]["errors"],
        "warnings": validation["summary"]["warnings"],
        "report": "validation/export_report.json",
    }
    write_json(os.path.join(staging, "manifest.json"), manifest)

    export_format = project.export_format
    if export_format == "URB":
        final_path = os.path.join(bpy.path.abspath(project.export_directory), package_name + ".urb")
        zip_directory(staging, final_path)
    elif export_format == "FOLDER":
        final_path = os.path.join(bpy.path.abspath(project.export_directory), package_name)
        if os.path.isdir(final_path):
            shutil.rmtree(final_path)
        shutil.copytree(staging, final_path)
    else:
        final_path = os.path.join(bpy.path.abspath(project.export_directory), package_name + ".json")
        json_exporter.write_single_json(staging, final_path)

    report_progress("Export finished", 1.0)
    return {
        "path": final_path,
        "manifest": manifest,
        "animations": animation_references,
        "meshes": mesh_references,
        "skeletons": len(skeletons.get("skeletons", [])),
        "validation": validation,
        "analysis": analysis,
    }


@contextmanager
def preserved_selection():
    """Restore object selection and the active object after FBX export."""
    active = bpy.context.view_layer.objects.active
    selected = [obj for obj in bpy.context.selected_objects]
    try:
        yield
    finally:
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for obj in selected:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        if active is not None and active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = active
        elif selected:
            bpy.context.view_layer.objects.active = selected[0]


def _export_meshes(staging, analysis, armature_objects, package_name, settings):
    mesh_directory = ensure_directory(os.path.join(staging, "meshes"))
    references = []
    meshes_by_armature = {}
    for armature_name in armature_objects:
        armature_obj = armature_objects[armature_name]
        for obj in rig_analyzer.associated_meshes(armature_obj):
            meshes_by_armature.setdefault(armature_name, []).append(obj)

    if not meshes_by_armature:
        return references

    deform_only = bool(settings.export.export_deform_only)
    with preserved_selection():
        for armature_name, objects in meshes_by_armature.items():
            armature_obj = armature_objects[armature_name]
            _select_only([armature_obj] + objects)
            filename = f"{sanitize(package_name)}_{sanitize(armature_name)}.fbx"
            path = os.path.join(mesh_directory, filename)
            _export_fbx(path, armature_obj, deform_only=deform_only)
            for obj in objects:
                references.append(
                    {
                        "name": obj.name,
                        "file": f"meshes/{filename}",
                        "armature": armature_name,
                        "vertex_count": len(obj.data.vertices),
                        "sha256": sha256_file(path),
                    }
                )
    return references


def _select_only(objects):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _export_fbx(path, armature_obj, deform_only=True):
    if not hasattr(bpy.ops.export_scene, "fbx"):
        raise ExportError("Blender's FBX exporter is not available")
    try:
        result = bpy.ops.export_scene.fbx(
            filepath=path,
            use_selection=True,
            object_types={"ARMATURE", "MESH"},
            use_mesh_modifiers=True,
            add_leaf_bones=False,
            bake_anim=False,
            use_armature_deform_only=bool(deform_only),
            apply_scale_options="FBX_SCALE_UNITS",
            axis_forward="-Z",
            axis_up="Y",
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            use_space_transform=True,
            # Baking space transform moves the skinned mesh away from the rig
            # when the armature object has a scale (verified in Blender 5.0).
            bake_space_transform=False,
            path_mode="COPY",
            embed_textures=False,
            use_custom_props=True,
        )
    except TypeError as error:
        raise ExportError(f"FBX export options are not supported by this Blender version: {error}")
    if "FINISHED" not in result:
        raise ExportError("FBX export failed")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise ExportError("FBX export produced no file")
    return path
