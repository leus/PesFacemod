import bpy, os, os.path, struct
from bpy.props import StringProperty, BoolProperty, FloatProperty
from struct import *
import tempfile

from .PesFacemodGlobalData import PesFacemodGlobalData
from .FmdlManager import FmdlManagerBase
import subprocess


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
        self.process_normals = True


class HairFmdlManager(FmdlManagerBase):
    def __init__(self, base_path, tempfile_path):
        super().__init__(base_path, tempfile_path)
        self.model_type = "Hair"
        self.process_normals = True


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
        row = box.row(align=0)

        if not os.path.isfile(PesFacemodGlobalData.oral_fmdl):
            row.label(text="Mouth set position not available!", icon="FILE_TICK")
            row = box.row()
        row.prop(scn, "eyes_size", text="Eye Size")
        box.row()

        box = layout.box()
        row = box.row(align=1)
        row.label(text="New scene (clear data)")
        row = box.row()
        if not PesFacemodGlobalData.good_path(scn.face_path):
            row.enabled = 0
        row.operator("primary.operator", text="New scene", icon="FILE_BLANK").face_opname = "newscene"


def pes_diff_bin_exp(diff_bin_export_filename, oralpath):
    scn = bpy.context.scene
    header_data = open(diff_bin_export_filename, 'rb').read(4)
    header_string = str(header_data, "utf-8")
    if header_string == "FACE":
        pes_diff_data = open(diff_bin_export_filename, 'r+b')
        # Writing eye size
        pes_diff_data.seek(0x08)
        pes_diff_data.write(struct.pack('3f', scn.eyes_size, scn.eyes_size, scn.eyes_size))
        # Writing mouth position
        if not os.path.isfile(oralpath):  # If oral.fmdl not available
            if 'mouth' in bpy.data.objects.keys():
                m0 = (bpy.data.objects['mouth'].location[0]) * 1
                m1 = (bpy.data.objects['mouth'].location[1]) * -1
                m2 = (bpy.data.objects['mouth'].location[2]) * 1
                pes_diff_data.seek(0x3c)
                pes_diff_data.write(struct.pack('3f', m0, m2, m1))

        if 'eyeR' in bpy.data.objects.keys():
            rx = (bpy.data.objects['eyeR'].location[0]) * -1
            ry = (bpy.data.objects['eyeR'].location[1]) * 1
            rz = (bpy.data.objects['eyeR'].location[2]) * 1
            # Writing eye position
            pes_diff_data.seek(0x150)
            pes_diff_data.write(struct.pack('3f', rz, ry, rx))  # Write eye Right

        if 'eyeL' in bpy.data.objects.keys():
            lx = (bpy.data.objects['eyeL'].location[0]) * -1
            ly = (bpy.data.objects['eyeL'].location[1]) * 1
            lz = (bpy.data.objects['eyeL'].location[2]) * 1
            pes_diff_data.seek(0x160)
            pes_diff_data.write(struct.pack('3f', lz, ly, lx))  # Write eye Left

        pes_diff_data.flush()
        pes_diff_data.close()
    return 1


pes_face = []
pes_hair = []
pes_oral = []
pes_diff_bin_data = []
temp_path = tempfile.gettempdir()

face_type = None
hair_type = None
oral_type = None

packfpk = None


def exec_tool(*args):
    print("\t*** Executing tool: ", args)
    return subprocess.run(args)


class OBJECT_OT_face_hair_modifier(bpy.types.Operator):
    bl_idname = "primary.operator"
    bl_label = "prime operator"
    face_opname = StringProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def unpack_files(self):
        if PesFacemodGlobalData.face_fpk != '':
            # unpack face_high.fmdl, etc.
            try:
                exec_tool(os.path.join('Tools', 'Gzs', 'GzsTool.exe'), PesFacemodGlobalData.face_fpk)
            except subprocess.CalledProcessError as gzs_ex:
                print("Gzs returned error:", gzs_ex.returncode, gzs_ex.output)

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
                    try:
                        # extract DDS from Ftex
                        exec_tool(os.path.join('Tools', 'FtexDdsTools.exe'), texture + '.ftex')
                    except subprocess.CalledProcessError as ftex_ex:
                        print("Ftex returned error:", ftex_ex.returncode, ftex_ex.output)
                    try:
                        # extract PNG from DDS
                        (path, fname) = os.path.split(texture + '.dds')
                        exec_tool(os.path.join('Tools', 'texconv.exe'), '-ft', 'png', texture + '.dds', '-o', path)
                    except subprocess.CalledProcessError as ftex_ex:
                        print("Texconv returned error:", ftex_ex.returncode, ftex_ex.output)
                else:
                    print("\tFile not found.")
        self.report({"INFO"}, "Files unpacked")

    def pack_files(self):
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
                exec_tool(os.path.join('Tools', 'nvidia-texture-tools-2.1.1-win64', 'bin64', 'nvcompress.exe'), '-bc3',
                          texture + '.PNG', texture + '.dds')
                # convert to Ftex
                exec_tool(os.path.join('Tools', 'DdsFtexTools.exe'), '-f', '0', texture + '.dds')

        # and pack face file
        xml_file = PesFacemodGlobalData.face_fpk + '.xml'
        exec_tool(os.path.join('Tools', 'Gzs', 'GzsTool.exe'), xml_file)
        self.report({"INFO"}, "Files packed")

    @staticmethod
    def remove_temp_files(*files):
        for file in files:
            if os.path.exists(os.path.join(temp_path, file)):
                os.remove(os.path.join(temp_path, file))

    def execute(self, context):
        scn = context.scene
        if not PesFacemodGlobalData.good_path(scn.face_path):
            return {'FINISHED'}

        global pes_face, pes_hair, pes_oral, pes_diff_bin_data, face_type, hair_type, oral_type
        if self.face_opname == "import_files":
            if len(pes_face) != 0:
                return {'FINISHED'}
            PesFacemodGlobalData.clear()
            pes_diff_bin_data.clear()
            PesFacemodGlobalData.load(scn.face_path)
            self.remove_temp_files("face_normals_data.bin", "face_tangents_data.bin")
            self.unpack_files()

            face_type = FaceFmdlManager(PesFacemodGlobalData.facepath, temp_path)
            print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
            pes_face = face_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
            self.report({"INFO"}, "Face Imported Succesfully (%s items)" % (len(pes_face)))

            print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
            self.remove_temp_files("hair_normals_data.bin", "hair_tangents_data.bin")
            hair_type = HairFmdlManager(PesFacemodGlobalData.facepath, temp_path)
            pes_hair = hair_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
            self.report({"INFO"}, "hair.fmdl file imported")

            if os.path.exists(str(os.path.abspath(PesFacemodGlobalData.oral_fmdl))):
                print("Trying to open file ", str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
                oral_type = OralFmdlManager(PesFacemodGlobalData.facepath, temp_path)
                pes_oral = oral_type.importmodel(str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
                self.report({"INFO"}, "Oral.fmdl file imported")

            self.pes_diff_bin_imp(PesFacemodGlobalData.diff_bin)
            self.report({"INFO"}, "PES_DIFF.BIN Imported Succesfully!")
            print("Files imported")
            return {'FINISHED'}

        if self.face_opname == "export_files":
            if len(pes_face) == 0:
                return {'FINISHED'}
            face_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.face_fmdl)))
            self.report({"INFO"}, "Face Exported Succesfully")

            hair_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.hair_fmdl)))
            self.report({"INFO"}, "Hair Exported Succesfully")

            if len(pes_oral) != 0 and oral_type is not None:
                oral_type.exportmodel(str(os.path.abspath(PesFacemodGlobalData.oral_fmdl)))
            self.report({"INFO"}, "Oral Exported Succesfully")

            if len(pes_diff_bin_data) != 0:
                pes_diff_bin_exp(PesFacemodGlobalData.diff_bin, PesFacemodGlobalData.oral_fmdl)
                self.report({"INFO"}, "Exporting PES_DIFF.BIN Succesfully!")
                print("Exporting PES_DIFF.BIN Succesfully!")
            else:
                self.report({"WARNING"}, "Import PES_DIFF.BIN before export!!")
                print("Import PES_DIFF.BIN before export!!")

            self.pack_files()

            return {'FINISHED'}

        if self.face_opname == "newscene":
            pes_diff_bin_data.clear()
            pes_face.clear()
            pes_hair.clear()
            pes_oral.clear()
            PesFacemodGlobalData.vertexgroup_disable = True
            bpy.ops.wm.read_homefile()
            PesFacemodGlobalData.clear()
            return {'FINISHED'}

    @staticmethod
    def pes_diff_bin_imp(pes_diff_filename):
        scn = bpy.context.scene
        header_data = open(pes_diff_filename, 'rb').read(4)
        header_string = str(header_data, "utf-8")
        if header_string == "FACE":
            pes_diff_data0 = open(pes_diff_filename, "rb")
            pes_diff_data0.seek(0x08)
            eyes_size = unpack("3f", pes_diff_data0.read(12))
            pes_diff_data0.seek(0x3c)
            m_pos = unpack("3f", pes_diff_data0.read(12))
            pes_diff_data0.seek(0x150)
            eyes_pos_r = unpack("3f", pes_diff_data0.read(12))
            pes_diff_data0.seek(0x160)
            eyes_pos_l = unpack("3f", pes_diff_data0.read(12))

            scn.eyes_size = eyes_size[0]

            if 'mouth' in bpy.data.objects.keys():
                bpy.data.objects['mouth'].location[0] = (m_pos[0] * 1)
                bpy.data.objects['mouth'].location[1] = (m_pos[2] * -1)
                bpy.data.objects['mouth'].location[2] = (m_pos[1] * 1)

            if 'eyeR' in bpy.data.objects.keys():
                bpy.data.objects['eyeR'].location[2] = (eyes_pos_r[0] * 1)
                bpy.data.objects['eyeR'].location[0] = (eyes_pos_r[2] * -1)
                bpy.data.objects['eyeR'].location[1] = (eyes_pos_r[1] * 1)

            if 'eyeL' in bpy.data.objects.keys():
                bpy.data.objects['eyeL'].location[2] = (eyes_pos_l[0] * 1)
                bpy.data.objects['eyeL'].location[0] = (eyes_pos_l[2] * -1)
                bpy.data.objects['eyeL'].location[1] = (eyes_pos_l[1] * 1)

            pes_diff_bin_data.append(eyes_size[0])
        return 1


class ListItem(bpy.types.PropertyGroup):
    """ Group of properties representing an item in the list """
    name: StringProperty(name="Name", description="A name for this item", default="Untitled")
