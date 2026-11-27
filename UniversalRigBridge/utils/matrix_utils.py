"""Matrix serialisation, interpolation and comparison utilities."""

from __future__ import annotations

import math

from mathutils import Matrix, Quaternion, Vector


def round_vector(vector, digits=7):
    return [round(float(value), digits) for value in vector]


def round_matrix(matrix, digits=7):
    # Row-major so JSON consumers do not need to know Blender internals.
    return [round(float(matrix[row][col]), digits) for row in range(4) for col in range(4)]


def matrix_from_rows(rows):
    """Rebuild a matrix from the row-major list produced by round_matrix."""
    if len(rows) != 16:
        raise ValueError("A 4x4 matrix requires 16 values")
    return Matrix([rows[index:index + 4] for index in range(0, 16, 4)])


def decompose(matrix):
    location, rotation, scale = matrix.decompose()
    return location, rotation, scale


def is_uniform_scale(scale, tolerance=1e-5):
    return (
        abs(abs(scale.x) - abs(scale.y)) <= tolerance
        and abs(abs(scale.y) - abs(scale.z)) <= tolerance
    )


def has_shear(matrix, tolerance=1e-4):
    axes = [matrix.to_3x3().col[index].normalized() for index in range(3)]
    return any(abs(axes[i].dot(axes[j])) > tolerance for i in range(3) for j in range(i + 1, 3))


def quaternion_continuity(previous, current):
    """Return a quaternion in the same hemisphere as previous."""
    if previous is not None and previous.dot(current) < 0.0:
        return Quaternion((-current.w, -current.x, -current.y, -current.z))
    return current.copy()


def matrix_delta(a, b):
    """Largest absolute component difference between two 4x4 matrices."""
    return max(abs(a[row][col] - b[row][col]) for row in range(4) for col in range(4))


def translation_delta(a, b):
    return (a.translation - b.translation).length


def rotation_delta(a, b):
    qa = a.to_quaternion().normalized()
    qb = b.to_quaternion().normalized()
    dot = min(1.0, max(-1.0, abs(qa.dot(qb))))
    return 2.0 * math.acos(dot)


def scale_delta(a, b):
    """Largest difference between the decomposed scale channels."""
    scale_a = a.to_scale()
    scale_b = b.to_scale()
    return max(abs(scale_a[axis] - scale_b[axis]) for axis in range(3))


def lerp_matrix(a, b, factor):
    """Interpolate an affine matrix with translation lerp and rotation slerp."""
    la, ra, sa = a.decompose()
    lb, rb, sb = b.decompose()
    location = la.lerp(lb, factor)
    rotation = ra.slerp(rb, factor)
    scale = sa.lerp(sb, factor)
    return Matrix.LocRotScale(location, rotation, scale)


def transform_error(a, b, rotation_weight=1.0, scale_weight=1.0):
    return max(
        translation_delta(a, b),
        rotation_delta(a, b) * rotation_weight,
        scale_delta(a, b) * scale_weight,
    )


def safe_invert(matrix):
    try:
        return matrix.inverted()
    except ValueError:
        return Matrix.Identity(4)
