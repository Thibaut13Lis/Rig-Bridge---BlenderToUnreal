"""Driver evaluation helper.

Drivers can be simple expressions, scripted expressions, or procedural noise.
They are always evaluated by Blender's dependency graph during sampling.  This
module only reports and verifies the evaluated state.
"""

from __future__ import annotations

import bpy


def evaluated_property(id_block, data_path, array_index=-1):
    owner = id_block
    attributes = data_path.split(".")
    for attribute in attributes[:-1]:
        owner = getattr(owner, attribute)
    prop = attributes[-1]
    value = getattr(owner, prop)
    if array_index >= 0:
        return value[array_index]
    return value


def driver_health(id_block):
    animation_data = getattr(id_block, "animation_data", None)
    if animation_data is None:
        return {"drivers": 0, "invalid": 0}
    drivers = list(animation_data.drivers)
    return {
        "drivers": len(drivers),
        "invalid": sum(1 for driver in drivers if not driver.driver.is_valid),
    }


def has_scripted_drivers(armature_obj):
    channels = []
    if armature_obj.animation_data:
        channels.extend(armature_obj.animation_data.drivers)
    for bone in armature_obj.pose.bones:
        if bone.animation_data:
            channels.extend(bone.animation_data.drivers)
    return any(
        channel.driver.type == "SCRIPTED" or channel.driver.is_simple_expression is False
        for channel in channels
    )
