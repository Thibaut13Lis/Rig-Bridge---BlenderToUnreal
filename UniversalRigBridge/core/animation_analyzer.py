"""Action, slot and NLA discovery using the Blender 4.4+/5.x animation API."""

from __future__ import annotations

import bpy


def action_fcurves(action, slot=None):
    """Return fcurves for a legacy or layered action.

    Blender 5.x stores curves in layers/strips/channelbags keyed by slot handle.
    Legacy actions still expose action.fcurves, which the fallback covers.
    """
    curves = []
    slots = getattr(action, "slots", None)
    layers = getattr(action, "layers", None)
    if layers is not None and len(layers) > 0:
        for layer in layers:
            for strip in layer.strips:
                try:
                    channelbags = list(strip.channelbags)
                except AttributeError:
                    continue
                for bag in channelbags:
                    if slot is not None:
                        if getattr(bag, "slot", None) != slot and getattr(bag, "slot_handle", None) != getattr(slot, "handle", None):
                            continue
                    curves.extend(list(bag.fcurves))
        return curves
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        curves.extend(list(legacy))
    return curves


def action_slots(action):
    """Return (slot, label) pairs, including the synthetic legacy slot."""
    slots = getattr(action, "slots", None)
    if slots is not None and len(slots) > 0:
        return [(slot, slot.name_display or slot.identifier) for slot in slots]
    return [(None, "Legacy")]


def slot_for_object(action, obj):
    """Find a slot that can be assigned to obj, or None for legacy actions."""
    slots = getattr(action, "slots", None)
    if slots is None or len(slots) == 0:
        return None
    animation_data = obj.animation_data
    if animation_data is not None and animation_data.action == action and animation_data.action_slot is not None:
        return animation_data.action_slot
    preferred = getattr(obj, "name", "")
    for slot in slots:
        if slot.target_id_type == "OBJECT" and (slot.name_display == preferred or slot.identifier.endswith(preferred)):
            return slot
    for slot in slots:
        if slot.target_id_type == "OBJECT":
            return slot
    return slots[0]


def assign_action(obj, action, slot=None):
    animation_data = obj.animation_data_create()
    animation_data.action = action
    if action is not None and hasattr(animation_data, "action_slot"):
        resolved = slot or slot_for_object(action, obj)
        if resolved is not None:
            animation_data.action_slot = resolved
    return animation_data


def clear_action(obj):
    animation_data = obj.animation_data
    if animation_data is None:
        return
    animation_data.action = None
    if hasattr(animation_data, "action_slot"):
        try:
            animation_data.action_slot = None
        except (TypeError, RuntimeError):
            pass


def action_frame_range(action, fallback=(1, 1)):
    try:
        start, end = action.frame_range
        if end >= start:
            return int(round(start)), int(round(end))
    except (AttributeError, ValueError, TypeError):
        pass
    if getattr(action, "use_frame_range", False):
        return int(round(action.frame_start)), int(round(action.frame_end))
    return fallback


def fcurve_bone_names(curves):
    names = set()
    prefix = 'pose.bones["'
    for curve in curves:
        path = curve.data_path
        if path.startswith(prefix):
            end = path.find('"]', len(prefix))
            if end != -1:
                names.add(path[len(prefix):end])
    return names


def action_uses_object_transform(curves):
    return any(not curve.data_path.startswith('pose.bones[') for curve in curves)


def animation_records(context):
    """Discover actions, slots and NLA strips without relying on the active action."""
    records = []
    seen = set()
    scene = context.scene
    default_range = (scene.frame_start, scene.frame_end)

    for action in bpy.data.actions:
        slots = action_slots(action)
        for slot, slot_label in slots:
            curves = action_fcurves(action, slot)
            if not curves:
                continue
            start, end = action_frame_range(action, default_range)
            record = {
                "key": f"action:{action.name}:{slot.identifier if slot else 'legacy'}",
                "name": action.name if len(slots) == 1 else f"{action.name} [{slot_label}]",
                "source": "ACTION",
                "action": action.name,
                "slot_identifier": slot.identifier if slot else "",
                "slot_handle": slot.handle if slot else 0,
                "nla_track": "",
                "nla_strip": "",
                "start": start,
                "end": end,
                "frame_count": max(0, end - start + 1),
                "animated_bones": len(fcurve_bone_names(curves)),
                "animated_objects": 1,
                "bone_names": sorted(fcurve_bone_names(curves)),
                "has_object_curves": action_uses_object_transform(curves),
            }
            records.append(record)
            seen.add(record["key"])

    for armature in (obj for obj in scene.objects if obj.type == "ARMATURE"):
        animation_data = armature.animation_data
        if animation_data is None:
            continue
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action is None:
                    continue
                action = strip.action
                slot = getattr(strip, "action_slot", None)
                curves = action_fcurves(action, slot)
                if not curves:
                    continue
                start = int(round(strip.frame_start))
                end = int(round(strip.frame_end))
                key = f"nla:{armature.name}:{track.name}:{strip.name}"
                if key in seen:
                    continue
                records.append(
                    {
                        "key": key,
                        "name": f"{strip.name}",
                        "source": "NLA",
                        "armature": armature.name,
                        "action": action.name,
                        "slot_identifier": slot.identifier if slot else "",
                        "slot_handle": slot.handle if slot else 0,
                        "nla_track": track.name,
                        "nla_strip": strip.name,
                        "start": start,
                        "end": end,
                        "frame_count": max(0, end - start + 1),
                        "animated_bones": len(fcurve_bone_names(curves)),
                        "animated_objects": 1,
                        "bone_names": sorted(fcurve_bone_names(curves)),
                        "has_object_curves": action_uses_object_transform(curves),
                    }
                )

    records.sort(key=lambda item: (item["source"], item["name"].lower()))
    return records


def detect_animation_properties(obj):
    """Describe animation capability and layers present on an object."""
    animation_data = obj.animation_data
    if animation_data is None:
        return {"has_animation_data": False, "nla_tracks": 0, "action": ""}
    tracks = len(animation_data.nla_tracks)
    action = animation_data.action.name if animation_data.action else ""
    nla_strips = sum(len(track.strips) for track in animation_data.nla_tracks)
    return {
        "has_animation_data": True,
        "action": action,
        "action_slot": getattr(getattr(animation_data, "action_slot", None), "identifier", ""),
        "nla_tracks": tracks,
        "nla_strips": nla_strips,
        "use_nla": bool(animation_data.use_nla),
        "drivers": len(animation_data.drivers),
    }
