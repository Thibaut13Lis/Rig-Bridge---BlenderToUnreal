"""Focused unit tests for the parts that are easy to get silently wrong.

Run headless:
    blender.exe -b --factory-startup --python tests/test_units.py
"""

from __future__ import annotations

import math
import os
import sys
import traceback

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

ADDON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ADDON_PATH not in sys.path:
    sys.path.insert(0, ADDON_PATH)

from UniversalRigBridge.baking import root_motion
from UniversalRigBridge.baking.transform_sampler import frame_samples, simplify_samples
from UniversalRigBridge.utils.coordinate_conversion import (
    BLENDER_TO_UNREAL,
    convert_matrix,
    convert_rotation,
    convert_vector,
)
from UniversalRigBridge.utils.matrix_utils import lerp_matrix, rotation_delta

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} {detail}")
        FAILURES.append(name)


def close(a, b, tolerance=1e-6):
    return abs(a - b) <= tolerance


# ---------------------------------------------------------------- coordinates


def test_axis_convention():
    """X_unreal = -Y_blender, Y_unreal = X_blender, Z unchanged."""
    for blender, expected in (
        ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),  # Blender +Y (backwards) -> -X
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),  # Blender +X (right) -> +Y
        ((0.0, 0.0, 1.0), (0.0, 0.0, 1.0)),  # up is shared
    ):
        result = convert_vector(blender)
        check(
            f"axis {blender}",
            all(close(result[i], expected[i]) for i in range(3)),
            f"got {tuple(result)}",
        )


def test_rotation_round_trip():
    """A full 360 degree sweep of yaw/pitch/roll must stay unit and invertible."""
    worst = 0.0
    for degrees in (0, 90, 180, 270, -90, 45, 315):
        for axis in ("X", "Y", "Z"):
            rotation = Euler(
                (
                    math.radians(degrees if axis == "X" else 0),
                    math.radians(degrees if axis == "Y" else 0),
                    math.radians(degrees if axis == "Z" else 0),
                )
            ).to_quaternion()
            converted = convert_rotation(rotation)
            check(
                f"rotation unit {axis} {degrees}",
                close(converted.magnitude, 1.0, 1e-5),
                f"magnitude {converted.magnitude}",
            )
            # Rotating the same vector through both frames must agree.
            source = Vector((0.3, -0.7, 0.5)).normalized()
            blender_result = rotation @ source
            unreal_result = converted @ (BLENDER_TO_UNREAL.to_3x3() @ source)
            expected = BLENDER_TO_UNREAL.to_3x3() @ blender_result
            worst = max(worst, (unreal_result - expected).length)
    check("rotation commutes with axis change", worst < 1e-5, f"error {worst}")


def test_matrix_conversion_keeps_composition():
    """convert(a @ b) must equal convert(a) @ convert(b) so hierarchies hold."""
    parent = Matrix.LocRotScale(
        Vector((0.2, -0.4, 1.3)), Euler((0.3, -0.8, 1.1)).to_quaternion(), Vector((1, 1, 1))
    )
    child = Matrix.LocRotScale(
        Vector((-0.1, 0.6, 0.2)), Euler((-0.5, 0.2, 0.9)).to_quaternion(), Vector((1, 1, 1))
    )
    direct = convert_matrix(parent @ child)
    composed = convert_matrix(parent) @ convert_matrix(child)
    error = max(abs(direct[r][c] - composed[r][c]) for r in range(4) for c in range(4))
    check("conversion preserves composition", error < 1e-6, f"error {error}")


def test_unit_scale_only_touches_translation():
    rotation = Quaternion((0.9238795, 0.3826834, 0.0, 0.0))
    matrix = Matrix.LocRotScale(Vector((0.25, 0.5, 1.0)), rotation, Vector((2, 3, 4)))
    converted = convert_matrix(matrix, 100.0)
    check("unit scale scales translation", close(converted.translation.z, 100.0, 1e-4), str(converted.translation))
    # Rotation is converted by the basis change, not by the unit scale.
    unscaled = convert_matrix(matrix, 1.0)
    check(
        "unit scale leaves rotation",
        rotation_delta(converted, unscaled) < 1e-6,
        f"{rotation_delta(converted, unscaled)}",
    )
    # The 90 degree basis change swaps local X and Y, so a non-uniform scale is
    # permuted with it.  This is correct: the scale is expressed in Unreal bone
    # axes.  Only the magnitudes must survive.
    scale = converted.to_scale()
    expected = (3.0, 2.0, 4.0)
    check(
        "unit scale permutes but preserves scale magnitudes",
        all(close(abs(scale[i]), expected[i], 1e-5) for i in range(3)),
        f"got {tuple(scale)}",
    )


def test_negative_and_non_uniform_scale():
    """Mirrored bones are common; decomposition must not explode."""
    matrix = Matrix.LocRotScale(
        Vector((0.0, 0.0, 0.5)), Euler((0.0, 0.0, math.pi)).to_quaternion(), Vector((-1.0, 2.0, 0.5))
    )
    converted = convert_matrix(matrix)
    check("negative scale stays finite", all(math.isfinite(v) for row in converted for v in row))
    reconstructed = Matrix.LocRotScale(*converted.decompose())
    error = max(abs(reconstructed[r][c] - converted[r][c]) for r in range(4) for c in range(4))
    check("negative scale decomposes consistently", error < 1e-5, f"error {error}")


# --------------------------------------------------------------------- timing


def test_frame_samples_preserve_range():
    cases = [
        ("EVERY_FRAME", 30, 30, 2),
        ("CUSTOM_FPS", 24, 30, 2),
        ("CUSTOM_FPS", 60, 30, 2),
        ("CUSTOM_INTERVAL", 30, 30, 3),
    ]
    for mode, fps, interval_or_rate, interval in cases:
        if mode == "CUSTOM_INTERVAL":
            frames = frame_samples(1, 24, mode, 30, 30, interval)
        else:
            frames = frame_samples(1, 24, mode, fps, 30, 2)
        check(f"{mode} starts at range start", close(frames[0], 1.0), str(frames[0]))
        check(f"{mode} ends at range end", close(frames[-1], 24.0), str(frames[-1]))
        check(f"{mode} is monotonic", all(b > a for a, b in zip(frames, frames[1:])))
        check(f"{mode} has no duplicates", len(set(frames)) == len(frames))
        if len(frames) > 2:
            steps = [round(b - a, 6) for a, b in zip(frames, frames[1:])]
            check(f"{mode} keys are evenly spaced", len(set(steps)) == 1, str(set(steps)))


def test_half_rate_keeps_duration():
    frames = frame_samples(1, 25, "CUSTOM_FPS", 15, 30, 2)
    # 24 frames at 30 fps is 0.8 s; at 15 fps that is 12 intervals.
    check("half rate yields uniform 15 fps", len(frames) == 13, f"{len(frames)} keys")
    check("half rate duration is 0.8s", close((frames[-1] - frames[0]) / 30.0, 0.8, 1e-6))


# ------------------------------------------------------------------- adaptive


def test_adaptive_sampling_bounds_error():
    """Static data must collapse, curved data must keep its shape."""
    bone = ["hips"]
    static = [{bone[0]: Matrix.Identity(4)} for _ in range(60)]
    kept = simplify_samples(static, list(range(60)), bone, 0.01, 0.25, 0.005)
    check("static animation collapses to two keys", len(kept) == 2, f"{len(kept)} keys")

    curve = []
    for index in range(60):
        matrix = Matrix.Translation(Vector((0.0, 0.0, math.sin(index * 0.2) * 0.5)))
        curve.append({bone[0]: matrix})
    kept = simplify_samples(curve, list(range(60)), bone, 0.001, 0.25, 0.005)
    check("curved animation keeps samples", 2 < len(kept) < 60, f"{len(kept)} keys")

    worst = 0.0
    position = 0
    for index in range(60):
        while position < len(kept) - 2 and kept[position + 1] <= index:
            position += 1
        start, end = kept[position], kept[min(position + 1, len(kept) - 1)]
        if end == start:
            continue
        factor = (index - start) / (end - start)
        interpolated = lerp_matrix(curve[start][bone[0]], curve[end][bone[0]], factor)
        actual = curve[index][bone[0]]
        worst = max(worst, (interpolated.translation - actual.translation).length)
    check("adaptive error within tolerance", worst <= 0.001 + 1e-6, f"worst {worst}")


# ---------------------------------------------------------------- root motion


def test_root_motion_extraction_and_removal():
    delta = Matrix.Translation(Vector((0.0, 150.0, 0.0)))
    first = Matrix.Identity(4)
    locals_ = [first, first @ delta, first @ Matrix.Translation(Vector((0.0, 250.0, 0.0)))]

    deltas = root_motion.root_motion_track(
        [convert_matrix(m, 100.0) for m in locals_], "root", True, True, False
    )
    # Blender +Y maps to Unreal -X, and translations scale to centimetres.
    check("root motion delta grows", close(deltas[-1].translation.x, -25000.0, 1e-2), str(deltas[-1].translation))

    cleaned = root_motion.remove_root_motion(locals_, True, True, False)
    worst = max(
        max(abs(cleaned[index][r][c] - first[r][c]) for r in range(4) for c in range(4))
        for index in range(len(cleaned))
    )
    check("full extraction removes translation from pose", worst < 1e-6, f"error {worst}")

    # Translation-only extraction must keep the animated rotation in the pose.
    rotating = [
        Matrix.LocRotScale(Vector((0.0, 0.0, 0.0)), Euler((0.0, 0.0, 0.5 * index)).to_quaternion(), Vector((1, 1, 1)))
        for index in range(3)
    ]
    cleaned = root_motion.remove_root_motion(rotating, True, False, False)
    check(
        "translation-only extraction keeps rotation",
        rotation_delta(cleaned[-1], rotating[-1]) < 1e-6,
        "rotation was lost",
    )
    check(
        "translation-only extraction drops translation",
        cleaned[-1].translation.length < 1e-6,
        str(cleaned[-1].translation),
    )


def test_root_motion_scale_handling():
    scaled = [
        Matrix.LocRotScale(Vector((0, 0, 0)), Quaternion((1, 0, 0, 0)), Vector((1.0 + 0.1 * index, 1.0, 1.0)))
        for index in range(3)
    ]
    deltas = root_motion.root_motion_track(scaled, "root", True, True, False)
    check("scale is ignored when not extracted", close(deltas[-1].to_scale().x, 1.0, 1e-5))
    deltas = root_motion.root_motion_track(scaled, "root", True, True, True)
    check("scale is captured when extracted", close(deltas[-1].to_scale().x, 1.2, 1e-5))


# ------------------------------------------------------------------ animation


def build_nla_rig():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    armature_data = bpy.data.armatures.new("NlaArmature")
    armature = bpy.data.objects.new("NlaRig", armature_data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    root = armature_data.edit_bones.new("root")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.2)
    child = armature_data.edit_bones.new("child")
    child.head = (0.0, 0.0, 0.2)
    child.tail = (0.0, 0.0, 0.6)
    child.parent = root
    child.use_deform = True
    bpy.ops.object.mode_set(mode="POSE")
    for name in ("root", "child"):
        armature.pose.bones[name].rotation_mode = "QUATERNION"
    child_bone = armature.pose.bones["child"]
    scene.frame_set(1)
    child_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    child_bone.keyframe_insert("rotation_quaternion", frame=1)
    scene.frame_set(10)
    child_bone.rotation_quaternion = Euler((math.radians(40), 0.0, 0.0)).to_quaternion()
    child_bone.keyframe_insert("rotation_quaternion", frame=10)
    bpy.ops.object.mode_set(mode="OBJECT")
    action = armature.animation_data.action
    action.name = "NlaAction"
    track = armature.animation_data.nla_tracks.new()
    track.name = "Track"
    strip = track.strips.new("Strip", 1, action)
    strip.name = "Strip"
    armature.animation_data.action = None
    return armature, action


def test_nla_export_and_restore():
    armature, action = build_nla_rig()
    from UniversalRigBridge.baking import animation_baker

    track = armature.animation_data.nla_tracks[0]
    track.mute = True  # user state that must survive the bake
    bone_order = animation_baker.exported_bone_order(armature, deform_only=True)
    clip = animation_baker.bake_clip(
        bpy.context,
        armature,
        name="Nla",
        start=1,
        end=10,
        bone_order=bone_order,
        sample_mode="EVERY_FRAME",
        nla_track="Track",
        nla_strip="Strip",
    )
    check("NLA clip sampled", clip["sample_count"] == 10, f"{clip['sample_count']} samples")
    check("NLA source recorded", clip["source"] == "NLA", clip["source"])
    track_data = next(item for item in clip["tracks"] if item["name"] == "child")
    # Blender X rotation becomes Unreal Y rotation: quaternion (w, x, y, z).
    check(
        "NLA strip pose reached the samples",
        any(abs(rotation[2]) > 0.05 for rotation in track_data["rotations"]),
        "no rotation sampled",
    )
    check("NLA track mute restored", armature.animation_data.nla_tracks[0].mute is True)
    check("NLA strip mute restored", armature.animation_data.nla_tracks[0].strips[0].mute is False)
    check("NLA action released again", armature.animation_data.action is None)


def test_source_fps_is_recorded():
    armature, _action = build_nla_rig()
    bpy.context.scene.render.fps = 24
    from UniversalRigBridge.baking import animation_baker

    clip = animation_baker.bake_clip(
        bpy.context,
        armature,
        name="Fps",
        start=1,
        end=25,
        bone_order=animation_baker.exported_bone_order(armature, deform_only=True),
        sample_mode="EVERY_FRAME",
        nla_track="Track",
        nla_strip="Strip",
    )
    check("source fps is scene fps", close(clip["source_fps"], 24.0), str(clip["source_fps"]))
    check("clip fps matches source", close(clip["fps"], 24.0), str(clip["fps"]))
    check("timestamps end at duration", close(clip["timestamps"][-1], 1.0), str(clip["timestamps"][-1]))

    # A reduced key rate must not change the real duration of the clip.
    half = animation_baker.bake_clip(
        bpy.context,
        armature,
        name="HalfRate",
        start=1,
        end=25,
        bone_order=animation_baker.exported_bone_order(armature, deform_only=True),
        sample_mode="CUSTOM_FPS",
        custom_fps=12,
        nla_track="Track",
        nla_strip="Strip",
    )
    check("resampled clip reports its key rate", close(half["fps"], 12.0, 1e-6), str(half["fps"]))
    check(
        "resampled clip keeps source duration",
        close(half["timestamps"][-1], 1.0, 1e-6),
        f"{half['timestamps'][-1]}",
    )
    check(
        "fps and timestamps agree",
        close((len(half["timestamps"]) - 1) / half["fps"], 1.0, 1e-6),
        f"{(len(half['timestamps']) - 1) / half['fps']}",
    )


def test_quaternion_continuity():
    """A full spin must not flip hemisphere between exported samples."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    armature_data = bpy.data.armatures.new("SpinArmature")
    armature = bpy.data.objects.new("SpinRig", armature_data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    bone = armature_data.edit_bones.new("root")
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, 0.6)
    bone.use_deform = True
    bpy.ops.object.mode_set(mode="POSE")
    pose_bone = armature.pose.bones["root"]
    pose_bone.rotation_mode = "QUATERNION"
    for index, frame in enumerate(range(1, 25)):
        scene.frame_set(frame)
        pose_bone.rotation_quaternion = Euler((0.0, 0.0, math.radians(350.0 * index / 23))).to_quaternion()
        pose_bone.keyframe_insert("rotation_quaternion", frame=frame)
    bpy.ops.object.mode_set(mode="OBJECT")

    from UniversalRigBridge.baking import animation_baker

    clip = animation_baker.bake_clip(
        bpy.context,
        armature,
        name="Spin",
        start=1,
        end=24,
        bone_order=animation_baker.exported_bone_order(armature, deform_only=True),
    )
    rotations = next(item for item in clip["tracks"] if item["name"] == "root")["rotations"]
    dots = [sum(a * b for a, b in zip(rotations[i], rotations[i + 1])) for i in range(len(rotations) - 1)]
    check("quaternions stay in one hemisphere", min(dots) > 0.0, f"min dot {min(dots)}")
    check(
        "quaternions stay normalised",
        all(close(sum(v * v for v in rotation), 1.0, 1e-5) for rotation in rotations),
    )
    check("spin is captured", dots[0] < 0.9999, f"first step dot {dots[0]}")


def test_package_inspector_round_trip():
    """The dependency-free reader must decode exactly what the exporter writes."""
    tools_path = os.path.abspath(os.path.join(ADDON_PATH, "tools"))
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    import urb_inspect

    from UniversalRigBridge.exporters.binary_exporter import encode_animation

    clip = {
        "name": "Inspect",
        "fps": 24.0,
        "start_frame": 1,
        "end_frame": 49,
        "sample_count": 3,
        "source_frames": [1.0, 25.0, 49.0],
        "timestamps": [0.0, 1.0, 2.0],
        "source": "ACTION",
        "bone_order": ["root", "child"],
        "root_motion": {
            "bone": "root",
            "translations": [(0, 0, 0), (0, 100, 0), (0, 200, 0)],
            "rotations": [(1, 0, 0, 0)] * 3,
            "scales": [(1, 1, 1)] * 3,
        },
        "tracks": [
            {
                "name": "root",
                "translations": [(0, 0, 0), (0, 100, 0), (0, 200, 0)],
                "rotations": [(1, 0, 0, 0)] * 3,
                "scales": [(1, 1, 1)] * 3,
            },
            {
                "name": "child",
                "translations": [(0, 0, 0)] * 3,
                "rotations": [(1, 0, 0, 0), (0.8660254, 0.5, 0.0, 0.0), (1, 0, 0, 0)],
                "scales": [(1, 1, 1)] * 3,
            },
        ],
        "object_reference": {"translation": (0, 0, 0), "rotation": (1, 0, 0, 0), "scale": (1, 1, 1)},
        "object_transforms": [],
    }
    data = encode_animation(clip)
    decoded = urb_inspect.read_urbanim(data)
    check("inspector reads every byte", decoded["bytes_consumed"] == len(data), str(decoded["bytes_consumed"]))
    check("inspector reads bone table", decoded["bones"] == ["root", "child"], str(decoded["bones"]))
    check("inspector reads samples", len(decoded["samples"]) == 3, str(len(decoded["samples"])))
    check(
        "inspector reads root motion",
        decoded["root_motion"] is not None and close(decoded["root_motion"][-1]["translation"][1], 200.0),
        str(decoded["root_motion"]),
    )
    check("inspector computes duration", close(urb_inspect.duration(decoded), 2.0, 1e-6), str(urb_inspect.duration(decoded)))


def main():
    tests = [
        test_axis_convention,
        test_rotation_round_trip,
        test_matrix_conversion_keeps_composition,
        test_unit_scale_only_touches_translation,
        test_negative_and_non_uniform_scale,
        test_frame_samples_preserve_range,
        test_half_rate_keeps_duration,
        test_adaptive_sampling_bounds_error,
        test_root_motion_extraction_and_removal,
        test_root_motion_scale_handling,
        test_nla_export_and_restore,
        test_source_fps_is_recorded,
        test_quaternion_continuity,
        test_package_inspector_round_trip,
    ]
    for test in tests:
        try:
            test()
        except Exception:
            traceback.print_exc()
            FAILURES.append(test.__name__)
    print(f"[RESULT] {len(tests) - len(FAILURES)}/{len(tests)} test groups passed")
    if FAILURES:
        print(f"[RESULT] failures: {FAILURES}")
        sys.exit(1)


if __name__ == "__main__":
    main()
