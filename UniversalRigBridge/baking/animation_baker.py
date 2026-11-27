"""Animation bake orchestration.

The baker is intentionally conservative: it never inserts keyframes into the
user's actions, never applies modifiers and never edits the rig.  It only
switches the evaluated action/slot, samples the dependency graph, and restores
the previous state in a finally block.
"""

from __future__ import annotations

import bpy
from mathutils import Matrix, Quaternion

from ..utils import logging as urb_log
from ..utils.coordinate_conversion import convert_matrix
from . import root_motion as root_motion_module
from .transform_sampler import (
    EvaluatedPoseReader,
    clip_time,
    frame_samples,
    set_scene_frame,
    simplify_samples,
)


class BakeError(RuntimeError):
    pass


class SceneState:
    """Snapshot of the parts of the scene the baker changes."""

    def __init__(self, scene, armature_obj):
        self.scene = scene
        self.armature = armature_obj
        self.frame_current = scene.frame_current
        self.frame_subframe = scene.frame_subframe
        self.frame_start = scene.frame_start
        self.frame_end = scene.frame_end
        self.render_fps = scene.render.fps
        self.render_fps_base = scene.render.fps_base
        self.pose_position = armature_obj.data.pose_position if armature_obj.data else "POSE"
        self.hide_viewport = armature_obj.hide_viewport
        self.hide_render = armature_obj.hide_render
        animation_data = armature_obj.animation_data
        self.action = animation_data.action if animation_data else None
        self.action_slot = None
        self.use_nla = True
        self.nla_mute = {}
        self.nla_solo = {}
        self.nla_strip_mute = {}
        if animation_data:
            self.action_slot = getattr(animation_data, "action_slot", None)
            self.use_nla = animation_data.use_nla
            for track in animation_data.nla_tracks:
                self.nla_mute[track.name] = track.mute
                self.nla_solo[track.name] = track.is_solo
                for strip in track.strips:
                    self.nla_strip_mute[f"{track.name}/{strip.name}"] = strip.mute
        self.mode = bpy.context.mode
        self.active_object = bpy.context.view_layer.objects.active
        self.selected = [obj.name for obj in bpy.context.selected_objects]
        self.object_matrix = armature_obj.matrix_world.copy()
        self.object_location = armature_obj.location.copy()
        self.object_rotation_mode = armature_obj.rotation_mode
        self.object_rotation_euler = armature_obj.rotation_euler.copy()
        self.object_rotation_quaternion = armature_obj.rotation_quaternion.copy()
        self.object_scale = armature_obj.scale.copy()

    def restore(self):
        scene = self.scene
        armature = self.armature
        try:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        scene.frame_set(int(self.frame_current), subframe=float(self.frame_subframe))
        scene.frame_start = self.frame_start
        scene.frame_end = self.frame_end
        scene.render.fps = self.render_fps
        scene.render.fps_base = self.render_fps_base
        if armature.data is not None:
            armature.data.pose_position = self.pose_position
        animation_data = armature.animation_data
        if animation_data is not None:
            animation_data.use_nla = self.use_nla
            for track in animation_data.nla_tracks:
                if track.name in self.nla_mute:
                    track.mute = self.nla_mute[track.name]
                if track.name in self.nla_solo:
                    track.is_solo = self.nla_solo[track.name]
                for strip in track.strips:
                    key = f"{track.name}/{strip.name}"
                    if key in self.nla_strip_mute:
                        strip.mute = self.nla_strip_mute[key]
            if self.action is not None:
                animation_data.action = self.action
                if self.action_slot is not None and hasattr(animation_data, "action_slot"):
                    try:
                        animation_data.action_slot = self.action_slot
                    except (TypeError, RuntimeError):
                        pass
            elif animation_data.action is not None:
                animation_data.action = None
                if hasattr(animation_data, "action_slot"):
                    try:
                        animation_data.action_slot = None
                    except (TypeError, RuntimeError):
                        pass
        armature.matrix_world = self.object_matrix
        armature.hide_viewport = self.hide_viewport
        armature.hide_render = self.hide_render
        active = self.active_object
        if active is not None and active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = active
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for name in self.selected:
            obj = bpy.context.view_layer.objects.get(name)
            if obj is not None:
                obj.select_set(True)
        bpy.context.view_layer.update()


def prepare_action(armature_obj, action, slot):
    animation_data = armature_obj.animation_data_create()
    animation_data.use_nla = False
    animation_data.action = action
    if slot is not None and hasattr(animation_data, "action_slot"):
        try:
            animation_data.action_slot = slot
        except (TypeError, RuntimeError):
            resolved = _match_slot(action, armature_obj)
            if resolved is not None:
                animation_data.action_slot = resolved
    elif hasattr(animation_data, "action_slot"):
        resolved = _match_slot(action, armature_obj)
        if resolved is not None:
            animation_data.action_slot = resolved


def prepare_nla_strip(armature_obj, track_name, strip_name):
    """Solo one NLA strip without mutating the user's track layout.

    The strip is moved to a local scene range so the sampled interval maps to
    the action frames selected by the user.  Mute/solo flags are restored by
    SceneState afterwards.
    """
    animation_data = armature_obj.animation_data
    if animation_data is None:
        raise BakeError("Armature has no animation data for the NLA clip")
    animation_data.use_nla = True
    animation_data.action = None
    if hasattr(animation_data, "action_slot"):
        try:
            animation_data.action_slot = None
        except (TypeError, RuntimeError):
            pass
    found = False
    for track in animation_data.nla_tracks:
        track.is_solo = False
        for strip in track.strips:
            strip.mute = True
        if track.name == track_name:
            track.mute = False
            for strip in track.strips:
                if strip.name == strip_name:
                    strip.mute = False
                    found = True
    if not found:
        raise BakeError(f"NLA strip '{track_name}/{strip_name}' no longer exists")


def _match_slot(action, obj):
    slots = getattr(action, "slots", None)
    if not slots:
        return None
    for slot in slots:
        if slot.name_display == obj.name:
            return slot
    for slot in slots:
        if slot.target_id_type == "OBJECT":
            return slot
    return None


def exported_bone_order(armature_obj, deform_only=True):
    """Hierarchy-ordered bones that will be exported.

    Matches Blender's FBX ``use_armature_deform_only`` behaviour: deform bones
    plus every ancestor required to preserve the hierarchy.  A rig with no
    deform bones falls back to the full skeleton so animation-only rigs still
    export.  Parents always precede children.
    """
    data = armature_obj.data
    if data is None:
        return []
    if not deform_only:
        candidates = {bone.name for bone in data.bones}
    else:
        deform = {bone.name for bone in data.bones if bone.use_deform}
        if deform:
            candidates = set(deform)
            for name in list(deform):
                bone = data.bones.get(name)
                while bone is not None and bone.parent is not None:
                    candidates.add(bone.parent.name)
                    bone = bone.parent
        else:
            candidates = {bone.name for bone in data.bones}
    ordered = [bone for bone in data.bones if bone.name in candidates]
    ordered.sort(key=lambda bone: _depth(bone))
    return [bone.name for bone in ordered]


def _depth(bone):
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def reference_skeleton(armature_obj, bone_order, unit_scale=1.0):
    """Reference rest matrices in Unreal space for the exported bone set.

    Reference locals are relative to the nearest exported ancestor, exactly
    like the sampled animation locals.  This keeps the reference skeleton and
    the animation tracks on the same hierarchy when intermediate control bones
    are omitted.
    """
    ordered = set(bone_order)
    records = []
    for name in bone_order:
        bone = armature_obj.data.bones.get(name)
        if bone is None:
            continue
        ancestor = bone.parent
        while ancestor is not None and ancestor.name not in ordered:
            ancestor = ancestor.parent
        if ancestor is not None:
            reference = ancestor.matrix_local.inverted() @ bone.matrix_local
        else:
            reference = bone.matrix_local.copy()
        records.append(
            {
                "name": name,
                "parent": ancestor.name if ancestor else "",
                "reference_local": convert_matrix(reference, unit_scale),
                "world": convert_matrix(armature_obj.matrix_world @ bone.matrix_local, unit_scale),
            }
        )
    return records


def bake_clip(
    context,
    armature_obj,
    *,
    name,
    start,
    end,
    fps=None,
    bone_order,
    unit_scale=1.0,
    sample_mode="EVERY_FRAME",
    custom_fps=30,
    frame_interval=2,
    action=None,
    slot=None,
    nla_track="",
    nla_strip="",
    adaptive_tolerances=(0.1, 0.5, 0.005),
    root_motion_settings=None,
    remove_root_from_pose=False,
    sample_rate=None,
):
    scene = context.scene
    if end < start:
        raise BakeError(f"Invalid frame range {start}..{end} for '{name}'")
    if not bone_order:
        raise BakeError(f"No exported bones for '{name}'")

    state = SceneState(scene, armature_obj)
    source_fps = state.render_fps / max(0.001, state.render_fps_base)
    if fps:
        requested_fps = float(fps)
    elif sample_rate:
        requested_fps = float(sample_rate)
    else:
        requested_fps = source_fps
    effective_mode = sample_mode
    effective_custom_fps = custom_fps
    if sample_mode == "EVERY_FRAME" and abs(requested_fps - source_fps) > 0.01:
        # An explicit clip rate differs from the scene rate: resample at that
        # rate while preserving the real-time duration of the clip.
        effective_mode = "CUSTOM_FPS"
        effective_custom_fps = max(1, int(round(requested_fps)))
    frames = frame_samples(
        start, end, effective_mode, effective_custom_fps, source_fps, frame_interval
    )
    duration_seconds = (float(end) - float(start)) / max(1e-9, source_fps)
    if duration_seconds > 0 and len(frames) > 1:
        sample_fps = (len(frames) - 1) / duration_seconds
    else:
        sample_fps = source_fps
    if abs(sample_fps - round(sample_fps)) < 1e-6:
        sample_fps = float(round(sample_fps))
    reader = EvaluatedPoseReader(armature_obj, bone_order, unit_scale)
    reference_local = {name: reader.reference_local(name) for name in bone_order}

    captured = []
    world_captured = []
    object_matrices = []
    try:
        if armature_obj.data is not None:
            armature_obj.data.pose_position = "POSE"
        if nla_track:
            prepare_nla_strip(armature_obj, nla_track, nla_strip)
        elif action is not None:
            prepare_action(armature_obj, action, slot)
        else:
            animation_data = armature_obj.animation_data
            if animation_data is not None:
                animation_data.use_nla = False
        for frame in frames:
            set_scene_frame(scene, frame)
            bpy.context.view_layer.update()
            locals_uw, worlds, object_matrix = reader.read()
            captured.append(locals_uw)
            world_captured.append(worlds)
            object_matrices.append(object_matrix)
    finally:
        state.restore()

    if not captured:
        raise BakeError(f"No frames sampled for '{name}'")

    kept_indices = list(range(len(frames)))
    adaptive_error = None
    if sample_mode == "ADAPTIVE":
        kept_indices = simplify_samples(
            captured,
            frames,
            bone_order,
            translation_tolerance=adaptive_tolerances[0],
            rotation_tolerance_degrees=adaptive_tolerances[1],
            scale_tolerance=adaptive_tolerances[2],
        )
        adaptive_error = interpolation_error(captured, kept_indices, bone_order)

    root_settings = root_motion_settings or {}
    root_name = root_settings.get("bone", "")
    root_enabled = bool(root_settings.get("enabled", False)) and root_name in bone_order
    root_track = None
    if root_enabled:
        world_for_root = [worlds[root_name] for worlds in world_captured]
        root_track = root_motion_module.root_motion_track(
            world_for_root,
            root_name,
            extract_translation=root_settings.get("translation", True),
            extract_rotation=root_settings.get("rotation", True),
            extract_scale=root_settings.get("full", False),
        )

    tracks = []
    for name_bone in bone_order:
        translations = []
        rotations = []
        scales = []
        previous_rotation = None
        for index in kept_indices:
            matrix = captured[index].get(name_bone, reference_local[name_bone])
            location, rotation, scale = matrix.decompose()
            # Keep successive quaternions in the same hemisphere.  Unreal slerps
            # the stored values directly, so a sign flip between samples would
            # interpolate the long way around the arc.
            if previous_rotation is not None and previous_rotation.dot(rotation) < 0.0:
                rotation = Quaternion((-rotation.w, -rotation.x, -rotation.y, -rotation.z))
            previous_rotation = rotation
            translations.append((float(location.x), float(location.y), float(location.z)))
            rotations.append((float(rotation.w), float(rotation.x), float(rotation.y), float(rotation.z)))
            scales.append((float(scale.x), float(scale.y), float(scale.z)))
        tracks.append(
            {
                "name": name_bone,
                "translations": translations,
                "rotations": rotations,
                "scales": scales,
            }
        )

    # Frame positions are scene frames, so real seconds always come from the
    # scene rate — not from the (possibly reduced) sample rate.
    timestamps = [clip_time(frames[index], start, source_fps) for index in kept_indices]
    source_frames = [float(frames[index]) for index in kept_indices]

    root_track_kept = None
    if root_track is not None:
        root_track_kept = [root_track[index] for index in kept_indices]

    # Validate the exported locals against the evaluated pose *before* root
    # motion is removed: once extracted, the root track is deliberately not the
    # Blender pose any more, and comparing against it would be meaningless.
    reconstruction = validate_reconstruction(
        captured, world_captured, kept_indices, bone_order, object_matrices, reader.fallback_ancestor
    )

    if remove_root_from_pose and root_enabled:
        # Root motion must leave the skeletal pose; otherwise Unreal applies the
        # displacement twice.  Only extracted channels are cancelled so a
        # translation-only extraction keeps the animated root rotation.
        root_locals = [captured[index][root_name] for index in kept_indices]
        cleaned = root_motion_module.remove_root_motion(
            root_locals,
            extract_translation=bool(root_settings.get("translation", True)),
            extract_rotation=bool(root_settings.get("rotation", True)),
            extract_scale=bool(root_settings.get("full", False)),
        )
        for position, index in enumerate(kept_indices):
            captured[index][root_name] = cleaned[position]
        for track in tracks:
            if track["name"] != root_name:
                continue
            for position, matrix in enumerate(cleaned):
                location, rotation, scale = matrix.decompose()
                track["translations"][position] = (float(location.x), float(location.y), float(location.z))
                track["rotations"][position] = (float(rotation.w), float(rotation.x), float(rotation.y), float(rotation.z))
                track["scales"][position] = (float(scale.x), float(scale.y), float(scale.z))

    source_type = "NLA" if nla_track else ("ACTION" if action is not None else "SCENE")
    clip = {
        "name": name,
        "fps": round(float(sample_fps), 6),
        "source_fps": round(float(source_fps), 6),
        "start_frame": int(start),
        "end_frame": int(end),
        "sample_count": len(kept_indices),
        "source_frames": source_frames,
        "timestamps": timestamps,
        "source": source_type,
        "action": action.name if action is not None else "",
        "slot_identifier": slot.identifier if slot is not None else "",
        "nla_track": nla_track,
        "nla_strip": nla_strip,
        "bone_order": list(bone_order),
        "tracks": tracks,
        "root_motion": {
            "bone": root_name if root_enabled else "",
            "translations": [tuple(matrix.translation) for matrix in root_track_kept] if root_track_kept else [],
            "rotations": [tuple(matrix.to_quaternion()) for matrix in root_track_kept] if root_track_kept else [],
            "scales": [tuple(matrix.to_scale()) for matrix in root_track_kept] if root_track_kept else [],
        },
        "object_transforms": [
            _object_track(object_matrices[index]) for index in kept_indices
        ] if root_settings.get("bake_object", False) else [],
    }
    object_matrix = object_matrices[kept_indices[0]]
    location, rotation, scale = object_matrix.decompose()
    clip["object_reference"] = {
        "translation": tuple(location),
        "rotation": tuple(rotation),
        "scale": tuple(scale),
    }
    clip["reconstruction"] = reconstruction
    if adaptive_error:
        clip["adaptive_error"] = adaptive_error
    urb_log.info(f"Baked '{name}': {clip['sample_count']} samples, {len(bone_order)} bones")
    return clip


def validate_reconstruction(captured, world_captured, kept_indices, bone_order, object_matrices, parents):
    """Rebuild Unreal-space world matrices from exported locals.

    The exported local matrix of a bone is relative to its nearest exported
    ancestor.  Composing those locals and applying the armature object matrix
    must equal the evaluated world matrix.  This is the guarantee that the
    animation will reproduce the Blender pose in Unreal.
    """
    from ..utils.matrix_utils import rotation_delta

    worst_translation = 0.0
    worst_rotation = 0.0
    worst_scale = 0.0
    for index in kept_indices:
        composed = {}
        for name in bone_order:
            local = captured[index][name]
            parent = parents.get(name, "")
            if parent:
                global_matrix = composed[parent] @ local
            else:
                global_matrix = local
            composed[name] = global_matrix
            reconstructed = object_matrices[index] @ global_matrix
            expected = world_captured[index][name]
            translation_error = (reconstructed.translation - expected.translation).length
            rotation_error = rotation_delta(reconstructed, expected)
            reconstructed_scale = reconstructed.to_scale()
            expected_scale = expected.to_scale()
            scale_error = max(abs(reconstructed_scale[axis] - expected_scale[axis]) for axis in range(3))
            worst_translation = max(worst_translation, translation_error)
            worst_rotation = max(worst_rotation, rotation_error)
            worst_scale = max(worst_scale, scale_error)
    return {
        "max_translation_error": round(worst_translation, 9),
        "max_rotation_error_radians": round(worst_rotation, 9),
        "max_scale_error": round(worst_scale, 9),
        "samples_checked": len(kept_indices),
        "bones_checked": len(bone_order),
    }


def _object_track(matrix):
    location, rotation, scale = matrix.decompose()
    return {
        "translation": (float(location.x), float(location.y), float(location.z)),
        "rotation": (float(rotation.w), float(rotation.x), float(rotation.y), float(rotation.z)),
        "scale": (float(scale.x), float(scale.y), float(scale.z)),
    }


def interpolation_error(captured, kept_indices, bone_order):
    """Measure the error introduced by keeping only the reduced samples.

    Intermediate dropped samples are reconstructed by linear/slerp between the
    two surrounding kept samples, then compared with the evaluated matrices.
    """
    if len(kept_indices) < 2 or len(kept_indices) == len(captured):
        return {"max_translation_error": 0.0, "max_rotation_error_radians": 0.0, "max_scale_error": 0.0}
    from ..utils.matrix_utils import lerp_matrix, rotation_delta, scale_delta

    worst_translation = 0.0
    worst_rotation = 0.0
    worst_scale = 0.0
    for position in range(len(kept_indices) - 1):
        start_index = kept_indices[position]
        end_index = kept_indices[position + 1]
        span = end_index - start_index
        if span <= 1:
            continue
        for index in range(start_index + 1, end_index):
            factor = (index - start_index) / span
            for name in bone_order:
                interpolated = lerp_matrix(captured[start_index][name], captured[end_index][name], factor)
                actual = captured[index][name]
                worst_translation = max(worst_translation, (interpolated.translation - actual.translation).length)
                worst_rotation = max(worst_rotation, rotation_delta(interpolated, actual))
                worst_scale = max(worst_scale, scale_delta(interpolated, actual))
    return {
        "max_translation_error": round(worst_translation, 9),
        "max_rotation_error_radians": round(worst_rotation, 9),
        "max_scale_error": round(worst_scale, 9),
    }
