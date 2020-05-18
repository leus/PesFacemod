import bpy, os, os.path, struct
from bpy.props import StringProperty, BoolProperty, FloatProperty
from struct import *
import tempfile
from mathutils import Vector
from .PesFacemodGlobalData import PesFacemodGlobalData
from .FmdlManager import FmdlManagerBase, exec_tool
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

        box = layout.box()
        row = box.row(align=1)
        row.label(text="New scene (clear data)")
        row = box.row()
        if not PesFacemodGlobalData.good_path(scn.face_path):
            row.enabled = 0
        row.operator("primary.operator", text="New scene", icon="FILE_BLANK").face_opname = "newscene"


def get_radius(obj):
    vsum = Vector()
    for v in obj.data.vertices:
        vsum += v.co  # sum all selected vectors together
    midPoint = vsum / len(obj.data.vertices)  # average point
    # get average distance from middlepoint, to account for minor variability.
    distances = [(v.co - midPoint).length for v in obj.data.vertices]
    averageDist = float(sum(distances) / len(distances))
    print("radius: ", averageDist)
    return averageDist


def reference_vector(object_name):
    obj = bpy.data.objects[object_name]
    if obj is not None:
        max_z = max([v.co.z for v in obj.data.vertices])

        # Select all the vertices that are on the lowest Z
        for v in obj.data.vertices:
            if v.co.z == max_z:
                ret = v.co.copy()
                ret.x = 0
                ret.y = 0
                return ret
    return None


def max_vert_distance(object_name):
    obj = bpy.data.objects[object_name]
    verts = obj.data.vertices
    centre = Vector([0, 0, 0])
    for vert in verts:
        centre += vert.co
    centre = centre / len(verts)
    distanceFromCentre = 0.0
    for vert in verts:
        vecFromCentre = vert.co - centre
        vertDistanceFromCentre = vecFromCentre.length
        if vertDistanceFromCentre > distanceFromCentre:
            distanceFromCentre = vertDistanceFromCentre
            vert1 = vert
    distance = 0.0
    for vert in verts:
        vec = vert.co - vert1.co
        vertsDistance = vec.length
        if vertsDistance > distance:
            distance = vertsDistance
            vert2 = vert
    return distance


def get_object_location(obj_name):
    return bpy.data.objects[obj_name].location.copy()


def scene_eye_size(pes_factor):
    return pes_factor * 0.05


def pes_eye_size(scene_diameter):
    return scene_diameter / 0.05


def save_eye(ref_vector, stream_handle, name, diameter_offset, position_offset):
    if name in bpy.data.objects.keys():
        loc = get_object_location(name)
        loc -= ref_vector
        diameter = pes_eye_size(max_vert_distance(name))
        print("Eye ", name, loc, diameter)
        # diameter
        stream_handle.seek(diameter_offset)
        stream_handle.write(struct.pack('f', diameter))
        stream_handle.seek(position_offset)
        stream_handle.write(struct.pack('3f', loc.z, loc.y, loc.x))  # Write eye Right
    else:
        print("Eye not present in scene: ", name)


def pes_diff_bin_exp(diff_bin_export_filename, oralpath):
    scn = bpy.context.scene
    header_data = open(diff_bin_export_filename, 'rb').read(4)
    header_string = str(header_data, "utf-8")
    if header_string == "FACE":
        pes_diff_data = open(diff_bin_export_filename, 'r+b')

        # Positions relative to this
        v = reference_vector('Face_0')
        # Writing mouth position
        if not os.path.isfile(oralpath):  # If oral.fmdl not available
            if 'mouth' in bpy.data.objects.keys():
                mx, my, mz = get_object_location('mouth')
                pes_diff_data.seek(0x3c)
                pes_diff_data.write(struct.pack('3f', mz, my * -1, mx))
        save_eye(v, pes_diff_data, 'eyeR', 0x08, 0x150)
        save_eye(v, pes_diff_data, 'eyeL', 0x10, 0x160)

        # overwrite diameter
        pes_diff_data.seek(0x08)
        pes_diff_data.write(struct.pack('3f', 1.0, 1.0, 1.0))

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
        print("diameters: ", diameter_x, diameter_y, diameter_z)
        pes_diff_data0.seek(0x3c)
        mouth_pos_r_x, mouth_pos_r_y, mouth_pos_r_z = unpack("3f", pes_diff_data0.read(12))
        print("mouth: ", mouth_pos_r_x, mouth_pos_r_y, mouth_pos_r_z)
        pes_diff_data0.seek(0x150)
        eyes_pos_r_x, eyes_pos_r_y, eyes_pos_r_z = unpack("3f", pes_diff_data0.read(12))
        print("right eye: ", eyes_pos_r_x, eyes_pos_r_y, eyes_pos_r_z)
        pes_diff_data0.seek(0x160)
        eyes_pos_l_x, eyes_pos_l_y, eyes_pos_l_z = unpack("3f", pes_diff_data0.read(12))
        print("left eye: ", eyes_pos_l_x, eyes_pos_l_y, eyes_pos_l_z)

        # translate to Blender coordinates
        if 'mouth' in bpy.data.objects.keys():
            bpy.data.objects['mouth'].location.x = mouth_pos_r_x
            bpy.data.objects['mouth'].location.y = mouth_pos_r_z * -1
            bpy.data.objects['mouth'].location.z = mouth_pos_r_y

        # The number stored in the diff file is not in game units, but a factor of an unknown number
        # I'm assuming 25mm radius (50mm)
        eye_diameter = scene_eye_size(diameter_x)

        # PES uses x (breadth), y (height), z (depth), but it stores it as z, y, x
        # Blender uses x (breadth), z (height), y (depth)
        eyeL = create_eye('eyeL', scene_eye_size(eye_diameter), eyes_pos_l_x, eyes_pos_l_z, eyes_pos_l_y)
        eyeR = create_eye('eyeR', scene_eye_size(eye_diameter), eyes_pos_r_x, eyes_pos_r_z, eyes_pos_r_y)

        v = reference_vector('Face_0')
        if v is not None:
            eyeL.location += v
            eyeR.location += v
    return True


# Eyes seem to be relative to the topmost vertex in the Face_0 mesh.
def create_eye(name, diameter, x, y, z):
    print("Creating eye: ", name, diameter, x, y, z)

    mesh = bpy.data.meshes.new(name)
    basic_sphere = bpy.data.objects.new(name, mesh)

    # Add the object into the scene.
    bpy.context.collection.objects.link(basic_sphere)

    # Select the newly created object
    bpy.context.view_layer.objects.active = basic_sphere
    basic_sphere.select_set(True)

    # Construct the bmesh sphere and assign it to the blender mesh.
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, diameter=diameter)
    bm.to_mesh(mesh)
    bm.free()

    bpy.ops.object.modifier_add(type='SUBSURF')
    bpy.ops.object.shade_smooth()

    basic_sphere.location = (x, y, z)

    return basic_sphere


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
                return False
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

            pes_diff_bin_exp(PesFacemodGlobalData.diff_bin, PesFacemodGlobalData.oral_fmdl)
            self.report({"INFO"}, "Exporting PES_DIFF.BIN Succesfully!")

            pack_files()
            self.report({"INFO"}, "Files packed")

            return {'FINISHED'}

        if self.face_opname == "newscene":
            pes_face.clear()
            pes_hair.clear()
            pes_oral.clear()
            PesFacemodGlobalData.vertexgroup_disable = True
            bpy.ops.wm.read_homefile()
            PesFacemodGlobalData.clear()
            return {'FINISHED'}


class ListItem(bpy.types.PropertyGroup):
    """ Group of properties representing an item in the list """
    name: StringProperty(name="Name", description="A name for this item", default="Untitled")
