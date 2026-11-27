"""Addon preferences: defaults and package locations."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences

from .constants import DEFAULT_MAX_INFLUENCES, SAMPLE_MODES


class URB_Preferences(AddonPreferences):
    bl_idname = __package__

    default_export_directory: StringProperty(
        name="Default Export Directory",
        subtype="DIR_PATH",
        default="//",
    )
    default_unreal_version: StringProperty(name="Default Unreal Version", default="5.8")
    default_sample_mode: EnumProperty(name="Default Sampling", items=SAMPLE_MODES, default="EVERY_FRAME")
    default_max_influences: IntProperty(name="Default Max Influences", default=DEFAULT_MAX_INFLUENCES, min=1, max=12)
    auto_analyse_on_export: BoolProperty(
        name="Analyse Before Export",
        description="Run rig analysis automatically before exporting",
        default=True,
    )
    show_advanced_metadata: BoolProperty(name="Show Advanced Metadata", default=True)
    keep_temporary_packages: BoolProperty(
        name="Keep Temporary Folders",
        description="Keep the uncompressed staging folder after export (debugging)",
        default=False,
    )
    adaptive_translation_tolerance: FloatProperty(name="Adaptive Translation", default=0.1, min=0.0)
    adaptive_rotation_tolerance: FloatProperty(name="Adaptive Rotation (deg)", default=0.5, min=0.0)
    fbx_leaf_bones: BoolProperty(
        name="Add Leaf Bones",
        description="Let Blender's FBX exporter add leaf bones; usually disabled for Unreal",
        default=False,
    )
    fbx_primary_axis: EnumProperty(
        name="Primary Bone Axis",
        items=(("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")),
        default="Y",
    )
    fbx_secondary_axis: EnumProperty(
        name="Secondary Bone Axis",
        items=(("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")),
        default="Z",
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Defaults")
        box.prop(self, "default_export_directory")
        box.prop(self, "default_unreal_version")
        box.prop(self, "default_sample_mode")
        box.prop(self, "default_max_influences")
        box.prop(self, "auto_analyse_on_export")

        box = layout.box()
        box.label(text="Sampling Tolerance")
        box.prop(self, "adaptive_translation_tolerance")
        box.prop(self, "adaptive_rotation_tolerance")

        box = layout.box()
        box.label(text="FBX")
        box.prop(self, "fbx_leaf_bones")
        row = box.row()
        row.prop(self, "fbx_primary_axis")
        row.prop(self, "fbx_secondary_axis")

        box = layout.box()
        box.label(text="Diagnostics")
        box.prop(self, "show_advanced_metadata")
        box.prop(self, "keep_temporary_packages")


def register():
    bpy.utils.register_class(URB_Preferences)


def unregister():
    bpy.utils.unregister_class(URB_Preferences)


def get_preferences(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        return None
    return addon.preferences
