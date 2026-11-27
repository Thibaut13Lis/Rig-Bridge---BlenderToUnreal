"""Test harness: create a skinned rig and exercise the addon headlessly."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import traceback

import bpy
from mathutils import Euler, Matrix, Vector

ADDON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ADDON_PATH not in sys.path:
    sys.path.insert(0, ADDON_PATH)


def log(message):
    print(f"[TEST] {message}")


def build_sample_rig():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start = 1
    scene.frame_end = 24

    armature_data = bpy.data.armatures.new("URB_Armature")
    armature = bpy.data.objects.new("URB_Rig", armature_data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    root = armature_data.edit_bones.new("root")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.2)
    root.use_deform = False

    hips = armature_data.edit_bones.new("hips")
    hips.head = (0.0, 0.0, 0.2)
    hips.tail = (0.0, 0.0, 0.5)
    hips.parent = root
    hips.use_connect = True
    hips.use_deform = True

    spine = armature_data.edit_bones.new("spine")
    spine.head = (0.0, 0.0, 0.5)
    spine.tail = (0.0, 0.0, 0.8)
    spine.parent = hips
    spine.use_connect = True
    spine.use_deform = True

    upper = armature_data.edit_bones.new("upper_arm.L")
    upper.head = (0.2, 0.0, 0.8)
    upper.tail = (0.5, 0.0, 0.8)
    upper.parent = spine
    upper.use_connect = False
    upper.use_deform = True

    forearm = armature_data.edit_bones.new("forearm.L")
    forearm.head = (0.5, 0.0, 0.8)
    forearm.tail = (0.8, 0.0, 0.8)
    forearm.parent = upper
    forearm.use_connect = True
    forearm.use_deform = True

    ik_target = armature_data.edit_bones.new("ik_hand.L")
    ik_target.head = (0.8, 0.0, 0.8)
    ik_target.tail = (0.9, 0.0, 0.8)
    ik_target.parent = root
    ik_target.use_connect = False
    ik_target.use_deform = False

    mecanim = armature_data.edit_bones.new("mch_counter.L")
    mecanim.head = (0.2, 0.0, 0.8)
    mecanim.tail = (0.2, 0.1, 0.8)
    mecanim.parent = spine
    mecanim.use_deform = False

    bpy.ops.object.mode_set(mode="POSE")

    const = armature.pose.bones["forearm.L"].constraints.new("IK")
    const.target = armature
    const.subtarget = "ik_hand.L"
    const.chain_count = 2

    limit = armature.pose.bones["spine"].constraints.new("LIMIT_ROTATION")
    limit.use_limit_x = True
    limit.min_x = math.radians(-20)
    limit.max_x = math.radians(20)

    armature.pose.bones["root"].rotation_mode = "QUATERNION"
    armature.pose.bones["hips"].rotation_mode = "QUATERNION"
    armature.pose.bones["spine"].rotation_mode = "QUATERNION"
    armature.pose.bones["upper_arm.L"].rotation_mode = "QUATERNION"
    armature.pose.bones["forearm.L"].rotation_mode = "QUATERNION"
    armature.pose.bones["ik_hand.L"].rotation_mode = "QUATERNION"

    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.12, depth=0.9, location=(0.0, 0.0, 0.5))
    body = bpy.context.object
    body.name = "URB_Body"
    group = body.vertex_groups.new(name="spine")
    group.add(list(range(len(body.data.vertices))), 1.0, "REPLACE")

    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.09, depth=0.62, location=(0.5, 0.0, 0.8))
    arm_mesh = bpy.context.object
    arm_mesh.name = "URB_Arm"
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = arm_mesh
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for vertex in arm_mesh.data.vertices:
        if vertex.co.x < 0.5:
            weight_group = arm_mesh.vertex_groups.get("upper_arm.L") or arm_mesh.vertex_groups.new(name="upper_arm.L")
            weight_group.add([vertex.index], 1.0, "REPLACE")
        else:
            weight_group = arm_mesh.vertex_groups.get("forearm.L") or arm_mesh.vertex_groups.new(name="forearm.L")
            weight_group.add([vertex.index], 1.0, "REPLACE")

    for mesh in (body, arm_mesh):
        modifier = mesh.modifiers.new("Armature", "ARMATURE")
        modifier.object = armature
        mesh.parent = armature
        mesh.matrix_parent_inverse = armature.matrix_world.inverted()

    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    bpy.context.scene.frame_set(1)
    root_bone = armature.pose.bones["root"]
    root_bone.location = (0.0, 0.0, 0.0)
    root_bone.keyframe_insert("location", frame=1)
    root_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    root_bone.keyframe_insert("rotation_quaternion", frame=1)

    bpy.context.scene.frame_set(24)
    root_bone.location = (1.5, 0.0, 0.0)
    root_bone.rotation_quaternion = Euler((0.0, 0.0, math.radians(45)), "XYZ").to_quaternion()
    root_bone.keyframe_insert("location", frame=24)
    root_bone.keyframe_insert("rotation_quaternion", frame=24)

    ik_bone = armature.pose.bones["ik_hand.L"]
    bpy.context.scene.frame_set(1)
    ik_bone.location = (0.0, 0.0, 0.0)
    ik_bone.keyframe_insert("location", frame=1)
    bpy.context.scene.frame_set(24)
    ik_bone.location = (0.0, 0.3, 0.4)
    ik_bone.keyframe_insert("location", frame=24)

    spine_bone = armature.pose.bones["spine"]
    bpy.context.scene.frame_set(1)
    spine_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    spine_bone.keyframe_insert("rotation_quaternion", frame=1)
    bpy.context.scene.frame_set(12)
    spine_bone.rotation_quaternion = Euler((math.radians(15), 0.0, 0.0), "XYZ").to_quaternion()
    spine_bone.keyframe_insert("rotation_quaternion", frame=12)
    bpy.context.scene.frame_set(24)
    spine_bone.rotation_quaternion = Euler((math.radians(-10), 0.0, 0.0), "XYZ").to_quaternion()
    spine_bone.keyframe_insert("rotation_quaternion", frame=24)

    action = armature.animation_data.action
    action.name = "URB_TestWalk"
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.scene.frame_set(1)
    return armature


def main():
    failures = []
    try:
        import UniversalRigBridge
        UniversalRigBridge.register()
        log("Addon registered")
    except Exception:
        traceback.print_exc()
        log("Registration failed")
        raise

    armature = build_sample_rig()
    scene = bpy.context.scene
    settings = scene.urb
    settings.project.export_directory = tempfile.mkdtemp(prefix="urb-export-")
    settings.project.project_name = "TestProject"
    settings.samples.translation_tolerance = 0.01
    settings.samples.rotation_tolerance = 0.25

    try:
        result = bpy.ops.urb.analyse_rig()
        log(f"analyse_rig -> {result}")
        summary = settings.summary
        log(
            "summary: "
            f"armatures={summary.armatures} bones={summary.bones} deform={summary.deform_bones} "
            f"control={summary.control_bones} mechanism={summary.mechanism_bones} "
            f"meshes={summary.meshes} constraints={summary.constraints} actions={summary.actions}"
        )
        assert summary.armatures == 1, "expected one armature"
        assert summary.bones == 7, f"expected 7 bones, got {summary.bones}"
        assert summary.constraints >= 2, "constraints not detected"
        assert summary.actions >= 1, "action not detected"
        types = {item.name: item.bone_type for item in settings.bones}
        log(f"classification: {types}")
        assert types["spine"] == "DEFORM"
        assert types["ik_hand.L"] == "CONTROL", "IK target should classify as CONTROL"
        assert types["mch_counter.L"] == "MECHANISM"

        issues = [(issue.severity, issue.message) for issue in settings.issues]
        for severity, message in issues:
            log(f"{severity}: {message}")

        for item in settings.animations:
            log(
                f"animation: {item.name} source={item.source} {item.start}-{item.end} "
                f"bones={item.animated_bones} enabled={item.export_enabled}"
            )
            item.root_motion = True
            item.looping = True

        settings.export.export_root_motion = True
        settings.root_motion.root_bone = "root"
        settings.root_motion.keep_in_pose = True

        # Verify our scene state before export.
        before = {
            "frame": scene.frame_current,
            "action": armature.animation_data.action.name if armature.animation_data.action else "",
            "slot": getattr(armature.animation_data.action_slot, "identifier", ""),
            "objects": [obj.name for obj in bpy.context.selected_objects],
        }

        result = bpy.ops.urb.export_to_unreal()
        log(f"export op -> {result}, status={settings.last_export_status}")
        path = settings.last_package
        log(f"package path: {path}")
        assert os.path.exists(path), "package file missing"

        after = {
            "frame": scene.frame_current,
            "action": armature.animation_data.action.name if armature.animation_data.action else "",
            "slot": getattr(armature.animation_data.action_slot, "identifier", ""),
        }
        log(f"scene before={before} after={after}")
        assert before["frame"] == after["frame"]
        assert before["action"] == after["action"]
        assert before["slot"] == after["slot"]

        import zipfile
        with zipfile.ZipFile(path) as archive:
            names = sorted(archive.namelist())
            log(f"package entries: {names}")
            manifest = json.loads(archive.read("manifest.json"))
            log(f"manifest: {json.dumps(manifest, indent=2)[:1500]}")
            report = json.loads(archive.read("validation/export_report.json"))
            log(f"validation summary: {report['summary']}")
            assert names.count("manifest.json") == 1
            assert any(name.startswith("animations/") and name.endswith(".urbanim") for name in names)
            assert "skeleton.json" in names
            assert "metadata/bones.json" in names
            assert "metadata/constraints.json" in names
            assert "validation/export_report.json" in names
            animation_name = [name for name in names if name.endswith(".urbanim")][0]
            animation_bytes = archive.read(animation_name)

        from UniversalRigBridge.exporters.binary_exporter import decode_animation
        decoded = decode_animation(animation_bytes)
        log(
            f"decoded animation: bones={decoded['bones']} samples={len(decoded['samples'])} "
            f"root={decoded['header']['root_motion_bone']} bytes={decoded['bytes_consumed']}/{decoded['total_bytes']}"
        )
        assert decoded["bytes_consumed"] == len(animation_bytes)
        assert len(decoded["samples"]) > 0
        assert decoded["header"]["root_motion_bone"] == "root"
        assert decoded["root_motion"] is not None
        first_root = decoded["samples"][0]["root"]["translation"]
        last_root = decoded["samples"][-1]["root"]["translation"]
        log(f"root pose first={first_root} last={last_root}")

        # Reconstruction guarantee
        from UniversalRigBridge.baking import animation_baker
        from UniversalRigBridge.exporters.animation_exporter import resolve_unit_scale
        unit_scale = resolve_unit_scale(settings)
        bone_order = animation_baker.exported_bone_order(armature, deform_only=True)
        clip = animation_baker.bake_clip(
            bpy.context,
            armature,
            name="Verify",
            start=1,
            end=24,
            fps=30,
            bone_order=bone_order,
            unit_scale=unit_scale,
            sample_mode="EVERY_FRAME",
            adaptive_tolerances=(0.01, 0.25, 0.005),
        )
        reconstruction = clip["reconstruction"]
        log(f"reconstruction: {reconstruction}")
        assert reconstruction["max_translation_error"] < 0.001, reconstruction
        assert reconstruction["max_rotation_error_radians"] < 1e-4, reconstruction
        log("ALL ASSERTIONS PASSED")
    except Exception:
        traceback.print_exc()
        failures.append("failure")
    finally:
        try:
            import UniversalRigBridge
            UniversalRigBridge.unregister()
            log("Addon unregistered")
        except Exception:
            traceback.print_exc()
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
