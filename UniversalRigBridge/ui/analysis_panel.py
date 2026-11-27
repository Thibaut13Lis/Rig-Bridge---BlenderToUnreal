"""Rig analysis summary, issue report and constraint inspector."""

from __future__ import annotations

import bpy
from bpy.types import Panel, UIList


class URB_UL_constraints(UIList):
    bl_idname = "URB_UL_constraints"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            icon_name = {"SUPPORTED": "CHECKMARK", "BAKED": "MODIFIER", "UNSUPPORTED": "CANCEL"}.get(
                item.category, "DOT"
            )
            row.label(text=item.name, icon=icon_name)
            row.label(text=item.constraint_type)
            row.prop(item, "category", text="")
        else:
            layout.label(text=item.name)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [0] * len(items)
        selected = context.scene.urb.constraint_filter
        order = list(range(len(items)))
        for index, item in enumerate(items):
            if selected == "ALL" or item.category == selected:
                flags[index] = self.bitflag_filter_item
        return flags, order


CONSTRAINT_FILTER_ITEMS = (
    ("ALL", "All", ""),
    ("SUPPORTED", "Supported", ""),
    ("BAKED", "Baked", ""),
    ("UNSUPPORTED", "Unsupported", ""),
)


class URB_PT_analysis(Panel):
    bl_label = "Rig Analysis"
    bl_idname = "URB_PT_analysis"
    bl_parent_id = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urb
        summary = settings.summary

        if not summary.analysed:
            layout.label(text="Run Analyze Rig to inspect the scene", icon="INFO")
            return

        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.label(text=f"Armatures: {summary.armatures}")
        grid.label(text=f"Bones: {summary.bones}")
        grid.label(text=f"Deform: {summary.deform_bones}")
        grid.label(text=f"Control: {summary.control_bones}")
        grid.label(text=f"Mechanism: {summary.mechanism_bones}")
        grid.label(text=f"Helper: {summary.helper_bones}")
        grid.label(text=f"Meshes: {summary.meshes}")
        grid.label(text=f"Constraints: {summary.constraints}")
        grid.label(text=f"Drivers: {summary.drivers}")
        grid.label(text=f"Actions: {summary.actions}")
        grid.label(text=f"NLA Tracks: {summary.nla_tracks}")
        grid.label(text=f"NLA Strips: {summary.nla_strips}")

        if summary.errors:
            layout.label(text=f"{summary.errors} error(s), {summary.warnings} warning(s)", icon="ERROR")
        elif summary.warnings:
            layout.label(text=f"{summary.warnings} warning(s)", icon="INFO")
        else:
            layout.label(text="No blocking issues detected", icon="CHECKMARK")

        if settings.armatures:
            column = layout.column(align=True)
            for item in settings.armatures:
                row = column.row(align=True)
                row.label(text=item.name, icon="ARMATURE_DATA")
                row.label(text=f"{item.bone_count}b / {item.mesh_count}m")

        if settings.issues:
            layout.label(text="Report", icon="TEXT")
            column = layout.column(align=True)
            shown = 0
            for issue in settings.issues:
                if shown >= 16:
                    break
                icon_name = {"error": "CANCEL", "warning": "ERROR", "info": "INFO"}.get(issue.severity, "DOT")
                column.label(text=issue.message, icon=icon_name)
                shown += 1
            remaining = max(0, len(settings.issues) - shown)
            if remaining:
                layout.label(text=f"... {remaining} more in export_report.json")


class URB_PT_constraints(Panel):
    bl_label = "Constraint Analysis"
    bl_idname = "URB_PT_constraints"
    bl_parent_id = "URB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UNIVERSAL RIG BRIDGE"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urb

        if not settings.constraints:
            layout.label(text="No constraints detected (or run Analyze Rig)", icon="INFO")
            return

        counts = {"SUPPORTED": 0, "BAKED": 0, "UNSUPPORTED": 0}
        for item in settings.constraints:
            counts[item.category] = counts.get(item.category, 0) + 1
        row = layout.row(align=True)
        row.label(text=f"Supported {counts['SUPPORTED']}")
        row.label(text=f"Baked {counts['BAKED']}")
        row.label(text=f"Unsupported {counts['UNSUPPORTED']}")

        row = layout.row()
        row.prop(settings, "constraint_filter", text="Show")
        row.prop(settings, "constraint_index", text="")

        layout.template_list(
            "URB_UL_constraints",
            "",
            settings,
            "constraints",
            settings,
            "constraint_index",
            rows=8,
        )

        index = settings.constraint_index
        if 0 <= index < len(settings.constraints):
            item = settings.constraints[index]
            box = layout.box()
            box.label(text=f"{item.owner} · {item.name}", icon="CONSTRAINT")
            column = box.column(align=True)
            column.label(text=f"Type: {item.constraint_type}")
            column.label(text=f"Target: {item.target or 'None'}")
            column.label(text=f"Channels: {item.channels or 'None'}")
            column.label(text=f"Influence: {item.influence:.2f}" + ("" if item.enabled else " (disabled)"))
            column.label(text=f"Dependencies: {item.dependencies or 'None'}")
            box.label(text=item.note, icon="INFO")


def register():
    bpy.utils.register_class(URB_UL_constraints)
    bpy.utils.register_class(URB_PT_analysis)
    bpy.utils.register_class(URB_PT_constraints)


def unregister():
    bpy.utils.unregister_class(URB_PT_constraints)
    bpy.utils.unregister_class(URB_PT_analysis)
    bpy.utils.unregister_class(URB_UL_constraints)
