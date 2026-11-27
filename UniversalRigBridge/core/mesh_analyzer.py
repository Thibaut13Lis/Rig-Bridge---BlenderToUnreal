"""Mesh, skinning and modifier validation (read-only)."""

from __future__ import annotations

import bpy

from ..constants import DEFAULT_MAX_INFLUENCES


def armature_modifier(obj, armature_obj):
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object == armature_obj:
            return modifier
    return None


def mesh_record(obj, armature_obj):
    mesh = obj.data
    modifier = armature_modifier(obj, armature_obj)
    uv_maps = [layer.name for layer in mesh.uv_layers]
    materials = [slot.material.name if slot.material else "" for slot in obj.material_slots]
    modifier_records = []
    unsupported = []
    for candidate in obj.modifiers:
        record = {
            "name": candidate.name,
            "type": candidate.type,
            "show_viewport": bool(candidate.show_viewport),
            "show_render": bool(candidate.show_render),
        }
        if candidate.type == "ARMATURE":
            record["object"] = candidate.object.name if candidate.object else ""
            record["use_deform_preserve_volume"] = bool(getattr(candidate, "use_deform_preserve_volume", False))
        else:
            unsupported.append(candidate.type)
        modifier_records.append(record)
    return {
        "name": obj.name,
        "data_name": mesh.name,
        "vertex_count": len(mesh.vertices),
        "polygon_count": len(mesh.polygons),
        "triangle_count": sum(max(0, len(polygon.vertices) - 2) for polygon in mesh.polygons),
        "material_slots": materials,
        "uv_maps": uv_maps,
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "armature_modifier": modifier.name if modifier else "",
        "armature_modifier_settings": modifier_records,
        "unsupported_modifiers": sorted(set(unsupported)),
        "parent": obj.parent.name if obj.parent else "",
        "parent_type": obj.parent_type,
        "matrix_world": [list(row) for row in obj.matrix_world],
        "shape_keys": bool(mesh.shape_keys),
        "has_custom_normals": bool(getattr(mesh, "has_custom_normals", False)),
    }


def weight_report(obj, armature_obj, max_influences=DEFAULT_MAX_INFLUENCES):
    """Read-only skin weight validation. Nothing is modified."""
    mesh = obj.data
    bone_names = {bone.name for bone in armature_obj.data.bones}
    group_names = {group.index: group.name for group in obj.vertex_groups}
    invalid_groups = sorted(name for name in group_names.values() if name not in bone_names)

    unweighted = 0
    excessive = 0
    non_normalised = 0
    invalid_weights = 0
    maximum_seen = 0
    affected_vertices = set()

    for vertex in mesh.vertices:
        influences = [
            membership
            for membership in vertex.groups
            if membership.weight > 0.0 and group_names.get(membership.group) in bone_names
        ]
        if not influences:
            unweighted += 1
            affected_vertices.add(vertex.index)
            continue
        count = len(influences)
        maximum_seen = max(maximum_seen, count)
        if count > max_influences:
            excessive += 1
            affected_vertices.add(vertex.index)
        total = sum(membership.weight for membership in influences)
        if abs(total - 1.0) > 1e-3:
            non_normalised += 1
            affected_vertices.add(vertex.index)
        if any(membership.weight < 0.0 or membership.weight > 1.0 for membership in influences):
            invalid_weights += 1
            affected_vertices.add(vertex.index)

    return {
        "mesh": obj.name,
        "bone_group_count": len([name for name in group_names.values() if name in bone_names]),
        "invalid_vertex_groups": invalid_groups,
        "unweighted_vertices": unweighted,
        "vertices_over_influence_limit": excessive,
        "non_normalised_vertices": non_normalised,
        "invalid_weight_values": invalid_weights,
        "max_influences_seen": maximum_seen,
        "max_influences_allowed": max_influences,
        "affected_vertex_count": len(affected_vertices),
    }


def deform_bones_used(obj, armature_obj):
    used = set()
    for group in obj.vertex_groups:
        if group.name in armature_obj.data.bones:
            used.add(group.name)
    return sorted(used)
