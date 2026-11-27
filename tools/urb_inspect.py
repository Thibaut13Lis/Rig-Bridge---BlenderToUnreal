"""Inspect a .urb package without Blender.

Usage:
    python tools/urb_inspect.py MyProject.urb
    python tools/urb_inspect.py MyProject.urb --animation Walk --frames 5
    python tools/urb_inspect.py MyProject.urb --json

This is a reference reader: it is intentionally dependency-free so it can run
with a plain CPython install (no Blender, no mathutils).  It documents the
.urbanim layout by parsing it, which makes it useful for verifying that the
exporter wrote what the manifest claims.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile

MAGIC = b"URBANIM\0"
HEADER = struct.Struct("<8sHHIIIIfffI")
SAMPLE = struct.Struct("<10f")


def read_urbanim(data):
    """Decode one .urbanim payload into plain Python data."""
    if len(data) < HEADER.size:
        raise ValueError("animation file is shorter than its header")
    (magic, version, _flags, header_size, bone_count, sample_count,
     json_length, fps, start_frame, end_frame, _reserved) = HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError("not a .urbanim file (bad magic)")
    offset = header_size
    embedded = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if embedded != json_length:
        raise ValueError(f"header length mismatch: {embedded} != {json_length}")
    header = json.loads(data[offset:offset + json_length].decode("utf-8"))
    offset += json_length

    names = []
    for _ in range(bone_count):
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        names.append(data[offset:offset + length].decode("utf-8"))
        offset += length

    samples = []
    for _ in range(sample_count):
        frame = {}
        for name in names:
            values = SAMPLE.unpack_from(data, offset)
            offset += SAMPLE.size
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
            for _ in range(sample_count):
                values = SAMPLE.unpack_from(data, offset)
                offset += SAMPLE.size
                root.append(
                    {
                        "translation": values[0:3],
                        "rotation": values[3:7],
                        "scale": values[7:10],
                    }
                )

    return {
        "version": version,
        "fps": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "header": header,
        "bones": names,
        "samples": samples,
        "root_motion": root,
        "bytes_consumed": offset,
        "total_bytes": len(data),
    }


def duration(decoded):
    timestamps = decoded["header"].get("timestamps") or []
    if timestamps:
        return float(timestamps[-1]) - float(timestamps[0])
    if decoded["samples"]:
        return (decoded["end_frame"] - decoded["start_frame"]) / max(1e-9, decoded["fps"])
    return 0.0


def describe(package_path, animation=None, frames=0, as_json=False):
    report = {"package": package_path, "entries": [], "problems": []}
    with zipfile.ZipFile(package_path) as archive:
        report["entries"] = sorted(archive.namelist())
        if "manifest.json" not in report["entries"]:
            report["problems"].append("missing manifest.json")
            return report
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        report["manifest"] = manifest

        for required in ("skeleton.json", "validation/export_report.json"):
            if required not in report["entries"]:
                report["problems"].append(f"missing {required}")

        animations = []
        targets = [
            entry for entry in report["entries"]
            if entry.startswith("animations/") and entry.endswith(".urbanim")
        ]
        if animation:
            targets = [
                entry for entry in targets
                if animation.lower() in entry.lower()
                or animation.lower() in entry.rsplit("/", 1)[-1].lower()
            ]
        for entry in targets:
            decoded = read_urbanim(archive.read(entry))
            info = {
                "file": entry,
                "name": decoded["header"].get("name", ""),
                "source": decoded["header"].get("source", ""),
                "fps": decoded["fps"],
                "start_frame": decoded["start_frame"],
                "end_frame": decoded["end_frame"],
                "samples": len(decoded["samples"]),
                "bones": len(decoded["bones"]),
                "duration_seconds": round(duration(decoded), 6),
                "root_motion_bone": decoded["header"].get("root_motion_bone", ""),
                "has_root_motion": decoded["root_motion"] is not None,
                "bytes_consumed": decoded["bytes_consumed"],
                "total_bytes": decoded["total_bytes"],
            }
            if decoded["bytes_consumed"] != decoded["total_bytes"]:
                report["problems"].append(
                    f"{entry}: decoder consumed {decoded['bytes_consumed']} of "
                    f"{decoded['total_bytes']} bytes"
                )
            if frames and decoded["samples"]:
                step = max(1, len(decoded["samples"]) // frames)
                info["frame_preview"] = [
                    {
                        "index": index,
                        "timestamp": (
                            decoded["header"].get("timestamps", [None] * len(decoded["samples"]))[index]
                        ),
                        "bones": {
                            name: {
                                "translation": [round(v, 4) for v in decoded["samples"][index][name]["translation"]],
                                "rotation": [round(v, 5) for v in decoded["samples"][index][name]["rotation"]],
                            }
                            for name in decoded["bones"]
                        },
                    }
                    for index in range(0, len(decoded["samples"]), step)
                ][:frames]
            animations.append(info)
        report["animations"] = animations

        if manifest.get("animations") and not animations:
            report["problems"].append("manifest lists animations but no .urbanim file was found")

        report["unit_scale"] = manifest.get("unit_scale")
        report["mesh_files"] = [
            entry for entry in report["entries"] if entry.startswith("meshes/")
        ]
        report["skeleton_bone_counts"] = {}
        if "skeleton.json" in report["entries"]:
            skeleton = json.loads(archive.read("skeleton.json").decode("utf-8"))
            for record in skeleton.get("skeletons", []):
                report["skeleton_bone_counts"][record.get("armature", "?")] = record.get("bone_count", 0)
    return report


def print_report(report):
    manifest = report.get("manifest", {})
    print(f"Package      : {report['package']}")
    print(f"Name         : {manifest.get('package_name', '?')}")
    print(f"Target       : Unreal {manifest.get('target_unreal_version', '?')}")
    print(f"Coordinates  : {manifest.get('coordinate_system', '?')} (unit scale {report.get('unit_scale')})")
    print(f"Skeletons    : {report.get('skeleton_bone_counts')}")
    print(f"Meshes       : {len(report.get('mesh_files', []))} file(s)")
    print()
    print(f"{'Animation':<28}{'Source':<8}{'Range':<12}{'FPS':>6}{'Keys':>7}{'Bones':>7}{'Seconds':>10}  Root")
    for item in report.get("animations", []):
        print(
            f"{item['name'][:27]:<28}{item['source']:<8}"
            f"{item['start_frame']:.0f}-{item['end_frame']:.0f}    "
            f"{item['fps']:>6.2f}{item['samples']:>7}{item['bones']:>7}"
            f"{item['duration_seconds']:>10.3f}  {item['root_motion_bone'] or '-'}"
        )
    print()
    entries = report.get("entries", [])
    print(f"Entries ({len(entries)}):")
    for entry in entries:
        print(f"  {entry}")
    if report.get("problems"):
        print()
        print("Problems:")
        for problem in report["problems"]:
            print(f"  ! {problem}")
    else:
        print()
        print("No structural problems found.")


def main(argv=None):
    if argv is None:
        # Works both as `python urb_inspect.py pkg.urb` and when launched
        # through Blender with `--python ... -- pkg.urb`.
        if "--" in sys.argv:
            argv = sys.argv[sys.argv.index("--") + 1:]
        elif sys.argv and sys.argv[0].lower().endswith(("blender.exe", "blender")):
            argv = [argument for argument in sys.argv[1:] if argument.endswith(".urb") or argument.startswith("--")]
        else:
            argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description="Inspect a Universal Rig Bridge .urb package")
    parser.add_argument("package", help="path to the .urb file")
    parser.add_argument("--animation", help="only decode animations whose name matches this text")
    parser.add_argument("--frames", type=int, default=0, help="print a preview of N samples per animation")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    try:
        report = describe(args.package, args.animation, args.frames, args.json)
    except (OSError, zipfile.BadZipFile) as error:
        print(f"Cannot read package: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"Malformed package: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 1 if report.get("problems") else 0


if __name__ == "__main__":
    raise SystemExit(main())
