"""Export settings, root motion and export command UI."""

from __future__ import annotations

import bpy
from bpy.types import Panel


class URB_PT_export(Panel):
    bl_label = "Export Settings"
    bl_idname = "URB_PT_export"
    bl_parent_id = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urb
        export = settings.export

        box = layout.box()
        box.label(text="Skeleton & Mesh", icon="ARMATURE_DATA")
        box.prop(export, "export_skeleton")
        box.prop(export, "export_skeletal_mesh")
        box.prop(export, "export_deform_only")
        row = box.row(align=True)
        row.prop(export, "check_weights")
        row.prop(export, "max_influences", text="Max Inf.")

        box = layout.box()
        box.label(text="Animation", icon="ACTION")
        box.prop(export, "export_animations")
        box.prop(export, "bake_object_transforms")
        box.prop(export, "export_all_actions")

        box = layout.box()
        box.label(text="Metadata", icon="TEXT")
        box.prop(export, "export_bone_metadata")

        box = layout.box()
        root = settings.root_motion
        header = box.row(align=True)
        header.prop(export, "export_root_motion")
        sub = box.column(align=True)
        sub.enabled = export.export_root_motion
        sub.prop(root, "root_bone")
        row = sub.row(align=True)
        row.prop(root, "extract_translation")
        row.prop(root, "extract_rotation")
        row = sub.row(align=True)
        row.prop(root, "extract_full")
        row.prop(root, "keep_in_pose")

        layout.separator()
        column = layout.column(align=True)
        column.scale_y = 1.4
        column.operator("urb.export_to_unreal", text="EXPORT TO UNREAL ENGINE", icon="EXPORT")

        if settings.last_export_status:
            layout.label(text=settings.last_export_status, icon="INFO")
        if settings.last_package:
            box = layout.box()
            box.label(text="Last package", icon="PACKAGE")
            box.label(text=bpy.path.basename(settings.last_package))
            box.operator("urb.open_package_folder", text="Open Folder", icon="FILE_FOLDER")


def register():
    bpy.utils.register_class(URB_PT_export)


def unregister():
    bpy.utils.unregister_class(URB_PT_export)
