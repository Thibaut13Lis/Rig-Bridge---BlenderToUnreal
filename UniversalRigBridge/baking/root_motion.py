"""Root motion extraction and pose cleanup."""

from __future__ import annotations

from mathutils import Matrix, Quaternion, Vector

from ..utils.coordinate_conversion import convert_matrix


def root_delta(first_world, current_world, extract_translation=True, extract_rotation=True, extract_scale=False):
    """Return an Unreal-space delta matrix relative to the first frame."""
    first_location, first_rotation, first_scale = first_world.decompose()
    location, rotation, scale = current_world.decompose()
    if not extract_translation:
        location = first_location
    if not extract_rotation:
        rotation = first_rotation
    if not extract_scale:
        scale = Vector((1.0, 1.0, 1.0))
    delta = Matrix.LocRotScale(first_location, first_rotation, first_scale).inverted() @ Matrix.LocRotScale(
        location, rotation, scale
    )
    if not extract_translation:
        delta.translation = (0.0, 0.0, 0.0)
    if not extract_rotation:
        delta = _strip_rotation(delta)
    if not extract_scale:
        delta = _strip_scale(delta)
    return delta


def _strip_rotation(matrix):
    location, _rotation, scale = matrix.decompose()
    return Matrix.LocRotScale(location, Quaternion((1, 0, 0, 0)), scale)


def _strip_scale(matrix):
    location, rotation, _scale = matrix.decompose()
    return Matrix.LocRotScale(location, rotation, Vector((1, 1, 1)))


def remove_root_motion(root_locals, extract_translation=True, extract_rotation=True, extract_scale=False):
    """Return root locals with the extracted root motion removed.

    The residual is computed relative to the first sample and only the
    *extracted* channels are reset.  With full extraction the root freezes at
    its first pose (the motion now lives solely in the root-motion track).
    Extracting translation only keeps the animated root rotation, which would
    otherwise be lost from the pose even though it was never extracted.
    """
    if not root_locals:
        return []
    first_local = root_locals[0]
    first_inverse = first_local.inverted()
    cleaned = []
    for local in root_locals:
        relative = first_inverse @ local
        location, rotation, scale = relative.decompose()
        if extract_translation:
            location = Vector((0.0, 0.0, 0.0))
        if extract_rotation:
            rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        if extract_scale:
            scale = Vector((1.0, 1.0, 1.0))
        cleaned.append(first_local @ Matrix.LocRotScale(location, rotation, scale))
    return cleaned


def root_motion_track(world_matrices, root_name, extract_translation=True, extract_rotation=True, extract_scale=False):
    """Return a list of Unreal-space delta matrices for each sample."""
    if not world_matrices:
        return []
    first = world_matrices[0]
    return [
        root_delta(first, world, extract_translation, extract_rotation, extract_scale)
        for world in world_matrices
    ]


def root_bone_candidates(armature_obj):
    candidates = []
    for bone in armature_obj.data.bones:
        if bone.parent is None:
            candidates.append(bone.name)
    return candidates


def choose_root_bone(armature_obj, preferred=""):
    if preferred and armature_obj.data and preferred in armature_obj.data.bones:
        return preferred
    roots = root_bone_candidates(armature_obj)
    if roots:
        lowered = {name.lower(): name for name in roots}
        for key in ("root", "rootbone", "root_bone", "master", "hips", "pelvis"):
            if key in lowered:
                return lowered[key]
        return roots[0]
    if armature_obj.data and len(armature_obj.data.bones) > 0:
        return armature_obj.data.bones[0].name
    return ""
