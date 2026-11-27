"""Binary .urbanim animation format (format version 1).

Layout (all little-endian):

    magic            8 bytes   b"URBANIM\0"
    version          u16
    flags            u16
    header_size      u32
    bone_count       u32
    sample_count     u32
    fps              f32
    start_frame      f32
    end_frame        f32
    json_length      u32
    json_bytes       json_length bytes   (UTF-8, no padding)
    bone table       bone_count * u32 length-prefixed UTF-8 names
    track data       sample_count * bone_count *
                     (3*f32 translation, 4*f32 quaternion [w,x,y,z], 3*f32 scale)
    root motion      u8 present, then (if present) sample_count * (10*f32)
                     translation(3), quaternion(4), scale(3)

The format is self-describing and can be decoded without Blender.  Timestamps
are stored in the header JSON so absolute frame values are recoverable.
"""

from __future__ import annotations

import struct

from ..constants import ANIMATION_FORMAT, ANIMATION_VERSION

MAGIC = b"URBANIM\0"
_HEADER = struct.Struct("<8sHHIIIIfffI")
_SAMPLE = struct.Struct("<10f")
_ROOT = struct.Struct("<10f")


def encode_animation(clip):
    bone_order = list(clip["bone_order"])
    tracks = {track["name"]: track for track in clip["tracks"]}
    sample_count = int(clip["sample_count"])
    header = {
        "format": ANIMATION_FORMAT,
        "version": ANIMATION_VERSION,
        "name": clip["name"],
        "fps": clip["fps"],
        "start_frame": clip["start_frame"],
        "end_frame": clip["end_frame"],
        "source": clip["source"],
        "source_frames": list(clip["source_frames"]),
        "timestamps": list(clip["timestamps"]),
        "bone_order": bone_order,
        "root_motion_bone": clip["root_motion"]["bone"],
        "object_reference": clip["object_reference"],
        "object_transforms": clip["object_transforms"],
    }
    import json

    json_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    bone_count = len(bone_order)
    body = bytearray()
    body.extend(struct.pack("<I", len(json_bytes)))
    body.extend(json_bytes)
    for name in bone_order:
        encoded = name.encode("utf-8")
        body.extend(struct.pack("<I", len(encoded)))
        body.extend(encoded)

    for sample in range(sample_count):
        for name in bone_order:
            track = tracks[name]
            location = track["translations"][sample]
            rotation = track["rotations"][sample]
            scale = track["scales"][sample]
            body.extend(
                _SAMPLE.pack(
                    location[0], location[1], location[2],
                    rotation[0], rotation[1], rotation[2], rotation[3],
                    scale[0], scale[1], scale[2],
                )
            )

    root = clip["root_motion"]
    if root["bone"]:
        body.extend(struct.pack("<B", 1))
        for sample in range(sample_count):
            location = root["translations"][sample]
            rotation = root["rotations"][sample]
            scale = root["scales"][sample]
            body.extend(
                _ROOT.pack(
                    location[0], location[1], location[2],
                    rotation[0], rotation[1], rotation[2], rotation[3],
                    scale[0], scale[1], scale[2],
                )
            )
    else:
        body.extend(struct.pack("<B", 0))

    header_size = _HEADER.size
    prefix = _HEADER.pack(
        MAGIC,
        ANIMATION_VERSION,
        0,
        header_size,
        bone_count,
        sample_count,
        len(json_bytes),
        float(clip["fps"]),
        float(clip["start_frame"]),
        float(clip["end_frame"]),
        0,
    )
    return bytes(prefix) + bytes(body)


def decode_animation(data):
    """Reference decoder used by tests and external tools."""
    import json

    if len(data) < _HEADER.size:
        raise ValueError("Animation data is too short")
    (magic, version, flags, header_size, bone_count, sample_count, json_length,
     fps, start_frame, end_frame, reserved) = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError("Not a URB animation")
    if version != ANIMATION_VERSION:
        raise ValueError(f"Unsupported animation version {version}")
    offset = header_size
    if len(data) < offset + 4 + json_length:
        raise ValueError("Truncated animation header")
    embedded_length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if embedded_length != json_length:
        raise ValueError("Animation header length mismatch")
    header = json.loads(data[offset:offset + json_length].decode("utf-8"))
    offset += json_length
    names = []
    for _index in range(bone_count):
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        names.append(data[offset:offset + length].decode("utf-8"))
        offset += length
    samples = []
    for _sample in range(sample_count):
        frame = {}
        for name in names:
            values = _SAMPLE.unpack_from(data, offset)
            offset += _SAMPLE.size
            frame[name] = {
                "translation": values[0:3],
                "rotation": values[3:7],
                "scale": values[7:10],
            }
        samples.append(frame)
    root = None
    if offset < len(data):
        present = data[offset]
        offset += 1
        if present:
            root = []
            for _sample in range(sample_count):
                values = _ROOT.unpack_from(data, offset)
                offset += _ROOT.size
                root.append(
                    {
                        "translation": values[0:3],
                        "rotation": values[3:7],
                        "scale": values[7:10],
                    }
                )
    return {
        "header": header,
        "bones": names,
        "samples": samples,
        "root_motion": root,
        "bytes_consumed": offset,
        "total_bytes": len(data),
    }
