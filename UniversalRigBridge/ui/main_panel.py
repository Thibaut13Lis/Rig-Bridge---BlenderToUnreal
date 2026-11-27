"""Viewport N-panel root and project settings."""

from __future__ import annotations

import bpy
from bpy.types import Panel


class URB_PT_main(Panel):
    bl_label = "Universal Rig Bridge"
    bl_idname = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"

    def draw(self, context):
        layout = self.layout
        settings = getattr(context.scene, "urb", None)
        if settings is None:
            layout.label(text="Addon properties unavailable", icon="ERROR")
            return

        project = settings.project
        box = layout.box()
        box.label(text="PROJECT SETTINGS", icon="FILE_FOLDER")
        column = box.column(align=True)
        column.prop(project, "project_name")

        row = column.row(align=True)
        row.prop(project, "export_directory", text="")
        row.operator("urb.select_export_directory", text="", icon="FILE_FOLDER")

        column.prop(project, "unreal_version")
        row = column.row(align=True)
        row.prop(project, "export_format", text="")
        row.prop(project, "coordinate_system", text="")

        row = column.row(align=True)
        row.prop(project, "use_scene_fps", text="Scene FPS")
        if project.use_scene_fps:
            row.label(text=f"{project.resolved_fps} fps")
        else:
            row.prop(project, "export_fps", text="FPS")

        row = column.row(align=True)
        row.prop(project, "auto_unit_scale", text="Auto Unit Scale")
        sub = row.row(align=True)
        sub.enabled = not project.auto_unit_scale
        sub.prop(project, "unit_scale", text="Scale")

        column.prop(project, "export_selected_only")

        row = layout.row(align=True)
        row.operator("urb.analyse_rig", text="ANALYZE RIG", icon="PLAY")
        row.operator("urb.clear_analysis", text="", icon="TRASH")


def register():
    bpy.utils.register_class(URB_PT_main)


def unregister():
    bpy.utils.unregister_class(URB_PT_main)
