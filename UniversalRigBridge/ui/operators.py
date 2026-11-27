"""Blender operators exposed by the addon."""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

from ..baking.animation_baker import BakeError
from ..core.validation import analyse_scene, apply_analysis_to_settings
from ..exporters.package_exporter import ExportError, export_package
from ..utils import logging as urb_log


class URB_OT_select_export_directory(Operator):
    bl_idname = "urb.select_export_directory"
    bl_label = "Select Export Folder"
    bl_description = "Choose the folder that receives exported packages"
    bl_options = {"INTERNAL"}

    directory: StringProperty(subtype="DIR_PATH")
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, event):
        current = bpy.path.abspath(context.scene.urb.project.export_directory or "//")
        if os.path.isfile(current):
            current = os.path.dirname(current)
        context.window_manager.fileselect_add(self)
        self.directory = current
        return {"RUNNING_MODAL"}

    def execute(self, context):
        directory = self.directory or context.scene.urb.project.export_directory
        context.scene.urb.project.export_directory = directory
        self.report({"INFO"}, f"Export folder: {bpy.path.abspath(directory)}")
        return {"FINISHED"}


class URB_OT_analyse_rig(Operator):
    bl_idname = "urb.analyse_rig"
    bl_label = "Analyze Rig"
    bl_description = "Analyse armatures, bones, constraints, drivers, meshes and animations"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.urb
        result = analyse_scene(
            context,
            selected_only=settings.project.export_selected_only,
            check_weights=settings.export.check_weights,
            max_influences=settings.export.max_influences,
        )
        apply_analysis_to_settings(context, result)
        summary = result["summary"]
        level = {"WARNING"} if summary["errors"] else set()
        self.report(
            level or {"INFO"},
            f"{summary['armatures']} armatures, {summary['bones']} bones, "
            f"{summary['constraints']} constraints, {summary['animation_clips']} animations",
        )
        return {"FINISHED"}


class URB_OT_focus_bone(Operator):
    bl_idname = "urb.focus_bone"
    bl_label = "Focus Bone"
    bl_description = "Select the armature and reveal the selected bone in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    armature: StringProperty()
    bone: StringProperty()

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature)
        if armature_obj is None or armature_obj.type != "ARMATURE":
            self.report({"ERROR"}, "Armature no longer exists")
            return {"CANCELLED"}
        if armature_obj.data is None or self.bone not in armature_obj.data.bones:
            self.report({"ERROR"}, "Bone no longer exists")
            return {"CANCELLED"}
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in context.selected_objects:
            obj.select_set(False)
        armature_obj.select_set(True)
        context.view_layer.objects.active = armature_obj
        armature_obj.data.bones.active = armature_obj.data.bones[self.bone]
        if not armature_obj.data.bones[self.bone].select:
            for bone in armature_obj.data.bones:
                bone.select = False
            armature_obj.data.bones[self.bone].select = True
        try:
            bpy.ops.object.mode_set(mode="POSE")
        except RuntimeError:
            pass
        region = _find_view3d(context)
        if region is not None:
            try:
                bpy.ops.view3d.view_selected()
            except RuntimeError:
                pass
        return {"FINISHED"}


def _find_view3d(context):
    for area in context.screen.areas if context.screen else []:
        if area.type == "VIEW_3D":
            for region in area.regions:
                if region.type == "WINDOW":
                    return region
    return None


class URB_OT_apply_classification(Operator):
    bl_idname = "urb.apply_classification"
    bl_label = "Use Automatic Classification"
    bl_description = "Restore the automatic bone classification for the selected bone"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1)

    def execute(self, context):
        settings = context.scene.urb
        item = settings.bones[self.index] if 0 <= self.index < len(settings.bones) else None
        if item is None:
            self.report({"WARNING"}, "No bone selected")
            return {"CANCELLED"}
        item.bone_type = item.auto_type
        item.override = False
        return {"FINISHED"}


class URB_OT_override_bone_type(Operator):
    bl_idname = "urb.override_bone_type"
    bl_label = "Override Bone Type"
    bl_description = "Store a manual classification for the selected bone (metadata only)"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1)
    bone_type: StringProperty(default="UNKNOWN")

    def execute(self, context):
        settings = context.scene.urb
        item = settings.bones[self.index] if 0 <= self.index < len(settings.bones) else None
        if item is None:
            self.report({"WARNING"}, "No bone selected")
            return {"CANCELLED"}
        item.bone_type = self.bone_type
        item.override = True
        return {"FINISHED"}


class URB_OT_select_all_animations(Operator):
    bl_idname = "urb.select_all_animations"
    bl_label = "Select All Animations"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for item in context.scene.urb.animations:
            item.export_enabled = True
        return {"FINISHED"}


class URB_OT_deselect_all_animations(Operator):
    bl_idname = "urb.deselect_all_animations"
    bl_label = "Deselect All Animations"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for item in context.scene.urb.animations:
            item.export_enabled = False
        return {"FINISHED"}


class URB_OT_preview_animation(Operator):
    bl_idname = "urb.preview_animation"
    bl_label = "Set Scene Range"
    bl_description = "Set the scene frame range to the selected animation without changing its data"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1)

    def execute(self, context):
        settings = context.scene.urb
        item = settings.animations[self.index] if 0 <= self.index < len(settings.animations) else None
        if item is None:
            self.report({"WARNING"}, "No animation selected")
            return {"CANCELLED"}
        scene = context.scene
        scene.frame_start = item.start
        scene.frame_end = item.end
        scene.frame_set(item.start)
        return {"FINISHED"}


class URB_OT_export(Operator):
    bl_idname = "urb.export_to_unreal"
    bl_label = "Export to Unreal Engine"
    bl_description = "Bake selected animations and write the URB package"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.urb
        settings.last_export_status = "Exporting..."
        try:
            result = export_package(context, settings, progress=_progress)
        except (ExportError, BakeError) as error:
            settings.last_export_status = f"Export failed: {error}"
            urb_log.error(str(error))
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except Exception as error:  # Surface unexpected failures without crashing Blender.
            settings.last_export_status = f"Export failed: {error}"
            urb_log.error(str(error))
            self.report({"ERROR"}, f"Export failed: {error}")
            return {"CANCELLED"}
        settings.last_package = result["path"]
        settings.last_export_status = (
            f"Exported {len(result['animations'])} clip(s), {len(result['meshes'])} mesh(es)"
        )
        self.report({"INFO"}, f"Package: {result['path']}")
        try:
            bpy.ops.ui.reports_to_textblock()
        except Exception:
            pass
        return {"FINISHED"}


def _progress(message, fraction):
    try:
        import bpy
        bpy.context.workspace.status_text_set(f"Universal Rig Bridge: {message}")
    except Exception:
        pass


class URB_OT_clear_analysis(Operator):
    bl_idname = "urb.clear_analysis"
    bl_label = "Clear Analysis"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.urb
        settings.bones.clear()
        settings.constraints.clear()
        settings.animations.clear()
        settings.issues.clear()
        settings.armatures.clear()
        settings.summary.analysed = False
        settings.summary.status = "Not analysed"
        return {"FINISHED"}


class URB_OT_open_package_folder(Operator):
    bl_idname = "urb.open_package_folder"
    bl_label = "Open Export Folder"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        path = bpy.path.abspath(context.scene.urb.project.export_directory or "//")
        if not os.path.isdir(path):
            self.report({"ERROR"}, "Export folder does not exist")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        return {"FINISHED"}


classes = (
    URB_OT_select_export_directory,
    URB_OT_analyse_rig,
    URB_OT_focus_bone,
    URB_OT_apply_classification,
    URB_OT_override_bone_type,
    URB_OT_select_all_animations,
    URB_OT_deselect_all_animations,
    URB_OT_preview_animation,
    URB_OT_export,
    URB_OT_clear_analysis,
    URB_OT_open_package_folder,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
