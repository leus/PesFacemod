import bpy, os, os.path, struct
from bpy.props import StringProperty, BoolProperty, FloatProperty, IntProperty
from struct import *
import tempfile
from mathutils import Vector
from .PesFacemodGlobalData import PesFacemodGlobalData
from .FmdlManager import FmdlManagerBase, exec_tool, apply_textures
import bmesh


def log(*args, logtype='debug', sep=' '):
    # getattr(logger, logtype)(sep.join(str(a) for a in args))
    pass


def get_active_mesh():
    # return bpy.context.scene.objects.active.data
    # return bpy.context.window.scene.objects[0].data
    if bpy.context.object is not None:
        return bpy.context.object.data
    else:
        return None


class FaceFmdlManager(FmdlManagerBase):
    def __init__(self, base_path, tempfile_path):
        super().__init__(base_path, tempfile_path)
        self.model_type = "Face"


class HairFmdlManager(FmdlManagerBase):
    def __init__(self, base_path, tempfile_path):
        super().__init__(base_path, tempfile_path)
        self.model_type = "Hair"


class OralFmdlManager(FmdlManagerBase):
    def __init__(self, base_path, tempfile_path):
        super().__init__(base_path, tempfile_path)
        self.model_type = "Oral"


class PANEL_PT_string_properties(bpy.types.Panel):
    bl_label = "FMDL Strings"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    def draw(self, context):
        layout = self.layout
        obj = context.object
        scn = context.scene

        row = layout.row()
        row.template_list("FMDL_UL_strings", "FMDL_String_List", obj, "fmdl_strings", obj, "list_index")


class FMDL_UL_strings(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):

        # We could write some code to decide which icon to use here...
        # custom_icon = 'OBJECT_DATAMODE'
        custom_icon = 'OUTLINER_DATA_FONT'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            # layout.label(text=item.name, icon = custom_icon)
            layout.prop(item, "name", text="", emboss=False, icon=custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label("", icon=custom_icon)


preview_collections = {}


class PANEL_PT_file_properties(bpy.types.Panel):
    bl_label = "PES2020 Face Modifier"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    default_filename = ''
    default_face = os.path.normpath(default_filename)
    bpy.types.Scene.face_path = StringProperty(name="FACE File", subtype='FILE_PATH', default=default_face)
    bpy.types.Scene.eyes_size = FloatProperty(name="", min=0.5, max=1.5, default=1.03)
    bpy.types.Scene.player_id = IntProperty(name="Player Id")

    def draw(self, context):
        layout = self.layout
        pcoll = preview_collections["main"]
        my_icon = pcoll["fhm_icon"]

        scn = bpy.context.scene
        PesFacemodGlobalData.facepath = scn.face_path
        box = layout.box()
        box.alignment = 'CENTER'

        row = box.row(align=0)
        row.label(text="PES2020 Face Modifier v2.0", icon_value=my_icon.icon_id)
        row = box.row()
        row.label(text="face.fpk file:")
        box.prop(scn, "face_path", text="")
        row = box.row(align=0)
        if not PesFacemodGlobalData.good_path(scn.face_path):
            row.enabled = 0

        row.operator("primary.operator", text="Import Fpk", icon="IMPORT").face_opname = "import_files"
        row.operator("primary.operator", text="Export Fpk", icon="EXPORT").face_opname = "export_files"

        box = layout.box()
        row = box.row(align=1)
        row.label(text="New scene (clear data)")
        row = box.row()
        if not PesFacemodGlobalData.good_path(scn.face_path):
            row.enabled = 0
        row.operator("primary.operator", text="New scene", icon="FILE_BLANK").face_opname = "newscene"

        row = box.row()
        row.label(text="New Id")
        box.prop(scn, "player_id", text="")
        row.operator("primary.operator", text="Renumber player", icon="FILE_REFRESH").face_opname = "renumber"


def get_diameter(obj, dim):
    max_d = max([v.co[dim] for v in obj.data.vertices])
    min_d = min([v.co[dim] for v in obj.data.vertices])
    return max_d - min_d


# Dimensions extracted from the base eye model we are using. I assume it's from the game.
def get_pes_diameters(obj):
    d_x = get_diameter(obj, 0) / 0.022276999428868294
    d_y = get_diameter(obj, 1) / 0.022332072257995605
    d_z = get_diameter(obj, 2) / 0.015468999743461609
    return d_x, d_y, d_z


def scene_eye_size(pes_factor):
    return pes_factor * 0.05


def save_eye(stream_handle, name, diameter_offset, position_offset):
    if name in bpy.data.objects.keys():
        loc = bpy.data.objects[name].location.copy()
        d_x, d_y, d_z = get_pes_diameters(bpy.data.objects[name])

        loc.x = -loc.x

        print("Eye ", name)
        print("\tdiameters:", d_x, d_y, d_z)
        print("\tlocation:", loc)

        stream_handle.seek(diameter_offset)
        stream_handle.write(struct.pack('3f', d_z, d_y, d_x))
        stream_handle.seek(position_offset)
        stream_handle.write(struct.pack('3f', loc.z, loc.y, loc.x))
    else:
        print("Eye not present in scene: ", name)


def pes_to_blender_location(obj_name, p1, p2, p3):
    print("## Assigning position to ", obj_name, p1, p2, p3)
    if obj_name in bpy.data.objects:
        obj = bpy.data.objects[obj_name]
        z, y, x = p1, p2, p3 * -1
        obj.location.x = x
        obj.location.y = y
        obj.location.z = z
        print("\tAssigned: ", obj.location)
        return obj
    else:
        print("\tNot found!")
        return None


def set_eye_parameters(obj_name, diameter_x, diameter_y, diameter_z, p1, p2, p3):
    if obj_name in bpy.data.objects:
        obj = bpy.data.objects[obj_name]
        # not working! need to scale in place, currently scales pivoting on origin
        # obj.scale = (diameter_x, diameter_y, diameter_z)

    return pes_to_blender_location(obj_name, p1, p2, p3)


def pes_diff_bin_exp(diff_bin_export_filename, oralpath):
    header_data = open(diff_bin_export_filename, 'rb').read(4)
    header_string = str(header_data, "utf-8")
    if header_string == "FACE":
        pes_diff_data = open(diff_bin_export_filename, 'r+b')

        # Writing mouth position
        if not os.path.isfile(oralpath):  # If oral.fmdl not available
            if 'mouth' in bpy.data.objects.keys():
                mx, my, mz = bpy.data.objects['mouth'].location
                pes_diff_data.seek(0x3c)
                pes_diff_data.write(struct.pack('3f', mz, my * -1, mx))
        save_eye(pes_diff_data, 'eyeR', 0x08, 0x150)
        save_eye(pes_diff_data, 'eyeL', 0x10, 0x160)

        # overwrite diameter
        # pes_diff_data.seek(0x08)
        # pes_diff_data.write(struct.pack('3f', 1.0, 1.0, 1.0))

        pes_diff_data.flush()
        pes_diff_data.close()
    return True


def pes_diff_bin_imp(pes_diff_filename):
    header_data = open(pes_diff_filename, 'rb').read(4)
    header_string = str(header_data, "utf-8")
    if header_string == "FACE":
        pes_diff_data0 = open(pes_diff_filename, "rb")
        pes_diff_data0.seek(0x08)
        diameter_x, diameter_y, diameter_z = unpack("3f", pes_diff_data0.read(12))
        pes_diff_data0.seek(0x3c)
        p1, p2, p3 = unpack("3f", pes_diff_data0.read(12))
        pes_to_blender_location('mouth', p1, p2, p3)
        pes_diff_data0.seek(0x150)
        p1, p2, p3 = unpack("3f", pes_diff_data0.read(12))
        set_eye_parameters('eyeR', diameter_x, diameter_y, diameter_z, p1, p2, p3)
        pes_diff_data0.seek(0x160)
        p1, p2, p3 = unpack("3f", pes_diff_data0.read(12))
        set_eye_parameters('eyeL', diameter_x, diameter_y, diameter_z, p1, p2, p3)
    return True


pes_face = []
pes_hair = []
pes_oral = []
temp_path = tempfile.gettempdir()

face_type = None
hair_type = None
oral_type = None

packfpk = None


def unpack_files():
    if PesFacemodGlobalData.face_fpk != '':
        # unpack face_high.fmdl, etc.
        if not exec_tool(os.path.join('Tools', 'Gzs', 'GzsTool.exe'), PesFacemodGlobalData.face_fpk):
            return False

        # unpack textures
        textures = [
            PesFacemodGlobalData.face_bsm_alp,
            PesFacemodGlobalData.eye_occlusion_alp,
            PesFacemodGlobalData.face_nrm,
            PesFacemodGlobalData.face_srm,
            PesFacemodGlobalData.face_trm,
            PesFacemodGlobalData.hair_parts_bsm_alp,
            PesFacemodGlobalData.hair_parts_nrm,
            PesFacemodGlobalData.hair_parts_srm,
            PesFacemodGlobalData.hair_parts_trm
        ]
        print("Unpacking textures...")
        for texture in textures:
            print("\tTrying to unpack ", texture + '.ftex', "...")
            if os.path.exists(texture + '.ftex'):
                exec_tool(os.path.join('Tools', 'FtexDdsTools.exe'), texture + '.ftex')
                # extract PNG from DDS
                (path, fname) = os.path.split(texture + '.dds')
                exec_tool(os.path.join('Tools', 'texconv.exe'), '-y', '-ft', 'png', texture + '.dds', '-o', path)
            else:
                print("\tFile not found.")
    return True


def pack_files():
    # pack textures
    textures = [
        PesFacemodGlobalData.face_bsm_alp,
        PesFacemodGlobalData.eye_occlusion_alp,
        PesFacemodGlobalData.face_nrm,
        PesFacemodGlobalData.face_srm,
        PesFacemodGlobalData.face_trm,
        PesFacemodGlobalData.hair_parts_bsm_alp,
        PesFacemodGlobalData.hair_parts_nrm,
        PesFacemodGlobalData.hair_parts_srm,
        PesFacemodGlobalData.hair_parts_trm
    ]
    for texture in textures:
        if os.path.exists(texture + '.PNG'):  # texconv adds extension in uppercase
            # convert from PNG to DDS
            if exec_tool(os.path.join('Tools', 'nvidia-texture-tools-2.1.1-win64', 'bin64', 'nvcompress.exe'),
                         '-bc3',
                         texture + '.PNG', texture + '.dds'):
                # convert to Ftex
                exec_tool(os.path.join('Tools', 'DdsFtexTools.exe'), '-f', '0', texture + '.dds')

    # and pack face file
    xml_file = PesFacemodGlobalData.face_fpk + '.xml'
    exec_tool(os.path.join('Tools', 'Gzs', 'GzsTool.exe'), xml_file)


class OBJECT_OT_face_hair_modifier(bpy.types.Operator):
    bl_idname = "primary.operator"
    bl_label = "prime operator"
    face_opname = StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    @staticmethod
    def remove_temp_files(*files):
        for file in files:
            if os.path.exists(os.path.join(temp_path, file)):
                os.remove(os.path.join(temp_path, file))

    def execute(self, context):
        scn = context.scene
        if not PesFacemodGlobalData.good_path(scn.face_path):
            return {'FINISHED'}

        global pes_face, pes_hair, pes_oral, face_type, hair_type, oral_type
        if self.face_opname == "import_files":
            if len(pes_face) != 0:
                return {'FINISHED'}
            PesFacemodGlobalData.clear()
            PesFacemodGlobalData.load(scn.face_path)
            self.remove_temp_files("face_normals_data.bin", "face_tangents_data.bin")
            if not unpack_files():
                self.report({"INFO"}, "Error unpacking files!")
                return {'CANCELLED'}
            self.report({"INFO"}, "Files unpacked")

            # Load base scene (mouth and eyes in default positions)
            base_scene_path = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                           '..', 'Tools', 'base-scene.blend'))
            print("Loading base scene: ", base_scene_path)
            # link eyeR, eyeL and mouth
            with bpy.data.libraries.load(base_scene_path, link=False) as (data_from, data_to):
                data_to.objects = [name for name in data_from.objects if name in ("eyeR", "eyeL", "mouth")]

            # link object to current scene
            for obj in data_to.objects:
                if obj is not None:
                    bpy.context.collection.objects.link(obj)

            face_type = FaceFmdlManager(PesFacemodGlobalData.facepath, temp_path)
            print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
            pes_face = face_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
            self.report({"INFO"}, "Face Imported Succesfully (%s items)" % (len(pes_face)))

            print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
            self.remove_temp_files("hair_normals_data.bin", "hair_tangents_data.bin")
            hair_type = HairFmdlManager(PesFacemodGlobalData.facepath, temp_path)
            pes_hair = hair_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
            self.report({"INFO"}, "hair.fmdl file imported")

            if False:  # oral.fmdl not processed yet (vertex weights are giving me trouble)
                print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
                oral_type = OralFmdlManager(PesFacemodGlobalData.facepath, temp_path)
                pes_oral = oral_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
                self.report({"INFO"}, "Oral.fmdl file imported")

            pes_diff_bin_imp(PesFacemodGlobalData.diff_bin)
            self.report({"INFO"}, "PES_DIFF.BIN Imported Succesfully!")
            print("Files imported")

            apply_textures()

            return {'FINISHED'}

        if self.face_opname == "export_files":
            self.export_files()
            return {'FINISHED'}

        if self.face_opname == "newscene":
            pes_face.clear()
            pes_hair.clear()
            pes_oral.clear()
            PesFacemodGlobalData.vertexgroup_disable = True
            bpy.ops.wm.read_homefile()
            PesFacemodGlobalData.clear()
            return {'FINISHED'}

        if self.face_opname == "renumber":
            self.renumber_player(scn.player_id)
            return {'FINISHED'}

    def export_files(self):
        if len(pes_face) == 0:
            return {'FINISHED'}
        face_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
        self.report({"INFO"}, "Face Exported Succesfully")

        hair_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
        self.report({"INFO"}, "Hair Exported Succesfully")

        if len(pes_oral) != 0 and oral_type is not None:
            oral_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
        self.report({"INFO"}, "Oral Exported Succesfully")

        pes_diff_bin_exp(PesFacemodGlobalData.diff_bin, PesFacemodGlobalData.oral_fmdl)
        self.report({"INFO"}, "Exporting PES_DIFF.BIN Succesfully!")

        pack_files()
        self.report({"INFO"}, "Files packed")

    def renumber_player(self, player_id):
        import re
        p = re.compile(r'/Assets/pes16/model/character/face/real/(?P<id>\d+)/sourceimages/', re.IGNORECASE)

        existing_player_path = PesFacemodGlobalData.player_path()
        new_path = re.sub(r'\\face\\real\\[0-9]+\\', f'\\\\face\\\\real\\\\{player_id}\\\\',
                          bpy.data.scenes[0].face_path)
        PesFacemodGlobalData.load(new_path)

        # Path shouldn't exist
        if os.path.exists(PesFacemodGlobalData.player_path()):
            self.report({"ERROR_INVALID_INPUT"},
                        "Cannot renumber to an existing folder - make sure it's out of the way")
            PesFacemodGlobalData.load(bpy.data.scenes[0].face_path)
        else:
            import shutil
            PesFacemodGlobalData.load(new_path)
            shutil.copytree(existing_player_path, PesFacemodGlobalData.player_path())
            print("Renumbering player id to ", player_id, PesFacemodGlobalData.face_fpk)
            bpy.data.scenes[0].face_path = PesFacemodGlobalData.face_fpk
            for obj in bpy.data.objects:
                for item in obj.fmdl_strings:
                    item.name = p.sub(f"/Assets/pes16/model/character/face/real/{player_id}/sourceimages/", item.name)

            self.export_files()


class ListItem(bpy.types.PropertyGroup):
    """ Group of properties representing an item in the list """
    name: StringProperty(name="Name", description="A name for this item", default="Untitled")
