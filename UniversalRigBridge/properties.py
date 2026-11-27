"""Scene-level settings and cached analysis data for Universal Rig Bridge."""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from .constants import (
    ANIMATION_SOURCES,
    BONE_TYPES,
    COORDINATE_SYSTEMS,
    CONSTRAINT_CATEGORIES,
    DEFAULT_MAX_INFLUENCES,
    EXPORT_FORMATS,
    SAMPLE_MODES,
    UNREAL_VERSIONS,
)


class URB_ProjectSettings(PropertyGroup):
    project_name: StringProperty(
        name="Project Name",
        description="Name used for the exported package and manifest",
        default="MyProject",
    )
    export_directory: StringProperty(
        name="Export Directory",
        description="Folder that receives the .urb package",
        subtype="DIR_PATH",
        default="//",
    )
    unreal_version: EnumProperty(
        name="Unreal Version",
        description="Target Unreal Engine version recorded in the manifest",
        items=UNREAL_VERSIONS,
        default="5.8",
    )
    export_format: EnumProperty(
        name="Export Format",
        description="Container written by the exporter",
        items=EXPORT_FORMATS,
        default="URB",
    )
    coordinate_system: EnumProperty(
        name="Coordinate System",
        description="Axis conversion applied to exported transforms",
        items=COORDINATE_SYSTEMS,
        default="UNREAL",
    )
    auto_unit_scale: BoolProperty(
        name="Automatic Unit Scale",
        description="Use scene unit scale (Blender metres to Unreal centimetres)",
        default=True,
    )
    unit_scale: FloatProperty(
        name="Unit Scale",
        description="Manual multiplier applied to exported translations",
        default=100.0,
        min=0.0001,
        soft_max=1000.0,
    )
    export_selected_only: BoolProperty(
        name="Export Selected Only",
        description="Restrict analysis and export to selected objects and their rigs",
        default=False,
    )
    export_fps: IntProperty(
        name="Export FPS",
        description="Framerate written to animation data",
        default=30,
        min=1,
        max=240,
    )
    use_scene_fps: BoolProperty(
        name="Use Scene FPS",
        description="Read the framerate from the scene at export time",
        default=True,
    )

    @property
    def resolved_fps(self):
        scene = bpy.context.scene
        if self.use_scene_fps and scene is not None:
            return max(1, round(scene.render.fps / max(0.001, scene.render.fps_base)))
        return self.export_fps


class URB_ExportSettings(PropertyGroup):
    export_skeletal_mesh: BoolProperty(
        name="Export Skeletal Mesh",
        description="Export skinned meshes as FBX alongside the rig metadata",
        default=True,
    )
    export_skeleton: BoolProperty(
        name="Export Skeleton",
        description="Write skeleton.json and reference bone transforms",
        default=True,
    )
    export_animations: BoolProperty(
        name="Export Animations",
        description="Bake and write animation clips",
        default=True,
    )
    export_root_motion: BoolProperty(
        name="Export Root Motion",
        description="Extract root motion tracks from the selected root bone",
        default=False,
    )
    export_bone_metadata: BoolProperty(
        name="Export Bone Metadata",
        description="Write the bone classification and hierarchy report",
        default=True,
    )
    bake_object_transforms: BoolProperty(
        name="Bake Object Transforms",
        description="Include object-level transform animation for the rig",
        default=True,
    )
    export_all_actions: BoolProperty(
        name="Export All Actions",
        description="Export every detected action regardless of per-clip Enable flags",
        default=False,
    )
    export_deform_only: BoolProperty(
        name="Deform Bones Only",
        description="Export the deform/root skeleton only; control and mechanism bones remain metadata",
        default=True,
    )
    max_influences: IntProperty(
        name="Max Influences",
        description="Maximum bone influences per vertex expected by Unreal",
        default=DEFAULT_MAX_INFLUENCES,
        min=1,
        max=12,
    )
    check_weights: BoolProperty(
        name="Validate Weights",
        description="Report invalid or excessive bone influences",
        default=True,
    )


class URB_SampleSettings(PropertyGroup):
    sample_mode: EnumProperty(
        name="Sampling",
        description="How animation samples are generated",
        items=SAMPLE_MODES,
        default="EVERY_FRAME",
    )
    custom_fps: IntProperty(name="Custom FPS", default=30, min=1, max=240)
    frame_interval: IntProperty(name="Frame Interval", default=2, min=1, max=120)
    translation_tolerance: FloatProperty(
        name="Translation Tolerance",
        description="Maximum positional error kept by adaptive sampling (Unreal units)",
        default=0.1,
        min=0.0,
        precision=4,
    )
    rotation_tolerance: FloatProperty(
        name="Rotation Tolerance",
        description="Maximum angular error kept by adaptive sampling (degrees)",
        default=0.5,
        min=0.0,
        precision=3,
    )
    scale_tolerance: FloatProperty(
        name="Scale Tolerance",
        default=0.005,
        min=0.0,
        precision=4,
    )


class URB_RootMotionSettings(PropertyGroup):
    root_bone: StringProperty(
        name="Root Bone",
        description="Bone whose motion is written to the root motion track",
        default="root",
    )
    extract_translation: BoolProperty(name="Extract Translation", default=True)
    extract_rotation: BoolProperty(name="Extract Rotation", default=True)
    extract_full: BoolProperty(
        name="Extract Full Transform",
        description="Extract translation, rotation and scale",
        default=False,
    )
    keep_in_pose: BoolProperty(
        name="Keep Root Motion in Pose",
        description="Keep extracted motion on the pose bone as well as the root track",
        default=True,
    )


class URB_AnalysisSummary(PropertyGroup):
    armatures: IntProperty(default=0)
    bones: IntProperty(default=0)
    deform_bones: IntProperty(default=0)
    control_bones: IntProperty(default=0)
    mechanism_bones: IntProperty(default=0)
    helper_bones: IntProperty(default=0)
    meshes: IntProperty(default=0)
    constraints: IntProperty(default=0)
    drivers: IntProperty(default=0)
    actions: IntProperty(default=0)
    nla_tracks: IntProperty(default=0)
    nla_strips: IntProperty(default=0)
    warnings: IntProperty(default=0)
    errors: IntProperty(default=0)
    analysed: BoolProperty(default=False)
    status: StringProperty(default="Not analysed")
    analysed_at: StringProperty(default="")


class URB_IssueItem(PropertyGroup):
    severity: StringProperty(default="info")
    message: StringProperty(default="")
    context: StringProperty(default="")


class URB_ArmatureItem(PropertyGroup):
    name: StringProperty()
    data_name: StringProperty()
    bone_count: IntProperty()
    mesh_count: IntProperty()
    deform_count: IntProperty()
    action_hint: StringProperty()


class URB_BoneItem(PropertyGroup):
    name: StringProperty()
    armature: StringProperty()
    parent: StringProperty()
    children: StringProperty()
    auto_type: EnumProperty(items=BONE_TYPES, default="UNKNOWN")
    bone_type: EnumProperty(
        name="Type",
        description="Exported classification; does not modify the armature",
        items=BONE_TYPES,
        default="UNKNOWN",
    )
    deform: BoolProperty(default=False)
    connected: BoolProperty(default=False)
    depth: IntProperty(default=0)
    collections: StringProperty()
    head: FloatVectorProperty(size=3)
    tail: FloatVectorProperty(size=3)
    length: FloatProperty()
    rest_display: StringProperty()
    pose_display: StringProperty()
    override: BoolProperty(default=False)


class URB_ConstraintItem(PropertyGroup):
    name: StringProperty()
    armature: StringProperty()
    owner: StringProperty()
    owner_kind: StringProperty(default="BONE")
    constraint_type: StringProperty()
    target: StringProperty()
    influence: FloatProperty()
    enabled: BoolProperty()
    category: EnumProperty(items=CONSTRAINT_CATEGORIES, default="BAKED")
    channels: StringProperty()
    dependencies: StringProperty()
    note: StringProperty()


class URB_AnimationItem(PropertyGroup):
    key: StringProperty()
    name: StringProperty()
    source: EnumProperty(items=ANIMATION_SOURCES, default="ACTION")
    armature: StringProperty()
    action: StringProperty()
    slot_identifier: StringProperty()
    nla_track: StringProperty()
    nla_strip: StringProperty()
    start: IntProperty()
    end: IntProperty()
    sample_rate: FloatProperty(
        name="Clip Rate",
        description="Exported key rate. 0 follows the scene frame rate",
        default=0.0,
        min=0.0,
        max=240.0,
    )
    sample_mode: EnumProperty(items=SAMPLE_MODES, default="EVERY_FRAME")
    looping: BoolProperty(default=False)
    root_motion: BoolProperty(default=False)
    compression: BoolProperty(default=True)
    export_enabled: BoolProperty(default=True)
    duration_seconds: FloatProperty()
    animated_objects: StringProperty()
    animated_bones: IntProperty()
    frame_count: IntProperty()


class URB_URBSettings(PropertyGroup):
    project: PointerProperty(type=URB_ProjectSettings)
    export: PointerProperty(type=URB_ExportSettings)
    samples: PointerProperty(type=URB_SampleSettings)
    root_motion: PointerProperty(type=URB_RootMotionSettings)
    summary: PointerProperty(type=URB_AnalysisSummary)
    armatures: CollectionProperty(type=URB_ArmatureItem)
    bones: CollectionProperty(type=URB_BoneItem)
    constraints: CollectionProperty(type=URB_ConstraintItem)
    animations: CollectionProperty(type=URB_AnimationItem)
    issues: CollectionProperty(type=URB_IssueItem)

    bone_index: IntProperty(default=0)
    constraint_index: IntProperty(default=0)
    animation_index: IntProperty(default=0)
    armature_index: IntProperty(default=0)
    bone_filter: StringProperty(name="Filter", default="")
    show_only_deform: BoolProperty(name="Deform Only", default=False)
    constraint_filter: EnumProperty(
        name="Show",
        items=(
            ("ALL", "All", ""),
            ("SUPPORTED", "Supported", ""),
            ("BAKED", "Baked", ""),
            ("UNSUPPORTED", "Unsupported", ""),
        ),
        default="ALL",
    )
    last_package: StringProperty(default="")
    last_export_status: StringProperty(default="")


classes = (
    URB_ProjectSettings,
    URB_ExportSettings,
    URB_SampleSettings,
    URB_RootMotionSettings,
    URB_AnalysisSummary,
    URB_IssueItem,
    URB_ArmatureItem,
    URB_BoneItem,
    URB_ConstraintItem,
    URB_AnimationItem,
    URB_URBSettings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.urb = PointerProperty(type=URB_URBSettings)


def unregister():
    if hasattr(bpy.types.Scene, "urb"):
        del bpy.types.Scene.urb
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
