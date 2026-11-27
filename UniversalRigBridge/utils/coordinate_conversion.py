"""Centralised Blender to Unreal coordinate conversion.

Blender: right handed, Z up, forward -Y, metres.
Unreal:  X forward, Y right, Z up, centimetres.

The basis change is a +90 degree rotation about Z:
    X_unreal = -Y_blender
    Y_unreal =  X_blender
    Z_unreal =  Z_blender

For affine transforms the similarity U = C * B * C^-1 is applied, which keeps
hierarchy composition valid (parent * local).  Units are applied as a separate
scalar so rotations and scales are not polluted by the metre/centimetre ratio.
"""

from __future__ import annotations

from mathutils import Matrix, Quaternion, Vector

BLENDER_TO_UNREAL = Matrix(
    (
        (0.0, -1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
)
UNREAL_TO_BLENDER = BLENDER_TO_UNREAL.inverted()

METRES_TO_CENTIMETRES = 100.0


def axis_matrix():
    return BLENDER_TO_UNREAL.copy()


def inverse_axis_matrix():
    return UNREAL_TO_BLENDER.copy()


def convert_vector(vector, unit_scale=1.0):
    v = BLENDER_TO_UNREAL.to_3x3() @ Vector(vector)
    if unit_scale != 1.0:
        v *= unit_scale
    return v


def convert_rotation(rotation, unit_scale=1.0):
    """Convert a quaternion by rotating its axis; unit scale is irrelevant."""
    axis, angle = rotation.to_axis_angle()
    return Quaternion(BLENDER_TO_UNREAL.to_3x3() @ axis, angle)


def convert_matrix(matrix, unit_scale=1.0):
    """Convert an affine matrix between coordinate systems."""
    result = BLENDER_TO_UNREAL @ matrix @ UNREAL_TO_BLENDER
    if unit_scale != 1.0:
        result.translation = result.translation * unit_scale
    return result


def convert_matrix_no_scale(matrix):
    return BLENDER_TO_UNREAL @ matrix @ UNREAL_TO_BLENDER


def convert_location(location, unit_scale=1.0):
    return convert_matrix(Matrix.Translation(location), unit_scale).translation


def convert_scale(scale):
    """Scales live on basis axes, so convert them as absolute magnitudes.

    Unreal and Blender both use Z up; the axis permutation can move a
    non-uniform scale between X and Y, so reorder explicitly.
    """
    return Vector((scale.y, scale.x, scale.z))


def convert_local_matrix(local_matrix, unit_scale=1.0):
    """Convert a bone-local transform.

    Local transforms are expressed relative to the parent bone's basis.  The
    parent and child are both re-oriented by the same basis change, therefore
    L' = C * L * C^-1.  Translation is scaled to Unreal units.
    """
    return convert_matrix(local_matrix, unit_scale)


def convert_armature_matrix(matrix, unit_scale=1.0):
    return convert_matrix(matrix, unit_scale)


def unit_scale_from_scene(scene, automatic=True, manual=1.0):
    if not automatic:
        return float(manual)
    # Blender units are metres; Unreal units are centimetres.
    return METRES_TO_CENTIMETRES * float(scene.unit_settings.scale_length or 1.0)


def roundtrip_error(matrix, unit_scale=1.0):
    """Diagnostic helper: convert to Unreal and back, return max error."""
    converted = convert_matrix(matrix, unit_scale)
    restored = convert_matrix(converted, 1.0 / unit_scale)
    return max(abs(restored[r][c] - matrix[r][c]) for r in range(4) for c in range(4))
