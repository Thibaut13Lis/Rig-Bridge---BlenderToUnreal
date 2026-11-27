"""Bone hierarchy explorer."""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList

ICONS = {
    "ROOT": "EMPTY_AXIS",
    "DEFORM": "BONE_DATA",
    "CONTROL": "PIVOT_CURSOR",
    "MECHANISM": "MODIFIER",
    "HELPER": "DOT",
    "UNKNOWN": "QUESTION",
}


class URB_UL_bones(UIList):
    bl_idname = "URB_UL_bones"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text="", icon=ICONS.get(item.bone_type, "DOT"))
            if item.depth:
                row.label(text="  " * min(item.depth, 8) + item.name)
            else:
                row.label(text=item.name)
            row.label(text=item.bone_type, icon="FREEZE" if item.override else "NONE")
        else:
            layout.label(text=item.name)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        settings = context.scene.urb
        search = settings.bone_filter.lower()
        flags = [0] * len(items)
        order = list(range(len(items)))
        for index, item in enumerate(items):
            matches = True
            if search and search not in item.name.lower() and search not in item.parent.lower():
                matches = False
            if settings.show_only_deform and not item.deform:
                matches = False
            if matches:
                flags[index] = self.bitflag_filter_item
        return flags, order


class URB_PT_bones(Panel):
    bl_label = "Bone Hierarchy"
    bl_idname = "URB_PT_bones"
    bl_parent_id = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urb

        if not settings.bones:
            layout.label(text="No bones cached (run Analyze Rig)", icon="INFO")
            return

        row = layout.row(align=True)
        row.prop(settings, "bone_filter", text="", icon="VIEWZOOM")
        row.prop(settings, "show_only_deform", text="", icon="BONE_DATA")

        layout.template_list("URB_UL_bones", "", settings, "bones", settings, "bone_index", rows=10)

        index = settings.bone_index
        if 0 <= index < len(settings.bones):
            item = settings.bones[index]
            box = layout.box()
            header = box.row(align=True)
            header.label(text=item.name, icon=ICONS.get(item.bone_type, "DOT"))
            op = header.operator("urb.focus_bone", text="Select", icon="RESTRICT_SELECT_OFF")
            op.armature = item.armature
            op.bone = item.name

            grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            grid.label(text=f"Parent: {item.parent or 'None'}")
            grid.label(text=f"Deform: {'Yes' if item.deform else 'No'}")
            grid.label(text=f"Connected: {'Yes' if item.connected else 'No'}")
            grid.label(text=f"Length: {item.length:.4f}")
            grid.label(text=f"Collections: {item.collections or 'None'}")
            grid.label(text=f"Children: {item.children or 'None'}")

            type_row = box.row(align=True)
            type_row.label(text="Classify:")
            type_row.prop(item, "bone_type", text="")
            type_row.operator("urb.apply_classification", text="", icon="LOOP_BACK").index = index
            if item.override:
                box.label(text="Manual override (metadata only)", icon="INFO")

            column = box.column(align=True)
            column.label(text="Rest matrix")
            column.label(text=item.rest_display)
            column.label(text="Pose matrix")
            column.label(text=item.pose_display)

        box = layout.box()
        box.label(text="Legend", icon="QUESTION")
        grid = box.grid_flow(row_major=False, columns=3, even_columns=True, align=True)
        for name in ("DEFORM", "CONTROL", "MECHANISM", "ROOT", "HELPER", "UNKNOWN"):
            grid.label(text=name, icon=ICONS[name])


def register():
    bpy.utils.register_class(URB_UL_bones)
    bpy.utils.register_class(URB_PT_bones)


def unregister():
    bpy.utils.unregister_class(URB_PT_bones)
    bpy.utils.unregister_class(URB_UL_bones)
