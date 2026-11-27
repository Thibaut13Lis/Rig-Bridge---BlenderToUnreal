"""Frame sampling primitives.

Samples are captured from the evaluated dependency graph and copied into plain
Python floats before the scene advances.  A sample transform is the bone-local
pose matrix (parent-relative), converted to the export coordinate system, which
is the same convention Unreal uses for bone animation tracks when paired with
the exported reference skeleton.
"""

from __future__ import annotations

import bpy
from mathutils import Matrix, Quaternion, Vector

from ..utils.coordinate_conversion import convert_matrix
from ..utils.matrix_utils import lerp_matrix, rotation_delta, scale_delta
from ..utils import logging as urb_log


def frame_samples(start, end, mode="EVERY_FRAME", custom_fps=30, scene_fps=30, interval=2):
    """Return scene frame positions (float) for a clip.

    Every mode keeps the first and last frame of the range so the clip duration
    is preserved.  Reduced rates are spread evenly across the range instead of
    stepping and appending a leftover frame, because Unreal evaluates keys at a
    uniform rate: uneven spacing would shift the sampled timing.
    """
    start = float(start)
    end = float(end)
    if end <= start:
        return [start]
    if mode in ("CUSTOM_FPS", "CUSTOM_INTERVAL"):
        source_fps = max(1.0, float(scene_fps))
        duration = (end - start) / source_fps
        if mode == "CUSTOM_FPS":
            target_fps = max(1, int(custom_fps))
        else:
            step = max(1, int(interval))
            target_fps = max(1, int(round(source_fps / step)))
        if target_fps >= source_fps:
            return [float(frame) for frame in range(int(start), int(end) + 1)]
        # Number of uniform intervals that best matches the requested rate.
        intervals = max(1, int(round(duration * target_fps)))
        step = (end - start) / intervals
        return [start + step * index for index in range(intervals + 1)]
    return [float(frame) for frame in range(int(start), int(end) + 1)]


def set_scene_frame(scene, frame):
    whole = int(frame)
    subframe = frame - whole
    if subframe > 1e-6:
        scene.frame_set(whole, subframe=subframe)
    else:
        scene.frame_set(whole)


class EvaluatedPoseReader:
    """Reads evaluated bone matrices and converts them to bone-local exports."""

    def __init__(self, armature_obj, bone_order, unit_scale=1.0):
        self.armature_obj = armature_obj
        self.bone_order = list(bone_order)
        self.set_order = set(self.bone_order)
        self.unit_scale = unit_scale
        self.parent_map = {}
        self.fallback_ancestor = {}
        self.rest_local = {}
        data = armature_obj.data
        for name in self.bone_order:
            bone = data.bones.get(name)
            if bone is None:
                self.parent_map[name] = ""
                self.fallback_ancestor[name] = ""
                self.rest_local[name] = Matrix.Identity(4)
                continue
            parent = bone.parent
            self.parent_map[name] = parent.name if parent else ""
            ancestor = parent
            while ancestor is not None and ancestor.name not in self.set_order:
                ancestor = ancestor.parent
            self.fallback_ancestor[name] = ancestor.name if ancestor else ""
            if ancestor is not None:
                # Nearest exported ancestor, mirroring the exported skeleton.
                rest = ancestor.matrix_local.inverted() @ bone.matrix_local
            else:
                rest = bone.matrix_local.copy()
            self.rest_local[name] = rest

    def reference_local(self, name):
        return convert_matrix(self.rest_local.get(name, Matrix.Identity(4)), self.unit_scale)

    def read(self):
        """Return (locals, world_matrices, object_matrix) in Unreal space."""
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = self.armature_obj.evaluated_get(depsgraph)
        pose = evaluated.pose
        object_matrix = convert_matrix(evaluated.matrix_world.copy(), self.unit_scale)
        world = {}
        for name in self.bone_order:
            pose_bone = pose.bones.get(name)
            if pose_bone is None:
                world[name] = object_matrix
            else:
                world[name] = convert_matrix(evaluated.matrix_world @ pose_bone.matrix, self.unit_scale)

        # Parent-relative values must be computed in Blender space before
        # conversion, otherwise the unit scale would be applied twice.
        converted = {}
        raw_world = {}
        for name in self.bone_order:
            pose_bone = pose.bones.get(name)
            if pose_bone is None:
                raw_world[name] = Matrix.Identity(4)
            else:
                raw_world[name] = pose_bone.matrix.copy()
        for name in self.bone_order:
            ancestor = self.fallback_ancestor[name]
            if ancestor:
                local = raw_world[ancestor].inverted() @ raw_world[name]
            else:
                local = raw_world[name]
            try:
                converted[name] = convert_matrix(local, self.unit_scale)
            except ValueError:
                converted[name] = Matrix.Identity(4)
        return converted, world, object_matrix


def matrix_to_tqs(matrix):
    location, rotation, scale = matrix.decompose()
    if rotation.w < 0.0:
        rotation = Quaternion((-rotation.w, -rotation.x, -rotation.y, -rotation.z))
    return (tuple(location), tuple(rotation), tuple(scale))


def simplify_samples(matrices_per_frame, frames, bone_order, translation_tolerance=0.1, rotation_tolerance_degrees=0.5, scale_tolerance=0.005, max_keys=20000):
    """Ramer-Douglas-Peucker reduction across every bone simultaneously.

    matrices_per_frame: one {bone: Matrix} mapping per evaluated sample.
    Returns sorted sample indices to keep.  Error is normalised per channel so
    a value of 1.0 means "exactly at tolerance".
    """
    count = len(matrices_per_frame)
    if count <= 2:
        return list(range(count))

    rotation_tolerance = max(1e-9, rotation_tolerance_degrees * 3.141592653589793 / 180.0)
    translation_tolerance = max(1e-9, float(translation_tolerance))
    scale_tolerance = max(1e-9, float(scale_tolerance))
    keep = {0, count - 1}

    def sample_error(start_index, end_index, index):
        factor = (index - start_index) / (end_index - start_index)
        start_matrices = matrices_per_frame[start_index]
        end_matrices = matrices_per_frame[end_index]
        actual_matrices = matrices_per_frame[index]
        worst = 0.0
        for name in bone_order:
            start = start_matrices[name]
            end = end_matrices[name]
            actual = actual_matrices[name]
            interpolated = lerp_matrix(start, end, factor)
            worst = max(
                worst,
                (interpolated.translation - actual.translation).length / translation_tolerance,
                rotation_delta(interpolated, actual) / rotation_tolerance,
                scale_delta(interpolated, actual) / scale_tolerance,
            )
            if worst > 1.0:
                return worst
        return worst

    def refine(start_index, end_index):
        if end_index - start_index <= 1 or len(keep) >= max_keys:
            return
        worst_index = -1
        worst_error = 0.0
        for index in range(start_index + 1, end_index):
            error = sample_error(start_index, end_index, index)
            if error > worst_error:
                worst_error = error
                worst_index = index
        if worst_error > 1.0 and worst_index > start_index:
            keep.add(worst_index)
            refine(start_index, worst_index)
            refine(worst_index, end_index)

    import sys

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, count * 2 + 100))
    try:
        refine(0, count - 1)
    finally:
        sys.setrecursionlimit(limit)

    if len(keep) >= max_keys:
        urb_log.warning(f"Adaptive sampling reached the {max_keys} key cap")
    return sorted(keep)


def clip_time(frame, start, fps):
    return (float(frame) - float(start)) / max(1.0, float(fps))
