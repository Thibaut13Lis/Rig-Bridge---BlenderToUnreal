"""Animation clip selection and .urbanim writing."""

from __future__ import annotations

import bpy

from ..baking import animation_baker as baker
from ..baking.root_motion import choose_root_bone
from ..utils.coordinate_conversion import unit_scale_from_scene
from . import binary_exporter


def resolve_unit_scale(settings):
    project = settings.project
    if project.coordinate_system == "BLENDER":
        return 1.0
    return unit_scale_from_scene(bpy.context.scene, project.auto_unit_scale, project.unit_scale)


def _find_slot(action, identifier):
    slots = getattr(action, "slots", None)
    if not slots:
        return None
    for slot in slots:
        if slot.identifier == identifier:
            return slot
    return None


def _armature_for_item(item, armature_objects):
    if item.armature:
        obj = armature_objects.get(item.armature)
        if obj is not None:
            return obj
    # Actions are not necessarily assigned; pick the rig that uses the action.
    action = bpy.data.actions.get(item.action)
    if action is not None:
        for obj in armature_objects.values():
            animation_data = obj.animation_data
            if animation_data and animation_data.action == action:
                return obj
    if len(armature_objects) == 1:
        return next(iter(armature_objects.values()))
    return None


def select_animation_items(settings, armature_objects, actions_cache):
    exported = []
    if settings.export.export_all_actions:
        selected = [item for item in settings.animations if item.source != "NLA"]
    else:
        selected = [item for item in settings.animations if item.export_enabled]
    for item in selected:
        armature = _armature_for_item(item, armature_objects)
        if armature is None:
            continue
        exported.append((item, armature))
    return exported


def bake_selected_animations(context, settings, armature_objects):
    """Bake every selected animation.  Returns (clips, errors)."""
    unit_scale = resolve_unit_scale(settings)
    root_settings_base = _root_settings(settings)
    clips = []
    errors = []
    for item, armature in select_animation_items(settings, armature_objects, {}):
        try:
            action = bpy.data.actions.get(item.action) if item.action else None
            slot = _find_slot(action, item.slot_identifier) if action is not None else None
            if item.source == "NLA":
                if armature.animation_data is None:
                    raise baker.BakeError("Armature lost animation data")
                action = None
                slot = None
            bone_order = baker.exported_bone_order(armature, deform_only=settings.export.export_deform_only)
            root_settings = dict(root_settings_base)
            root_settings["enabled"] = bool(settings.export.export_root_motion and item.root_motion)
            root_settings["bone"] = choose_root_bone(armature, settings.root_motion.root_bone) if root_settings["enabled"] else ""
            root_settings["bake_object"] = bool(settings.export.bake_object_transforms)
            clip = baker.bake_clip(
                context,
                armature,
                name=item.name,
                start=item.start,
                end=item.end,
                fps=None,
                sample_rate=item.sample_rate if item.sample_rate else None,
                bone_order=bone_order,
                unit_scale=unit_scale,
                sample_mode=item.sample_mode,
                custom_fps=settings.samples.custom_fps,
                frame_interval=settings.samples.frame_interval,
                action=action if item.source != "NLA" else None,
                slot=slot if item.source != "NLA" else None,
                nla_track=item.nla_track,
                nla_strip=item.nla_strip,
                adaptive_tolerances=(
                    settings.samples.translation_tolerance,
                    settings.samples.rotation_tolerance,
                    settings.samples.scale_tolerance,
                ),
                root_motion_settings=root_settings,
                remove_root_from_pose=(
                    root_settings["enabled"]
                    and not settings.root_motion.keep_in_pose
                ),
            )
            clip["looping"] = bool(item.looping)
            clip["compression"] = bool(item.compression)
            clip["armature"] = armature.name
            clip["source_key"] = item.key
            clips.append(clip)
        except Exception as error:  # Keep other clips exportable.
            message = f"Animation '{item.name}' failed: {error}"
            errors.append(message)
            from ..utils import logging as urb_log
            urb_log.error(message)
    return clips, errors


def _root_settings(settings):
    root = settings.root_motion
    return {
        "enabled": False,
        "bone": root.root_bone,
        "translation": root.extract_translation,
        "rotation": root.extract_rotation,
        "full": root.extract_full,
    }


def write_animation_files(staging_directory, clips):
    import os

    directory = os.path.join(staging_directory, "animations")
    os.makedirs(directory, exist_ok=True)
    written = []
    used = set()
    from ..utils.naming import sanitize, unique_name

    for clip in clips:
        base = sanitize(clip["name"], "Animation")
        filename = unique_name(base, used) + ".urbanim"
        path = os.path.join(directory, filename)
        data = binary_exporter.encode_animation(clip)
        with open(path, "wb") as handle:
            handle.write(data)
        written.append(
            {
                "name": clip["name"],
                "file": f"animations/{filename}",
                "frame_start": clip["start_frame"],
                "frame_end": clip["end_frame"],
                "fps": clip["fps"],
                "source_fps": clip.get("source_fps", clip["fps"]),
                "samples": clip["sample_count"],
                "bones": len(clip["bone_order"]),
                "root_motion": clip["root_motion"]["bone"],
                "looping": clip.get("looping", False),
                "source": clip["source"],
                "armature": clip.get("armature", ""),
                "bytes": len(data),
            }
        )
    return written
