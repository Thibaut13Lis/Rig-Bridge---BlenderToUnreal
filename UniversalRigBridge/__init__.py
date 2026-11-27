bl_info = {
    "name": "Universal Rig Bridge",
    "author": "Universal Rig Bridge",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Universal Rig Bridge",
    "description": "Analyse, bake and package Blender rigs and animations for Unreal Engine",
    "category": "Import-Export",
}

import bpy

from . import preferences, properties
from .ui import operators, panels

_MODULES = (properties, preferences, operators, panels)


def register():
    for module in _MODULES:
        if hasattr(module, "register"):
            module.register()


def unregister():
    for module in reversed(_MODULES):
        if hasattr(module, "unregister"):
            module.unregister()


if __name__ == "__main__":
    register()
