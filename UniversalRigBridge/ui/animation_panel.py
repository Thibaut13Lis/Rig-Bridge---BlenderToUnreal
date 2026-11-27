"""Animation manager UI."""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


class URB_UL_animations(UIList):
    bl_idname = "URB_UL_animations"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "export_enabled", text="")
            icon_name = {"ACTION": "ACTION", "NLA": "NLA", "SCENE": "SCENE_DATA"}.get(item.source, "DOT")
            row.label(text=item.name, icon=icon_name)
            row.label(text=f"{item.start}-{item.end}")
        else:
            layout.label(text=item.name)


class URB_PT_animations(Panel):
    bl_label = "Animation Manager"
    bl_idname = "URB_PT_animations"
    bl_parent_id = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urb
        samples = settings.samples

        row = layout.row(align=True)
        row.prop(samples, "sample_mode", text="")
        if samples.sample_mode == "CUSTOM_FPS":
            row.prop(samples, "custom_fps", text="FPS")
        elif samples.sample_mode == "CUSTOM_INTERVAL":
            row.prop(samples, "frame_interval", text="Step")
        elif samples.sample_mode == "ADAPTIVE":
            row.label(text="Tolerance", icon="DRIVER")

        if samples.sample_mode == "ADAPTIVE":
            box = layout.box()
            box.prop(samples, "translation_tolerance")
            box.prop(samples, "rotation_tolerance")
            box.prop(samples, "scale_tolerance")

        if not settings.animations:
            layout.label(text="No animations cached (run Analyze Rig)", icon="INFO")
            return

        row = layout.row(align=True)
        row.operator("urb.select_all_animations", text="All")
        row.operator("urb.deselect_all_animations", text="None")
        row.label(text=f"{len(settings.animations)} clip(s)")

        layout.template_list(
            "URB_UL_animations", "", settings, "animations", settings, "animation_index", rows=8
        )

        index = settings.animation_index
        if 0 <= index < len(settings.animations):
            item = settings.animations[index]
            box = layout.box()
            box.prop(item, "name")
            row = box.row(align=True)
            row.prop(item, "start")
            row.prop(item, "end")
            row = box.row(align=True)
            row.prop(item, "sample_rate")
            if not item.sample_rate:
                row.label(text="= Scene")
            row.prop(item, "sample_mode", text="")
            row = box.row(align=True)
            row.prop(item, "looping")
            row.prop(item, "root_motion")
            row.prop(item, "compression")
            info_row = box.row(align=True)
            info_row.label(text=f"{item.frame_count} frames · {item.duration_seconds:.2f}s · {item.animated_bones} bones")
            info_row.operator("urb.preview_animation", text="Range").index = index


def register():
    bpy.utils.register_class(URB_UL_animations)
    bpy.utils.register_class(URB_PT_animations)


def unregister():
    bpy.utils.unregister_class(URB_PT_animations)
    bpy.utils.unregister_class(URB_UL_animations)
