"""Constraint and driver baking helpers.

Both modules evaluate through Blender; they never convert the constraint or
driver itself.  The produced values are the exported animation samples.
"""

from __future__ import annotations

import bpy

from .transform_sampler import EvaluatedPoseReader


def capture_pose(armature_obj, bone_order, unit_scale):
    reader = EvaluatedPoseReader(armature_obj, bone_order, unit_scale)
    return reader.read()


def constraints_affect(armature_obj):
    for bone in armature_obj.pose.bones:
        if len(bone.constraints) > 0:
            return True
    return len(armature_obj.constraints) > 0


def drivers_present(armature_obj):
    animation_data = armature_obj.animation_data
    if animation_data and len(animation_data.drivers) > 0:
        return True
    for bone in armature_obj.pose.bones:
        if bone.animation_data and len(bone.animation_data.drivers) > 0:
            return True
    return False
