"""Universal Rig Bridge viewport interface."""

from . import analysis_panel, animation_panel, bone_panel, export_panel, main_panel

_PANELS = (main_panel, analysis_panel, bone_panel, animation_panel, export_panel)


def register():
    for module in _PANELS:
        module.register()


def unregister():
    for module in reversed(_PANELS):
        module.unregister()
