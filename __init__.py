import bpy
from bpy.props import *
from .PesFacemod.PesFacemod import *
import bpy.utils.previews

bl_info = {
    "name": "PES2020 Facemod",
    "version": (1, 80, 0),
    "blender": (2, 80, 0),
    "location": "Under Scene Tab",
    "description": "Unpacks and packs face.fpk files for modification",
    "warning": "Saving your .blend file won't work, you must pack everything and start again. Backup your files.",
    "wiki_url": "",
    "tracker_url": "",
    "category": "System"
}

classes = (
    ListItem,
    PANEL_PT_file_properties,
    FMDL_UL_strings,
    PANEL_PT_string_properties,
    OBJECT_OT_face_hair_modifier
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    pcoll = bpy.utils.previews.new()
    my_icons_dir = os.path.join(os.path.dirname(__file__))

    # load a preview thumbnail of a file and store in the previews collection
    print("Loading ", os.path.join(my_icons_dir, "icon.png"))
    pcoll.load("fhm_icon", os.path.join(my_icons_dir, "icon.png"), 'IMAGE')
    preview_collections["main"] = pcoll

    bpy.types.Object.fmdl_strings = CollectionProperty(type=ListItem)
    bpy.types.Object.list_index = IntProperty(name="Index for fmdl_strings", default=0)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()


if __name__ == "__main__":
    register()
