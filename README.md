# Universal Rig Bridge

A Blender add-on that analyses a rig, bakes what Blender evaluates, and exports
Unreal-ready assets as a single compressed `.urb` package. The rig itself is
never rebuilt in Unreal: constraints, drivers and control bones are evaluated in
Blender, and only the resulting skeleton, animation samples and skinned meshes
are exported.

Supported target: **Blender 5.0+** with the bundled FBX exporter,
**Unreal Engine 5.4 – 5.8** (5.8 tested).

## Install

1. Zip the `UniversalRigBridge` folder (the folder, not the repository).
2. In Blender: **Edit › Preferences › Add-ons › Install…**, pick the zip.
3. Enable **Universal Rig Bridge**.
4. In the 3D viewport press `N` and open the **UNIVERSAL RIG BRIDGE** tab.

## Workflow

1. **Project Settings** — set the project name, export folder and target engine
   version. Defaults are Unreal 5.8, Unreal Compatible axes, URB Package format
   and automatic unit scale (metres → centimetres).
2. **Rig Analysis** — run **Analyze Rig**. The add-on inspects armatures,
   constraints, drivers, meshes, weights and animations, then reports problems.
3. **Bone Hierarchy** — review how bones were classified. Classification uses
   evidence (deform flag, vertex weights, hierarchy, constraints, targets), not
   names. A manual classification changes metadata only.
4. **Constraint Analysis** — each constraint is `SUPPORTED` (no runtime effect
   left), `BAKED` (evaluated into samples) or `UNSUPPORTED` (cannot be
   guaranteed). Baking is not assumed from the constraint type; the dependency
   graph is evaluated.
5. **Animation Manager** — pick clips, ranges and sampling. Actions (including
   layered actions with multiple slots), NLA strips and the scene range are all
   discovered automatically.
6. **Export** — writes the package and a validation report.

Nothing in the scene is modified: actions, weights, modifiers, selection,
frame, active action/slot and NLA mute states are restored even if the bake
fails.

## Sampling modes

| Mode | Behaviour |
| --- | --- |
| Every Frame | One sample per scene frame. Most accurate, largest files. |
| Custom FPS | Resamples at a fixed rate while preserving the clip's real duration. |
| Frame Interval | One sample every *N* frames, evenly spaced. |
| Adaptive | Keeps only the keys needed to stay inside the translation/rotation/scale tolerances, then reports the measured error. |

Exported timestamps always describe real seconds, so a clip sampled at 15 fps
has the same duration as the same clip sampled at 30 fps.

## Package contents

```
manifest.json                     package identity, contents, unit scale, axes
skeleton.json                     reference skeleton(s) in Unreal space
animations/*.urbanim              binary baked animation
animations/animations_index.json  human-readable clip index
meshes/*.fbx                      skinned meshes with the armature
metadata/bones.json               classification and rest data per bone
metadata/constraints.json         constraint categories, reasons, dependencies
metadata/drivers.json             driver summary
metadata/rig_analysis.json        full analysis payload
validation/export_report.json     issues, weight checks, export notes
```

### Skeleton and animation convention

Bone locals are stored **parent-relative to the nearest exported ancestor** — the
same rule Unreal uses when composing `Local * ParentComponentSpace`. If a
non-deform control bone is dropped, its deform children are re-parented in the
export so animation tracks and the skeleton always agree.

Rotations are quaternions ordered `w, x, y, z`. Translations are in centimetres
when **Unreal Compatible** is selected, with `X_unreal = -Y_blender`,
`Y_unreal = X_blender` and shared `Z`.

### `.urbanim` binary layout

All values little-endian.

| Field | Type |
| --- | --- |
| magic `URBANIM\0` | 8 bytes |
| version, flags | u16, u16 |
| header size, bone count, sample count | u32 ×3 |
| fps, start frame, end frame | f32 ×3 |
| header JSON length | u32 |
| header JSON | UTF-8 (timestamps, source frames, bone order, source) |
| bone table | length-prefixed UTF-8 names |
| samples | `sample_count × bone_count × 10 × f32` (T3, Q4, S3) |
| root motion | u8 flag, then `sample_count × 10 × f32` |

`tools/urb_inspect.py` is a dependency-free reference decoder:

```
python tools/urb_inspect.py MyProject.urb
python tools/urb_inspect.py MyProject.urb --animation Walk --frames 3
```

It also runs through Blender's Python if CPython is unavailable:

```
blender.exe -b --python tools/urb_inspect.py -- MyProject.urb
```

## Importing in Unreal

1. Drag `meshes/*.fbx` into the Content Browser. Import as **Skeletal Mesh**,
   accept the detected skeleton, and keep *Import Animations* off.
2. The FBX carries the bind pose and skin weights; bone names match
   `skeleton.json`.
3. Map `.urbanim` clips onto the imported skeleton using your own pipeline — the
   format is self-describing (`tools/urb_inspect.py` prints every field). Clip
   length, fps, bone order and root-motion channel are all in the header.
4. Enable root motion on clips whose header lists a `root_motion_bone`.

## Root motion

Root motion is extracted as a delta relative to the first sample and stored in a
separate block. When **Keep In Pose** is off, the extracted channels are removed
from the root's pose track so Unreal does not apply the displacement twice;
channels you did not extract stay animated in the pose.

## Tests

```
blender.exe -b --factory-startup --python tests/test_addon.py
blender.exe -b --factory-startup --python tests/test_units.py
```

`test_addon.py` builds a skinned rig with an IK chain and a limit constraint,
analyses it, exports a package, decodes the animation and checks that the
exported locals reconstruct the evaluated pose. `test_units.py` covers axis
conversion, coordinate composition, sampling rates, adaptive error bounds, root
motion handling, NLA export and the standalone decoder.

## Architecture

```
UniversalRigBridge/
  core/       rig, bone, constraint, dependency, animation, mesh analysis
  baking/     sampling, baking orchestration, root motion, drivers
  exporters/  skeleton, animation, binary codec, metadata, package assembly
  utils/      coordinates, matrices, files, naming, logging
  ui/         panels, operators
```

Analysis produces plain Python dictionaries; the UI caches them in scene
properties, and the exporter consumes the same data, so what the panels show is
what gets written.
