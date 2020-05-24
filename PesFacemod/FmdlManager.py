import os.path

import bpy, os, binascii, bmesh, shutil, os.path, struct
from bpy_extras import object_utils
from bpy.props import *
from struct import *
from math import sqrt
from dataclasses import dataclass
import subprocess
import os
from .PesFacemodGlobalData import PesFacemodGlobalData


@dataclass
class MaterialAssignment:
    material_index: int
    mesh_index: int
    name_index: int


@dataclass
class Texture:
    name_index: int
    path_index: int


def log(*args, logtype='debug', sep=' '):
    # getattr(logger, logtype)(sep.join(str(a) for a in args))
    pass


def exec_tool(*args):
    path, *arguments = args
    path = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', path))
    escaped_args = [path, *arguments]
    print("\t*** Executing tool: ", *escaped_args)
    try:
        subprocess.run(escaped_args)
        return True
    except subprocess.CalledProcessError as ex:
        print("Process ended with error error:", ex.returncode, ex.output)
        return False
    except PermissionError as pex:
        print("There was a permissions error: ", pex.filename, pex.args, pex.errno, pex.strerror)
        return False
    except FileNotFoundError as fex:
        print("The file to execute was not found: ", fex.filename, fex.errno, fex.strerror)
        return False


def ftex_to_tga(ftexfilepath):
    exec_tool(os.path.join('Tools', 'FtexDdsTools.exe'), ftexfilepath)
    (fname, ext) = os.path.splitext(ftexfilepath)
    exec_tool(os.path.join('Tools', 'nvidia-texture-tools-2.1.1-win64', 'bin64', 'nvdecompress.exe'), fname + '.dds',
              '-format', 'tga')
    return fname + '.tga'


def tga_to_dds(tgafilepath):
    (fname, ext) = os.path.splitext(tgafilepath)
    exec_tool(os.path.join('Tools', 'nvidia-texture-tools-2.1.1-win64', 'bin64', 'nvcompress.exe'), '-bc3',
              fname + '.tga', fname + '.dds')
    exec_tool(os.path.join('Tools', 'DdsFtexTools.exe'), fname + '.dds')
    return fname + '.dds'


def get_active_mesh():
    if bpy.context.object is not None:
        return bpy.context.object.data
    else:
        return None


def collect_objects(obj_type):
    obj_list = []
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            pass
        elif obj.name[:len(obj_type)] == obj_type:
            if not obj.hide_viewport:
                obj_list.append(obj)
    return obj_list


def collect_vertex_colors(mesh_data, layer_name):
    color_layer = mesh_data.vertex_colors[layer_name].data
    v_loop_color_list = {}
    for loop in mesh_data.loops:
        if loop.vertex_index not in v_loop_color_list:
            clr_list = []
            v_loop_color_list[loop.vertex_index] = clr_list
            v_loop_color_list[loop.vertex_index].append(color_layer[loop.vertex_index].color)
        else:
            v_loop_color_list[loop.vertex_index].append(color_layer[loop.vertex_index].color)

    v_color_list = []
    for key in v_loop_color_list:  # not sure, may have to average values from multiple tuples per vertex
        v_color_list.append(
            v_loop_color_list[key][0])  # decided on less accurate but quick option of picking just first color
    return v_color_list


def normalize_tangents(in_x, in_y, in_z):
    radius = 1
    len_p = sqrt(in_x * in_x + in_y * in_y + in_z * in_z)
    out_x, out_y, out_z = 0, 0, 0
    if in_x != 0:
        out_x = (radius * in_x) / len_p
    if in_y != 0:
        out_y = (radius * in_y) / len_p
    if in_z != 0:
        out_z = (radius * in_z) / len_p
    return out_x, out_y, out_z


def get_face_tuples(mesh_obj):
    mesh = mesh_obj.data
    t_face_list = []
    for poly in mesh.polygons:
        # for idx in poly.vertices:
        #    vector = mesh.vertices[idx].co
        #    if len(vector) != 3:
        #        raise Exception("Mesh not triangulated")
        if len(poly.vertices) != 3:
            raise Exception("Mesh not triangulated")
        t_face_list.append([poly.vertices[0], poly.vertices[1], poly.vertices[2]])
    return t_face_list


def get_uv_map(mesh_obj, map_name):
    mesh = mesh_obj.data
    uv_list = {}
    uvlayer = mesh.uv_layers[map_name]
    for loop in mesh.loops:
        uv_coords = uvlayer.data[loop.index].uv
        uv_list[loop.vertex_index] = (uv_coords[0], uv_coords[1])
    return uv_list


def get_custom_vertex_normals(mesh_obj, map_name):
    data = mesh_obj.data
    cv_nrm_list = {}
    if map_name == "":
        data.calc_tangents()
    else:
        data.calc_tangents(uvmap=map_name)
    for loop in data.loops:
        if cv_nrm_list.get(loop.vertex_index) is None:
            nrm_list = []
            # sorting into dictionary because other methods produced weird bugs
            cv_nrm_list[loop.vertex_index] = nrm_list
            cv_nrm_list[loop.vertex_index].append(loop.normal)
        else:
            # slight concern order of keys may not match vertex order
            cv_nrm_list[loop.vertex_index].append(loop.normal)

    # sort into sublist
    # I think the idea of this code was to get the average of each
    # normal as each vertex can have more than one loop, and their normals may
    # be misaligned; so they tried to average it at the beginning. For some
    # reason that code was uncommented.
    nrm_avg_list = []
    for key in cv_nrm_list:
        loop_list = cv_nrm_list[key]
        avg_vec = loop_list[0]
        for vec in range(len(loop_list)):
            vec_instance = loop_list[vec]
            # avg_vec = avg_vec.slerp(vec_instance,0.5)
        nrm_avg_list.append((key, avg_vec))

    return nrm_avg_list


def get_custom_vertex_tangents(mesh_obj, map_name):
    mesh = mesh_obj.data
    cv_tan_list = {}
    if map_name == "":
        mesh.calc_tangents()
    else:
        mesh.calc_tangents(uvmap=map_name)
    for loop in mesh.loops:
        if cv_tan_list.get(loop.vertex_index) is None:
            # sorting into dictionary because other methods produced weird bugs
            tan_list = []
            cv_tan_list[loop.vertex_index] = tan_list
            cv_tan_list[loop.vertex_index].append(loop.tangent)
        else:
            # slight concern order of keys may not match vertex order
            cv_tan_list[loop.vertex_index].append(loop.tangent)

    # sort into sublist
    tan_avg_list = []
    for key in cv_tan_list:
        loop_list = cv_tan_list[key]
        avg_vec = loop_list[0]
        for vec in range(len(loop_list)):
            vec_instance = loop_list[vec]
            # avg_vec = avg_vec.slerp(vec_instance,0.5)
        tan_avg_list.append((key, avg_vec))

    return tan_avg_list


def generate_skeleton(skeleton_prefix, bone_name_list, bone_position_list):
    amt = bpy.data.armatures.new(skeleton_prefix + '_RigData')
    rig = bpy.data.objects.new(skeleton_prefix + "_Rig", amt)
    rig.location = (0, 0, 0)
    amt.show_names = True
    scn = bpy.context.scene
    scn.objects.link(rig)
    scn.objects.active = rig
    rig.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(
        mode='EDIT')  # apparently theres's a bug where mode switch only sticks when call twice in a row

    for bone_number in range(len(bone_name_list)):
        new_bone = amt.edit_bones.new(str(bone_name_list[bone_number]))
        b_x = bone_position_list[bone_number][0]
        b_y = bone_position_list[bone_number][1]
        b_z = bone_position_list[bone_number][2]
        # new_bone.head = (b_x,b_y,b_z) #bone placement needs to account for parenting
        # new_bone.tail = (b_x,b_y+.1,b_z)

        # quick and dirty place holder
        new_bone.head = (0, bone_number * 0.1, 0.0)
        new_bone.tail = (0, bone_number * 0.1, 0.1)

    rig.hide_viewport = True

    scn.update()

    bpy.ops.object.mode_set(mode='OBJECT')

    return rig


def allocate_object(object_name, vert_list, face_list):
    edge_list = []  # never used?

    mesh = bpy.data.meshes.new(object_name)
    mesh.from_pydata(vert_list, edge_list, face_list)
    active_obj = object_utils.object_data_add(bpy.context, mesh, operator=None)
    active_obj.location = 0, 0, 0
    active_obj.show_all_edges = 1
    active_obj.show_wire = 0

    return active_obj


def allocate_maps(mesh_obj, face_list, uvlist, uvlist_normal):
    active_mesh = mesh_obj.data
    bpy.ops.mesh.uv_texture_add('EXEC_SCREEN')
    mapping_mesh = bmesh.new()
    mapping_mesh.from_mesh(active_mesh)
    uv_layer = mapping_mesh.loops.layers.uv.verify()

    for f in range(len(mapping_mesh.faces)):
        mapping_mesh.faces.ensure_lookup_table()
        for i in range(len(mapping_mesh.faces[f].loops)):
            fuv = mapping_mesh.faces[f].loops[i][uv_layer]
            fuv.uv = uvlist[face_list[f][i]]

    if len(uvlist_normal) != 0:
        mapping_mesh.loops.layers.uv.new("normal_map")
        uv_normal_layer = mapping_mesh.loops.layers.uv["normal_map"]

        for f_nrm in range(len(mapping_mesh.faces)):
            for i_nrm in range(len(mapping_mesh.faces[f_nrm].loops)):
                fuv_nrm = mapping_mesh.faces[f_nrm].loops[i_nrm][uv_normal_layer]
                fuv_nrm.uv = uvlist_normal[face_list[f_nrm][i_nrm]]

    mapping_mesh.to_mesh(active_mesh)
    mapping_mesh.free()


def set_vertex_colors(obj_data, color_list):
    obj_data.vertex_colors.new(name='Edit_Mode')
    color_layer = obj_data.vertex_colors.active
    for poly in obj_data.polygons:
        for idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
            c_r = color_list[obj_data.loops[idx].vertex_index][0]  # filtering out the alpha channel
            c_g = color_list[obj_data.loops[idx].vertex_index][1]
            c_b = color_list[obj_data.loops[idx].vertex_index][2]
            color_layer.data[idx].color = (c_r, c_g, c_b, 1.0)


def set_vertex_weights(mesh_obj, bone_name_list, bone_id_list, bone_weight_list):
    for bone_number in range(len(bone_name_list)):
        v_group = mesh_obj.vertex_groups.new(name=bone_name_list[bone_number])
    for vert_inst in range(len(mesh_obj.data.vertices)):
        id_tuple = bone_id_list[vert_inst]
        weight_tuple = bone_weight_list[vert_inst]

        if weight_tuple[0] > 0.0:
            mesh_obj.vertex_groups[id_tuple[0]].add((vert_inst,), weight_tuple[0], 'ADD')
        if weight_tuple[1] > 0.0:
            mesh_obj.vertex_groups[id_tuple[1]].add((vert_inst,), weight_tuple[1], 'ADD')
        if weight_tuple[2] > 0.0:
            mesh_obj.vertex_groups[id_tuple[2]].add((vert_inst,), weight_tuple[2], 'ADD')
        if weight_tuple[3] > 0.0:
            mesh_obj.vertex_groups[id_tuple[3]].add((vert_inst,), weight_tuple[3], 'ADD')


def remove_vertex_weights(mesh_obj, bone_name_list):
    for bone_number in range(len(bone_name_list)):
        v_group = mesh_obj.vertex_groups.clear()


def collect_vertex_weights(vertex_data):
    vertex_weight_list = []
    for vertex in vertex_data:
        sub_list = []
        for gp in vertex.groups:
            w_group = gp.group
            w_weight = gp.weight
            sub_list.append((w_group, w_weight))
        while len(sub_list) < 4:
            sub_list.append((0, 0.0))
        vertex_weight_list.append(sub_list)

    return vertex_weight_list


def add_image_texture_to_material(node_type, texture_path, material):
    if node_type in ('Base_Tex_SRGB', 'NormalMap_Tex_NRM', 'SpecularMap_Tex_LIN', 'Base_Tex_2_SRGB'):
        if os.path.exists(texture_path):
            teximage = bpy.data.images.load(texture_path)
        else:
            # teximage = bpy.data.images.new(name='empty', width=1024, height=1024)
            log("File '%s' not found, skipping material" % texture_path)
            return

        texture = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = teximage
        principled = material.node_tree.nodes['Principled BSDF']

        if node_type == 'Base_Tex_2_SRGB':
            material.blend_method = 'BLEND'
            material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Base Color'])
            material.node_tree.links.new(texture.outputs['Alpha'], principled.inputs['Alpha'])
        elif node_type == 'Base_Tex_SRGB':
            material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Base Color'])
        elif node_type == 'NormalMap_Tex_NRM':
            material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Normal'])
        elif node_type == 'SpecularMap_Tex_LIN':
            material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Specular'])
    else:
        print("I don't know how to handle '%s', ignoring texture", node_type)


def add_image_to_material(method, filename, material):
    png_file = PesFacemodGlobalData.tex_path(filename + '.PNG')
    if os.path.exists(png_file):
        print("\t\tAdding texture to material '%s'" % png_file)
        add_image_texture_to_material(method, png_file, material)
    else:
        print("\t\t** Image not found: ", png_file)


def apply_textures():
    # Arbitrary materials - one for the face, one for the hair, and let's be done with it

    # face
    face_mat = get_material("skin_material")
    add_image_to_material("Base_Tex_SRGB",  "face_bsm_alp", face_mat)
    add_image_to_material("SpecularMap_Tex_LIN",  "face_srm", face_mat)
    add_image_to_material("NormalMap_Tex_NRM",  "face_nrm", face_mat)
    add_image_to_material("Translucent_Tex_LIN",  "face_trm", face_mat)
    for obj in ['Face_0', 'Face_2', 'Hair_0']:
        bpy.data.objects[obj].data.materials.append(face_mat)

    hair_mat = get_material("hair_material")
    add_image_to_material("Base_Tex_2_SRGB",  "hair_parts_bsm_alp", hair_mat)
    add_image_to_material("SpecularMap_Tex_LIN",  "hair_parts_srm", hair_mat)
    add_image_to_material("NormalMap_Tex_NRM",  "hair_parts_nrm", hair_mat)
    add_image_to_material("Translucent_Tex_LIN",  "hair_parts_trm", hair_mat)
    for obj in ['Hair_1']:
        bpy.data.objects[obj].data.materials.append(hair_mat)


def get_material(texture_name):
    if texture_name in bpy.data.materials:
        return bpy.data.materials[texture_name]
    mat = bpy.data.materials.new(name=texture_name)
    mat.use_nodes = True
    return mat


# http://davidejones.com/blog/1413-python-precision-floating-point/
def halffloat2float(float16):
    sign = int((float16 >> 15) & 0x00000001)
    exponent = int((float16 >> 10) & 0x0000001f)
    fraction = int(float16 & 0x000003ff)
    if exponent == 0:
        if fraction == 0:
            return int(sign << 31)
        else:
            while not (fraction & 0x00000400):
                fraction = fraction << 1
                exponent -= 1
            exponent += 1
            fraction &= ~0x00000400
    elif exponent == 31:
        if fraction == 0:
            return int((sign << 31) | 0x7f800000)
        else:
            return int((sign << 31) | 0x7f800000 | (fraction << 13))

    exponent = exponent + (127 - 15)
    fraction = fraction << 13
    result = int((sign << 31) | (exponent << 23) | fraction)
    return result


# http://davidejones.com/blog/1413-python-precision-floating-point/
def float2halffloat(float32):
    F16_EXPONENT_BITS = 0x1F
    F16_EXPONENT_SHIFT = 10
    F16_EXPONENT_BIAS = 15
    F16_MANTISSA_BITS = 0x3ff
    F16_MANTISSA_SHIFT = (23 - F16_EXPONENT_SHIFT)
    F16_MAX_EXPONENT = (F16_EXPONENT_BITS << F16_EXPONENT_SHIFT)

    a = pack('>f', float32)
    b = binascii.hexlify(a)

    f32 = int(b, 16)
    f16 = 0
    sign = (f32 >> 16) & 0x8000
    exponent = ((f32 >> 23) & 0xff) - 127
    mantissa = f32 & 0x007fffff

    if exponent == 128:
        f16 = sign | F16_MAX_EXPONENT
        if mantissa:
            f16 |= (mantissa & F16_MANTISSA_BITS)
    elif exponent > 15:
        f16 = sign | F16_MAX_EXPONENT
    elif exponent > -15:
        exponent += F16_EXPONENT_BIAS
        mantissa >>= F16_MANTISSA_SHIFT
        f16 = sign | exponent << F16_EXPONENT_SHIFT | mantissa
    else:
        f16 = sign
    return f16


class FmdlManagerBase:

    def __init__(self, base_path, tempfile_path):
        self.model_type = None
        self.process_normals = False
        self.temp_path = ""
        self.img_search_path = ""
        self.export_offset = 0
        self.export_vertex_offset = 0
        self.vertex_header_position = 0
        self.trailing_data_start = 0
        self.trailing_data_end = 0
        self.byte_16 = 0
        self.byte_32 = 0
        self.section0_header_count = 0
        self.section1_header_count = 0
        self.section0_offset = 0
        self.section1_offset = 0
        self.Section0_length = 0
        self.section1_length = 0
        self.section0_block_list = {}
        self.section1_block_list = {}
        self.skeleton_flag = False
        self.skeleton_list = []
        self.mesh_group_def_list = []
        self.object_assignment_list = []
        self.object_data_list = []
        self.block4_data_list = []
        self.bone_group_list = []
        self.block6_data_list = []
        self.mat_param_data_list = []
        self.block8_data_list = []
        self.block9_data_list = []
        self.vbuffer_def_list = []
        self.vert_format_def_list = []
        self.string_buffer_list = []
        self.string_list = []
        self.block13_data_list = []
        self.buffer_offset_list = []
        self.lod_list = []
        self.face_index_table_list = []
        self.block18_data_list = []
        self.block20_data_list = []
        self.block1_0_data_list = []
        self.block1_1_data_list = []
        self.vformat_per_submesh_list = []
        self.local_mesh_data = []
        self.internal_ex_submesh_vert_weights_list = []
        self.internal_mesh_list = []
        self.material_assignment = []
        self.textures = []
        self.sourceimages_path = os.path.normpath(os.path.join(os.path.dirname(base_path), '..',
                                                               'sourceimages/#windx11'))
        self.vertexgroup_disable = True
        self.auto_smooth = True
        self.temp_path = tempfile_path
        super().__init__()

    def parse_fmdl(self, work_filepath):
        print("Opening fmdl file: ", work_filepath)
        sub_mesh_list = []
        work_file = open(work_filepath, 'rb')
        work_file.seek(16, 0)
        self.byte_16 = unpack("B", work_file.read(1))[0]
        work_file.seek(7, 1)
        self.byte_32 = unpack("B", work_file.read(1))[0]
        work_file.seek(7, 1)

        self.section0_header_count, self.section1_header_count = unpack("2I", work_file.read(8))
        self.section0_offset, self.Section0_length = unpack("2I", work_file.read(8))
        self.section1_offset, self.section1_length = unpack("2I", work_file.read(8))

        work_file.seek(8, 1)

        for data_block0 in range(self.section0_header_count):
            block_id = unpack("H", work_file.read(2))[0]
            entry_count = unpack("H", work_file.read(2))[0]
            block_offset = unpack("I", work_file.read(4))[0]
            self.section0_block_list[block_id] = (block_id, entry_count, block_offset)

        # print ("entry1 ",work_file.tell(),"\n")
        for data_block1 in range(self.section1_header_count):
            block_id, block_offset, block_size = unpack("3I", work_file.read(12))
            self.section1_block_list[block_id] = (block_id, block_offset, block_size)

        sub_mesh_count = self.section0_block_list[3][1]
        log("sub_mesh_count", sub_mesh_count)

        # get skeleton if available
        if self.section0_block_list.get(0) is not None:
            self.skeleton_flag = True

        if self.skeleton_flag:
            work_file.seek(self.section0_offset + self.section0_block_list[0][2], 0)
            log("\n0x00   Skelly@", work_file.tell())
            for bn in range(self.section0_block_list[0][1]):
                bone_id, bone_parent, bounding_box_id, unknown0, unknown1, padding0 = unpack("6H", work_file.read(12))

                padding1 = unpack("I", work_file.read(4))

                bx_l, by_l, bz_l, bw_l = unpack("4f", work_file.read(16))  # local
                bx_w, by_w, bz_w, bw_w = unpack("4f", work_file.read(16))  # world

                self.skeleton_list.append((bone_id, bone_parent, bounding_box_id, unknown0, unknown1, padding0, bx_l,
                                           by_l, bz_l, bw_l, bx_w, by_w, bz_w, bw_w))
                log("bone@", work_file.tell())
                log("bone", bone_id, bone_parent, bounding_box_id, unknown0, unknown1, padding0)
                log("Coords:", by_l, bx_l, bz_l, bw_l, "Coords2:", bx_w, by_w, bz_w, bw_w)  # 0xFFFF = root
            log("Block13 data:not printed")

        # get mesh group defs
        work_file.seek(self.section0_offset + self.section0_block_list[1][2], 0)
        log("\nOxO1   mesh group def@", work_file.tell())
        for mgd in range(self.section0_block_list[1][1]):
            name_position = unpack("H", work_file.read(2))[0]
            invis_flag, pad = unpack("2B", work_file.read(2))
            parent_id, unknown = unpack("2H", work_file.read(4))
            self.mesh_group_def_list.append((name_position, invis_flag, parent_id))

            log("mesh_group_def", name_position, invis_flag, parent_id, unknown)

        # get object assignment table
        work_file.seek(self.section0_offset + self.section0_block_list[2][2], 0)
        log("\n0x02   Obj table@", work_file.tell())
        for oba in range(self.section0_block_list[2][1]):
            pad0, mesh_group_id, mesh_group_obj_count, preceding_obj_count, entry_id, pad1, unknown = unpack("I4HIH",
                                                                                                             work_file.read(
                                                                                                                 18))
            work_file.seek(14, 1)
            self.object_assignment_list.append(
                (mesh_group_id, mesh_group_obj_count, preceding_obj_count, entry_id, unknown))

            log("obj group", pad0, mesh_group_id, mesh_group_obj_count, preceding_obj_count, entry_id, pad1,
                unknown)

        print("Object assignment list: ", self.object_assignment_list)

        # get object data (get vert counts)
        work_file.seek(self.section0_offset + self.section0_block_list[3][2], 0)
        log("\n0x03   Obj data@", work_file.tell())
        for obd in range(self.section0_block_list[3][1]):
            unknown_int = unpack("I", work_file.read(4))[0]
            mat_instance_id, bone_group_id, entry_id, vert_count = unpack("4H", work_file.read(8))
            work_file.seek(4, 1)  # padding
            first_face_vert_id, face_vert_count = unpack("2I", work_file.read(8))
            unknown_long = unpack("I", work_file.read(4))[0]
            work_file.seek(20, 1)

            self.object_data_list.append((unknown_int, mat_instance_id, bone_group_id, entry_id, vert_count,
                                          first_face_vert_id, face_vert_count, unknown_long))
            sub_mesh_list.append((vert_count, first_face_vert_id, face_vert_count))

            print("Obj data", unknown_int, mat_instance_id, bone_group_id, entry_id, vert_count, first_face_vert_id,
                  face_vert_count, unknown_long)

            print("Material instance id: ", mat_instance_id)
            new_material_assignment = MaterialAssignment(
                material_index=mat_instance_id, mesh_index=entry_id, name_index=0)
            self.material_assignment.append(new_material_assignment)

        # get Material instance def
        work_file.seek(self.section0_offset + self.section0_block_list[4][2], 0)
        log("\n0x04 Mat instance def@", work_file.tell())
        for mtu in range(self.section0_block_list[4][1]):
            name_position, pad_short, material_index = unpack("3H", work_file.read(6))
            texture_count, parameter_count = unpack("2B", work_file.read(2))
            first_texture_index, first_parameter_index, pad_int = unpack("2HI", work_file.read(8))
            self.block4_data_list.append(
                (name_position, material_index, texture_count, parameter_count, first_texture_index,
                 first_parameter_index))
            self.material_assignment[material_index].name_index = name_position

        print("Block4 data (material instance)", self.block4_data_list)

        # get bone group table
        if self.skeleton_flag:
            work_file.seek(self.section0_offset + self.section0_block_list[5][2], 0)
            log("\n0x05   Bone group table@", work_file.tell())
            for ob in range(self.section0_block_list[5][1]):

                unknown_int, bone_entry_count = unpack("2H", work_file.read(4))
                bone_entry_list = []
                for bec in range(bone_entry_count):
                    bone_entry = unpack("H", work_file.read(2))[0]
                    bone_entry_list.append(bone_entry)
                work_file.seek(64 - bone_entry_count * 2, 1)
                self.bone_group_list.append((unknown_int, bone_entry_count, bone_entry_list))
                log("bone group", unknown_int, bone_entry_count, "\nbone_entry_list", bone_entry_list)
            log("Bone Groups:not printed")

        # get texture defs
        work_file.seek(self.section0_offset + self.section0_block_list[6][2], 0)
        log("\n0x06 Texture defs@", work_file.tell())
        for te in range(self.section0_block_list[6][1]):
            name_position, texture_name_position = unpack("2H", work_file.read(4))
            self.block6_data_list.append((name_position, texture_name_position))
            print("Block6 data", name_position, texture_name_position)
            self.textures.append(Texture(name_index=name_position, path_index=texture_name_position))

        # get material parameter defs
        work_file.seek(self.section0_offset + self.section0_block_list[7][2], 0)
        log("\n0x07 Mat param Defs@", work_file.tell())
        for mpd in range(self.section0_block_list[7][1]):
            mat_param_type_name_position, mat_param_name_position = unpack("2H", work_file.read(4))
            self.mat_param_data_list.append((mat_param_type_name_position, mat_param_name_position))
            log("Mat param data", mat_param_type_name_position, mat_param_name_position)
        log("Mat param Defs:not printed")

        # get Material type defs
        work_file.seek(self.section0_offset + self.section0_block_list[8][2], 0)
        log("\n0x08 Mat type defs@", work_file.tell())
        for bl8 in range(self.section0_block_list[8][1]):
            string_id, material_type = unpack("2H", work_file.read(4))
            self.block8_data_list.append((string_id, material_type))
            log("Block8 data", string_id, material_type)
        log("Mat type defs:not printed")

        # get mesh format assignment
        work_file.seek(self.section0_offset + self.section0_block_list[9][2], 0)
        log("\n0x09 Mesh format assignment@", work_file.tell())
        for bl9 in range(self.section0_block_list[9][1]):
            mesh_fe_count, vert_fe_count, unknown_short, first_mfe_id, first_vfd_id = unpack("2B3H", work_file.read(8))
            self.block9_data_list.append((mesh_fe_count, vert_fe_count, unknown_short, first_mfe_id, first_vfd_id))
            log("Block9 data", mesh_fe_count, vert_fe_count, unknown_short, first_mfe_id, first_vfd_id)
        log("Mesh format def:not printed")

        #
        work_file.seek(self.section0_offset + self.section0_block_list[10][2], 0)
        log("\n0x0A VBuffer Defs@", work_file.tell())
        for vbd in range(self.section0_block_list[10][1]):
            buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset = unpack("4BI", work_file.read(8))
            self.vbuffer_def_list.append((buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset))
            log("Vbuffer data", buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset)
        log("Block10 data:not printed")

        # get block11, data types unknown, each entry 4 bytes long
        work_file.seek(self.section0_offset + self.section0_block_list[11][2], 0)
        log("\n0x0B Vertex format defs@", work_file.tell())
        for blb in range(self.section0_block_list[11][1]):
            usage, data_type, format_offset = unpack("2BH", work_file.read(4))
            self.vert_format_def_list.append((usage, data_type, format_offset))
            log("Vert format def", usage, data_type, format_offset)
        log("Block11 data:not printed")

        # fetch string buffer data
        work_file.seek(self.section0_offset + self.section0_block_list[12][2], 0)
        log("\n0x0C String Buffer@", work_file.tell())
        for sb in range(self.section0_block_list[12][1]):
            string_type, string_length, string_offset = unpack("2HI", work_file.read(8))
            self.string_buffer_list.append((string_type, string_length, string_offset))

        # fetch strings
        self.string_list.clear()
        for sa in range(self.section0_block_list[12][1]):
            work_file.seek(self.section1_offset + self.section1_block_list[3][1] + self.string_buffer_list[sa][2], 0)
            temp_string_length = self.string_buffer_list[sa][1]
            unpack_string = str(temp_string_length) + "s"
            temp_string = unpack(unpack_string, work_file.read(temp_string_length))[0]
            self.string_list.append(temp_string.decode("utf-8"))
        print("String list: ", self.string_list)

        # get Bounding box defs
        work_file.seek(self.section0_offset + self.section0_block_list[13][2], 0)
        log("\n0x0D Bounding box defs@", work_file.tell())
        for bld in range(self.section0_block_list[13][1]):
            d_0, d_1, d_2, d_3 = unpack("4f", work_file.read(16))
            d_4, d_5, d_6, d_7 = unpack("4f", work_file.read(16))
            self.block13_data_list.append((d_0, d_1, d_2, d_3, d_4, d_5, d_6, d_7))
            log("Block13 data", d_0, d_1, d_2, d_3, d_4, d_5, d_6, d_7)
        log("Bounding box defs:not printed")

        # Get buffer offset table
        work_file.seek(self.section0_offset + self.section0_block_list[14][2], 0)
        log("\n0x0E buffer offset table@", work_file.tell())
        for bot in range(self.section0_block_list[14][1]):
            unknown_int, buffer_size, buffer_offset, padding = unpack("4I", work_file.read(
                16))  # unknown_int might be EoF flag
            self.buffer_offset_list.append((unknown_int, buffer_size, buffer_offset))
            log("buffer offset table", unknown_int, buffer_size, buffer_offset, padding)

        # block 0x0f = Error 404 block not found

        # get LOD info
        work_file.seek(self.section0_offset + self.section0_block_list[16][2], 0)
        log("\n0x10 Lod info@", work_file.tell())
        for lfi in range(self.section0_block_list[16][1]):
            lod_count, hd_distance, sd_distance, lo_distance = unpack("I3f", work_file.read(16))
            self.lod_list.append((lod_count, hd_distance, sd_distance, lo_distance))
            log("Lod data", lod_count, hd_distance, sd_distance, lo_distance)

        # get LOD face index table
        work_file.seek(self.section0_offset + self.section0_block_list[17][2], 0)
        log("\n0x11 face index table@", work_file.tell())
        for blfi in range(self.section0_block_list[17][1]):
            preceeding_face_vert_count, face_vert_count = unpack("2I", work_file.read(8))
            self.face_index_table_list.append((preceeding_face_vert_count, face_vert_count))
            log("face index table", preceeding_face_vert_count, face_vert_count)
        log("Block11 data:not printed")

        # get block18, unknown purpose, 8 byte entries always all 0s
        work_file.seek(self.section0_offset + self.section0_block_list[18][2], 0)
        log("\n0x12 Block18@", work_file.tell())
        for bln in range(self.section0_block_list[18][1]):
            entry_bin = work_file.read(8)
            self.block18_data_list.append(entry_bin)
            log("Block18 data", entry_bin)
        log("Block18 data:not printed")

        # block 0x13 = Error 404 block not found

        # get block20, unknown purpose and data types currently assumed 32 bytes long
        work_file.seek(self.section0_offset + self.section0_block_list[20][2], 0)
        log("\n0x14 Block20@", work_file.tell())
        for bln in range(self.section0_block_list[20][1]):
            entry_bin = work_file.read(32)
            self.block20_data_list.append(entry_bin)
            log("Block20 data", entry_bin)
        log("Block20 data:not printed")

        # 8 bytes of padding (rounds header to nearest 16)
        # 96 bytes of padding before the section1 headers start

        ##--section 1 headers below --

        # section1 header 0 start, unknown purpose, 16 bytes of 0s
        work_file.seek(self.section1_offset + self.section1_block_list[0][1], 0)
        log("\nSection1-0@", work_file.tell())
        entry_bin = work_file.read(self.section1_block_list[0][2])
        self.block1_0_data_list.append(entry_bin)
        log("Section1-0 data", entry_bin)
        log("Block1-0 data:not printed")

        # section1 header 1 start, unknown purpose
        if self.section1_block_list.get(1) is not None:
            work_file.seek(self.section1_offset + self.section1_block_list[1][1], 0)
            log("\nSection1-1@", work_file.tell())
            entry_bin = work_file.read(self.section1_block_list[1][2])
            self.block1_1_data_list.append(entry_bin)
            log("Section1-1 data", entry_bin)
            log("Block1-1 data:not printed")

        # get header 2
        work_file.seek(self.section1_offset + self.section1_block_list[2][1], 0)
        log("\nSection1-2@", work_file.tell())

        # Below is where the mesh is constructed
        #
        #
        #

        # Get Mesh Geometry
        buffer_offset1 = self.section1_block_list[2][1]

        vertex_list_offset = self.section1_offset + buffer_offset1

        uv_buffer_offset = self.buffer_offset_list[1][2]
        uv_list_offset = self.section1_offset + buffer_offset1 + uv_buffer_offset
        log("\nuv_list_offset", uv_list_offset)
        log("uv_list_size  ", self.buffer_offset_list[1][1])

        face_buffer_offset = self.buffer_offset_list[2][2]
        face_list_offset = self.section1_offset + buffer_offset1 + face_buffer_offset
        log("\nface_list_offset ", face_list_offset)

        # organize skeleton list into specific lists
        # bone_list=[]
        bone_position_list = []
        bone_name_list = []
        submesh_bone_names_list = []
        if self.skeleton_flag:
            for bone_ent in range(len(self.skeleton_list)):
                # bone_list.append(self.skeleton_list[bone_ent][0])
                b_x = self.skeleton_list[bone_ent][6]
                b_y = self.skeleton_list[bone_ent][7]
                b_z = self.skeleton_list[bone_ent][8]
                bone_position_list.append((b_x, b_y, b_z))
                bone_name_list.append(self.string_list[bone_ent + 1])
            if not self.vertexgroup_disable:
                mesh_rig = generate_skeleton(self.model_type, bone_name_list, bone_position_list)

            for bgl in range(len(self.bone_group_list)):
                sub_list = []
                for name_entry in range(len(self.bone_group_list[bgl][2])):
                    bone_name = bone_name_list[self.bone_group_list[bgl][2][name_entry]]
                    sub_list.append(bone_name)
                submesh_bone_names_list.append(sub_list)

            log("bone sub lists")
            log(submesh_bone_names_list)

        # construct list of MTL strings
        first_mtl_string = 1
        first_mtl_string += len(self.skeleton_list)

        mtl_list = self.string_list[first_mtl_string:]
        log("MTL list")
        log(mtl_list)

        # organize format list into a list per submesh
        format_sublist = []
        for ent in range(len(self.vert_format_def_list)):
            if self.vert_format_def_list[ent][0] == 0:
                if len(format_sublist) != 0:
                    self.vformat_per_submesh_list.append(format_sublist)
                    format_sublist = [0]
                else:
                    format_sublist.append(0)
            else:
                format_sublist.append(self.vert_format_def_list[ent][0])
        self.vformat_per_submesh_list.append(format_sublist)  # add last list, sloppy cleanup code

        log("vformat", self.vformat_per_submesh_list)

        for subm in range(sub_mesh_count):
            vertexlist, uvlist, facelist = [], [], []
            uvlist_normal = []
            bone_weight_list = []
            bone_id_list = []
            vertex_color_list = []

            sub_mesh_verts = sub_mesh_list[subm][0]
            sub_mesh_format = self.vformat_per_submesh_list[subm]
            v_normals_list = []

            work_file.seek(vertex_list_offset, 0)
            for vert in range(sub_mesh_verts):
                x, z, y = unpack("3f", work_file.read(12))
                vertexlist.append((x, y * -1, z))  # flip from fox engine orientation
            # print ("Vert list end ",work_file.tell(),"\n")

            # seek to next vertex block
            while (work_file.tell() % 16) != 0:
                work_file.seek(4, 1)
            vertex_list_offset = work_file.tell()

            work_file.seek(uv_list_offset)
            if self.process_normals:
                normals_data_file = open(os.path.join(self.temp_path, self.model_type.lower() + "_normals_data.bin"),
                                         "ab")
                tangents_data_file = open(os.path.join(self.temp_path, self.model_type.lower() + "_tangents_data.bin"),
                                          "ab")
            for uvc in range(sub_mesh_verts):
                for ent in range(len(sub_mesh_format)):
                    current_usage = sub_mesh_format[ent]
                    # the order in which these are evaluated is very important
                    if current_usage == 2:  # normals
                        norm_x, norm_y, norm_z, norm_w = unpack("4H", work_file.read(8))  # actually half floats
                        if self.process_normals:
                            normals_data_file.write(pack("4H", norm_x, norm_y, norm_z, norm_w))
                        sx = halffloat2float(norm_x)
                        sy = halffloat2float(norm_y)
                        sz = halffloat2float(norm_z)
                        sw = halffloat2float(norm_w)
                        str0 = pack('I', sx)
                        str1 = pack('I', sy)
                        str2 = pack('I', sz)
                        str3 = pack('I', sw)
                        fl_x = unpack('f', str0)[0]
                        fl_y = unpack('f', str1)[0]
                        fl_z = unpack('f', str2)[0]
                        fl_w = unpack('f', str3)[0]
                        v_normals_list.append((fl_x, fl_z * -1, fl_y))  # flip from fox engine orientation
                    if current_usage == 14:  # tangents
                        tan_x, tan_y, tan_z, tan_w = unpack("4H", work_file.read(8))  # actually half floats
                        if self.process_normals:
                            tangents_data_file.write(pack("4H", tan_x, tan_y, tan_z, tan_w))
                    if current_usage == 3:  # color
                        r, g, b, a = unpack("4B", work_file.read(4))
                        vertex_color_list.append((r / 255, g / 255, b / 255, a / 255))
                    if current_usage == 1:  # bone weight
                        bw0, bw1, bw2, bw3 = unpack("4B", work_file.read(4))
                        bone_weight_list.append((bw0 / 255, bw1 / 255, bw2 / 255, bw3 / 255))
                    if current_usage == 7:  # bone ids
                        bid0, bid1, bid2, bid3 = unpack("4B", work_file.read(4))
                        bone_id_list.append((bid0, bid1, bid2, bid3))
                    if current_usage == 8:  # UV
                        tu, tv = unpack("2H", work_file.read(4))
                        su = halffloat2float(tu)
                        sv = halffloat2float(tv)
                        str0 = pack('I', su)
                        str1 = pack('I', sv)
                        fu = unpack('f', str0)[0]
                        fv = unpack('f', str1)[0]
                        uvlist.append((fu, (fv - 1) * -1))
                    if current_usage == 9:  # UV2
                        nu, nv = unpack("2H", work_file.read(4))
                        snu = halffloat2float(nu)
                        snv = halffloat2float(nv)
                        str2 = pack('I', snu)
                        str3 = pack('I', snv)
                        fnu = unpack('f', str2)[0]
                        fnv = unpack('f', str3)[0]
                        uvlist_normal.append((fnu, (fnv * -1) + 1))
            if self.process_normals:
                normals_data_file.flush(), normals_data_file.close()
                tangents_data_file.flush(), tangents_data_file.close()
            while (work_file.tell() % 16) != 0:
                work_file.seek(4, 1)
            uv_list_offset = work_file.tell()

            work_file.seek(face_list_offset + (sub_mesh_list[subm][1] * 2),
                           0)  # change sub_mesh_list[0][1] to -> sub_mesh_list[subm][1]
            log("face_start ", work_file.tell())
            for face in range(int(sub_mesh_list[subm][2] / 3)):  # change face_nodes to -> sub_mesh_list[subm][2]
                f1, f2, f3 = unpack("3H", work_file.read(6))
                facelist.append((f3, f2, f1))
            log("face_end   ", work_file.tell())

            # attempt to construct mesh
            submesh_name = self.model_type + "_" + str(subm)
            print("Creating object ", submesh_name)
            submesh_object = allocate_object(submesh_name, vertexlist, facelist)
            print(self.internal_mesh_list)
            self.internal_mesh_list.append(submesh_object)
            allocate_maps(submesh_object, facelist, uvlist, uvlist_normal)

            # attempt to apply custom vertex normals???
            sub_mesh_data = submesh_object.data
            # sub_mesh_data.normals_split_custom_set(v_normals_list) #doesn't work
            if self.auto_smooth:
                for f in sub_mesh_data.polygons:
                    f.use_smooth = True
                sub_mesh_data.normals_split_custom_set_from_vertices(v_normals_list)
                sub_mesh_data.use_auto_smooth = True
            # apply vertex colors
            if len(vertex_color_list) != 0:
                set_vertex_colors(submesh_object.data, vertex_color_list)
                if self.process_normals:
                    self.color_vertex(submesh_object.data)
            self.local_mesh_data.append(sub_mesh_data)
            # populate sring list for editing
            if subm == 1:
                for st in range(len(mtl_list)):
                    item = submesh_object.fmdl_strings.add()
                    item.name = mtl_list[st]
                    print("item.name = ", mtl_list[st])
            # link to skeleton
            if self.skeleton_flag:
                if not self.vertexgroup_disable:
                    mod = submesh_object.modifiers.new(self.model_type + '_rig_modifier', 'ARMATURE')
                    mod.object = mesh_rig
                    mod.use_bone_envelopes = False
                    mod.use_vertex_groups = True
                    mesh_rig.select = False
                    bone_group_id = self.object_data_list[subm][2]
                    bone_sub_list = submesh_bone_names_list[bone_group_id]
                    set_vertex_weights(submesh_object, bone_sub_list, bone_id_list, bone_weight_list)
                else:
                    bone_group_id = self.object_data_list[subm][2]
                    bone_sub_list = submesh_bone_names_list[bone_group_id]
                    set_vertex_weights(submesh_object, bone_sub_list, bone_id_list, bone_weight_list)
                    self.internal_ex_submesh_vert_weights_list.append(
                        collect_vertex_weights(submesh_object.data.vertices))
                    remove_vertex_weights(submesh_object, bone_sub_list)

    def importmodel(self, file_path):
        # reinitialize all variables
        self.byte_16 = 0
        self.byte_32 = 0

        self.section0_header_count = 0
        self.section1_header_count = 0

        self.section0_offset = 0
        self.section1_offset = 0

        self.Section0_length = 0
        self.section1_length = 0

        self.section0_block_list = {}
        self.section1_block_list = {}
        self.skeleton_flag = False
        self.skeleton_list = []
        self.mesh_group_def_list = []
        self.object_assignment_list = []
        self.object_data_list = []
        self.block4_data_list = []
        self.bone_group_list = []
        self.block6_data_list = []
        self.mat_param_data_list = []
        self.block8_data_list = []
        self.block9_data_list = []
        self.vbuffer_def_list = []
        self.vert_format_def_list = []
        self.string_buffer_list, string_list = [], []
        self.block13_data_list = []
        self.buffer_offset_list = []
        self.lod_list = []
        self.face_index_table_list = []
        self.block18_data_list = []
        self.block20_data_list = []
        self.block1_0_data_list = []
        self.block1_1_data_list = []
        self.vformat_per_submesh_list = []
        self.img_search_path = os.path.dirname(file_path) + os.sep
        self.internal_ex_submesh_vert_weights_list.clear()

        self.parse_fmdl(file_path)
        self.show_materials()
        return self.local_mesh_data

    def exportmodel(self, fmdl_filename):
        scn = bpy.context.scene
        submesh_vert_count_list = []

        ex_section1_block_list = []

        submesh_vertex_list = []
        ex_submesh_face_tuple_list = []
        ex_submesh_uv_list = []
        ex_submesh_nrm_uv_list = []
        ex_submesh_count = 0
        ex_custom_normals_list = []
        ex_custom_tangents_list = []

        ex_submesh_vert_weights_list = []
        ex_submesh_vert_color_list = []
        ex_vbuffer_def_list = []
        ex_buffer_offset_list = []

        ex_string_defs = []
        ex_string_list = []
        ex_mtl_strings = []

        objlist = collect_objects(self.model_type)
        ex_submesh_count = len(objlist)

        for count, obj in enumerate(objlist):
            # obj.data.calc_tessface()  # supresses tessalation error when getting UV data
            obj.data.calc_loop_triangles()
            submesh_vert_count_list.append(len(obj.data.vertices))
            submesh_vertex_list.append(obj.data.vertices)

            face_list = get_face_tuples(obj)
            ex_submesh_face_tuple_list.append(face_list)

            uv_list = get_uv_map(obj, "UVMap")
            ex_submesh_uv_list.append(uv_list)

            if "normal_map" in obj.data.uv_layers:
                uv_nrml_list = get_uv_map(obj, "normal_map")
            else:
                uv_nrml_list = get_uv_map(obj, "UVMap")
            ex_submesh_nrm_uv_list.append(uv_nrml_list)

            log("Custom normals?", obj.data.has_custom_normals)
            custom_nrm_list = get_custom_vertex_normals(obj, "UVMap")
            ex_custom_normals_list.append(custom_nrm_list)

            if "normal_map" in obj.data.uv_layers:
                custom_tan_list = get_custom_vertex_tangents(obj, "normal_map")
            else:
                custom_tan_list = get_custom_vertex_tangents(obj, "UVMap")
            ex_custom_tangents_list.append(custom_tan_list)

            if self.skeleton_flag and False:  # bpy.context.scene.vertexgroup:
                ex_submesh_vert_weights_list.append(collect_vertex_weights(obj.data.vertices))

            if True:  # "Hair_Anim" in obj.data.vertex_colors:
                color_list = []
                for color in obj.data.vertex_colors.keys():
                    color_list = collect_vertex_colors(obj.data, color)
                ex_submesh_vert_color_list.append(color_list)  # keeps indexes synced with submeshes
            else:
                color_list = []
                ex_submesh_vert_color_list.append(color_list)  # keeps indexes synced with submeshes

            if count == 1:
                for ent in range(len(obj.fmdl_strings)):
                    ex_mtl_strings.append(obj.fmdl_strings[ent].name)

        # Precalculation segment
        #

        # 0x0A  precalc vertex buffer def list
        vbuff_def_sub_mesh = -1
        vbuff_def_vert_offset = 0
        vbuff_def_uv_offset = 0
        vbuff_def_type_2_offset = 0
        vbuff_def_type_3_offset = 0
        for obj in range(self.section0_block_list[10][1]):
            buffer_offset_id = self.vbuffer_def_list[obj][0]
            vert_fe_count = self.vbuffer_def_list[obj][1]
            buffer_length = self.vbuffer_def_list[obj][2]
            mfd_type = self.vbuffer_def_list[obj][3]
            if mfd_type == 0:
                vbuff_def_sub_mesh += 1  # update submesh count

                buffer_offset = vbuff_def_vert_offset

                new_vert_offset = submesh_vert_count_list[vbuff_def_sub_mesh] * buffer_length
                while (new_vert_offset % 16) != 0:
                    new_vert_offset += 4
                vbuff_def_vert_offset += new_vert_offset

            elif mfd_type == 1:
                buffer_offset = vbuff_def_uv_offset

                new_vert_offset = submesh_vert_count_list[vbuff_def_sub_mesh] * buffer_length
                while (new_vert_offset % 16) != 0:
                    new_vert_offset += 4
                vbuff_def_uv_offset += new_vert_offset

            elif mfd_type == 2:
                if vbuff_def_sub_mesh > 0 and vbuff_def_type_2_offset == 0:
                    vbuff_def_type_2_offset = vbuff_def_uv_offset
                else:
                    buffer_offset = vbuff_def_type_2_offset

                    new_vert_offset = submesh_vert_count_list[vbuff_def_sub_mesh] * buffer_length
                    while (new_vert_offset % 16) != 0:
                        new_vert_offset += 4
                    vbuff_def_type_2_offset += new_vert_offset

            elif mfd_type == 3:
                buffer_offset = vbuff_def_type_3_offset

                new_vert_offset = submesh_vert_count_list[vbuff_def_sub_mesh] * buffer_length
                while (new_vert_offset % 16) != 0:
                    new_vert_offset += 4
                vbuff_def_type_3_offset += new_vert_offset

            else:
                raise Exception("0x0A: Unexpected type in vbuff def list")

            ex_vbuffer_def_list.append((buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset))
            log("calc vbuff defs", buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset)

        # 0x0C  setup string defs and table
        first_mtl_string = len(self.skeleton_list) + 1  # make sure aligns with offset during import
        ex_string_list = self.string_list[:first_mtl_string]
        ex_string_list = ex_string_list + ex_mtl_strings

        str_type = 3
        char_offset = 0
        for ste in range(len(ex_string_list)):
            char_length = len(ex_string_list[ste])
            ex_string_defs.append((str_type, char_length, char_offset))
            char_offset += char_length + 1

        # 0x0E precalc buffer offset table

        # default game files ocassionally have extra data written in the blocks, probably lod data
        # it's not known what that data represents if anything, as have not found headers that adress that data
        # This formula does not account for that data so exported files may differ from their imports

        vert_buffer_total = 0
        uv_buffer_total = 0
        face_buffer_total = 0
        format_entry_offset = 0
        log("subm_count", ex_submesh_count)

        for sbm in range(ex_submesh_count):
            sbm_v_count = submesh_vert_count_list[sbm]
            vert_bytes = sbm_v_count * 12
            rounded_bytes = vert_bytes
            while (rounded_bytes % 16) != 0:
                rounded_bytes += 4
            vert_buffer_total += rounded_bytes
            log("\ntotal vert bytes", vert_buffer_total)

            # self.block9_data_list
            uv_bytes = sbm_v_count * ex_vbuffer_def_list[format_entry_offset + 1][2]
            rounded_bytes = uv_bytes
            while (rounded_bytes % 16) != 0:
                rounded_bytes += 4
            uv_buffer_total += rounded_bytes
            log("total uv   bytes", uv_buffer_total)

            format_entry_offset += self.block9_data_list[sbm][0]

            sbm_f_count = len(ex_submesh_face_tuple_list[sbm])
            face_bytes = sbm_f_count * 6
            log("face_bytes", face_bytes)
            rounded_bytes = face_bytes

            face_buffer_total += rounded_bytes
            log("total face bytes", face_buffer_total)

        while (
                face_buffer_total % 16) != 0:  # might still need to pad out to bytes divisble by 16, but only at very end of block?
            face_buffer_total += 2

        # not sure if an extra 32 bytes is necessary for unknown block? seems to contain lod face vert indexes

        # not sure if hard code 3 entries is the best way to go, but it'll have to do for now
        ex_buffer_offset_list.append((self.buffer_offset_list[0][0], vert_buffer_total, 0))
        ex_buffer_offset_list.append((self.buffer_offset_list[1][0], uv_buffer_total, vert_buffer_total))
        ex_buffer_offset_list.append(
            (self.buffer_offset_list[2][0], face_buffer_total, uv_buffer_total + vert_buffer_total))

        # setup section 1 header values now that meshes have been calculated
        block1_offset = 0
        if self.section1_block_list.get(0) is not None:  # currently no idea of what this section does
            ex_size = self.section1_block_list[0][2]
            ex_section1_block_list.append((0, block1_offset, ex_size))
            block1_offset += ex_size
        if self.section1_block_list.get(1) is not None:  # currently no idea of what this section does
            ex_type = self.section1_block_list[1][0]
            ex_size = self.section1_block_list[1][2]
            ex_section1_block_list.append((1, block1_offset, ex_size))
            block1_offset += ex_size
        if self.section1_block_list.get(2) is not None:
            ex_size = vert_buffer_total + uv_buffer_total + face_buffer_total + 32  # extra 32 bytes for lod faces???
            ex_section1_block_list.append((2, block1_offset, ex_size))
            block1_offset += ex_size
        if self.section1_block_list.get(3) is not None:  # string block
            ex_size = self.section1_block_list[3][2]
            ex_section1_block_list.append((3, block1_offset, ex_size))
            block1_offset += ex_size

        # EXPORT segment, for the most part
        #

        ##set parameters, then pack

        export_file = open(fmdl_filename, 'wb')

        fmdl_string = "FMDL"
        export_file.write(pack("4s", fmdl_string.encode("utf-8")))
        export_file.write(pack("4B", 133, 235, 1, 64))  # replace values with hex literals for clarity
        export_file.write(pack("B7x", 64))

        export_file.write(
            pack("3B5x", self.byte_16, 127, 23))  # 255 for face/hair/suit =skeletons, 222 for ball = no skeletons

        export_file.write(pack("1B7x", self.byte_32))  # 15 for face/hair/suit =skeletons, 13 for ball

        #
        # FOR testing PURPOSES: just copy old header offsets,
        # in practice filler values may have to be written and then updated after the subheaders are filled in
        #

        export_file.write(pack("2I", self.section0_header_count,
                               self.section1_header_count))  # 19 for face/hair/suit =skeletons, 17 for ball
        export_file.write(pack("2I", self.section0_offset, self.Section0_length))  # offset =(header-count x 8) + 64
        export_file.write(pack("2I", self.section1_offset,
                               block1_offset))  # offset =(header-count x 12) + section0_offset + 4 [or bytes to make header divisble by 16]
        export_file.write(pack("8x"))

        for key in self.section0_block_list:
            export_file.write(
                pack("2H", self.section0_block_list[key][0], self.section0_block_list[key][1]))  # id, entry count
            # do math for section offsets
            export_file.write(
                pack("I", self.section0_block_list[key][2]))  # FOR testing PURPOSES: just copy the old offset

        for ent in range(len(ex_section1_block_list)):
            export_file.write(pack("I", ex_section1_block_list[ent][0]))  # id
            export_file.write(pack("I", ex_section1_block_list[ent][1]))  # offset
            export_file.write(pack("I", ex_section1_block_list[ent][2]))  # length

        filler_bytes = 16 - (export_file.tell() % 16)
        log("ex", export_file.tell())
        log("md", filler_bytes)
        export_file.write(pack(str(filler_bytes) + "x"))

        if self.skeleton_flag == True:
            for skl in range(self.section0_block_list[0][1]):
                bone_string_id = self.skeleton_list[skl][0]
                bone_parent = self.skeleton_list[skl][1]
                bounding_box_id = self.skeleton_list[skl][2]
                unknown_short0 = self.skeleton_list[skl][3]
                unknown_short1 = self.skeleton_list[skl][4]
                padding = self.skeleton_list[skl][5]
                bx_l = self.skeleton_list[skl][6]
                by_l = self.skeleton_list[skl][7]
                bz_l = self.skeleton_list[skl][8]
                bw_l = self.skeleton_list[skl][9]
                bx_w = self.skeleton_list[skl][10]
                by_w = self.skeleton_list[skl][11]
                bz_w = self.skeleton_list[skl][12]
                bw_w = self.skeleton_list[skl][13]

                export_file.write(
                    pack("6H", bone_string_id, bone_parent, bounding_box_id, unknown_short0, unknown_short1, padding))
                export_file.write(pack("4x"))
                export_file.write(pack("4f", bx_l, by_l, bz_l, bw_l))
                export_file.write(pack("4f", bx_w, by_w, bz_w, bw_w))

        for mgd in range(self.section0_block_list[1][1]):
            name_position = self.mesh_group_def_list[mgd][0]
            invisibility_flag = self.mesh_group_def_list[mgd][1]
            parent_id = self.mesh_group_def_list[mgd][2]
            export_file.write(pack("HBx2H", name_position, invisibility_flag, parent_id, 0xFFFF))

        for oba in range(self.section0_block_list[2][1]):
            mesh_group_id = self.object_assignment_list[oba][0]
            mesh_group_obj_count = self.object_assignment_list[oba][1]
            preceding_obj_count = self.object_assignment_list[oba][2]
            entry_id = self.object_assignment_list[oba][3]
            unknown_short = self.object_assignment_list[oba][4]

            export_file.write(pack("4x4H", mesh_group_id, mesh_group_obj_count, preceding_obj_count, entry_id))
            export_file.write(pack("4xH", unknown_short))
            export_file.write(pack("14x"))

        # Warning ---
        # face and hair model files have an undocumented behaviour that can add 6 or 12 verts to one of its first_face_vert_ids

        previous_face_vert_offset = 0
        for obd in range(self.section0_block_list[3][1]):
            unknown_int0 = self.object_data_list[obd][0]
            mat_instance_id = self.object_data_list[obd][1]
            bone_group_id = self.object_data_list[obd][2]
            entry_id = self.object_data_list[obd][
                3]  # should be equal to, but needs check for different submesh count than old file
            vert_count = submesh_vert_count_list[obd]
            first_face_vert_id = previous_face_vert_offset
            face_vert_count = len(ex_submesh_face_tuple_list[obd]) * 3
            unknown_int1 = self.object_data_list[obd][7]

            previous_face_vert_offset += len(ex_submesh_face_tuple_list[obd]) * 3

            export_file.write(pack("I4H", unknown_int0, mat_instance_id, bone_group_id, entry_id, vert_count))
            export_file.write(pack("4x3I", first_face_vert_id, face_vert_count, unknown_int1))
            export_file.write(pack("20x"))  # padding inaccurate?

            log("Obj data", bone_group_id, entry_id, vert_count, first_face_vert_id, face_vert_count)

        for bl4 in range(self.section0_block_list[4][1]):
            name_position = self.block4_data_list[bl4][0]
            section_8_entry_id = self.block4_data_list[bl4][1]
            unknown_byte0 = self.block4_data_list[bl4][2]
            unknown_byte1 = self.block4_data_list[bl4][3]
            unknown_short0 = self.block4_data_list[bl4][4]
            unknown_short1 = self.block4_data_list[bl4][5]

            export_file.write(pack("H2xH", name_position, section_8_entry_id))
            export_file.write(pack("2B", unknown_byte0, unknown_byte1))
            export_file.write(pack("2H4x", unknown_short0, unknown_short1))

        if self.skeleton_flag:
            for bg in range(self.section0_block_list[5][1]):
                unknown_short = self.bone_group_list[bg][0]
                bone_entry_count = self.bone_group_list[bg][1]
                export_file.write(pack("2H", unknown_short, bone_entry_count))

                bone_entry_list = self.bone_group_list[bg][2]
                for bec in range(bone_entry_count):
                    bone_entry = bone_entry_list[bec]
                    export_file.write(pack("H", bone_entry))

                pad_bytes = 64 - (bone_entry_count * 2)
                padding_string = str(pad_bytes) + "x"
                export_file.write(pack(padding_string))

        for te in range(self.section0_block_list[6][1]):
            name_position = self.block6_data_list[te][0]
            texture_name_position = self.block6_data_list[te][1]
            export_file.write(pack("2H", name_position, texture_name_position))

        for mpd in range(self.section0_block_list[7][1]):
            mat_param_type_name_position = self.mat_param_data_list[mpd][0]
            mat_param_name_position = self.mat_param_data_list[mpd][1]
            export_file.write(pack("2H", mat_param_type_name_position, mat_param_name_position))

        for bl8 in range(self.section0_block_list[8][1]):
            string_id = self.block8_data_list[bl8][0]
            material_type = self.block8_data_list[bl8][1]
            export_file.write(pack("2H", string_id, material_type))

        for bl9 in range(self.section0_block_list[9][1]):
            mesh_fe_count = self.block9_data_list[bl9][0]
            vert_fe_count = self.block9_data_list[bl9][1]
            unknown_short = self.block9_data_list[bl9][2]
            first_mfe_id = self.block9_data_list[bl9][3]
            first_vfd_id = self.block9_data_list[bl9][4]
            export_file.write(pack("2B3H", mesh_fe_count, vert_fe_count, unknown_short, first_mfe_id, first_vfd_id))
            # entry_bin = self.block9_data_list[bl9]
            # export_file.write(entry_bin)

        for obj in range(self.section0_block_list[10][1]):
            buffer_offset_id = ex_vbuffer_def_list[obj][0]
            vert_fe_count = ex_vbuffer_def_list[obj][1]
            buffer_length = ex_vbuffer_def_list[obj][2]
            mfd_type = ex_vbuffer_def_list[obj][3]
            buffer_offset = ex_vbuffer_def_list[obj][4]
            export_file.write(pack("4B", buffer_offset_id, vert_fe_count, buffer_length, mfd_type))
            export_file.write(pack("I", buffer_offset))
            log("exp vbuff defs", buffer_offset_id, vert_fe_count, buffer_length, mfd_type, buffer_offset)

        for blb in range(self.section0_block_list[11][1]):
            usage = self.vert_format_def_list[blb][0]
            data_type = self.vert_format_def_list[blb][1]
            format_offset = self.vert_format_def_list[blb][2]
            export_file.write(pack("2BH", usage, data_type, format_offset))

        for sb in range(self.section0_block_list[12][1]):
            string_type = ex_string_defs[sb][0]
            string_length = ex_string_defs[sb][1]
            string_offset = ex_string_defs[sb][2]
            export_file.write(pack("2H", string_type, string_length))
            export_file.write(pack("I", string_offset))

        # dynamically pad block until divisble by 16
        while (export_file.tell() % 16) != 0:
            export_file.write(pack("2x"))

        for bld in range(self.section0_block_list[13][1]):
            d_0 = self.block13_data_list[bld][0]
            d_1 = self.block13_data_list[bld][1]
            d_2 = self.block13_data_list[bld][2]
            d_3 = self.block13_data_list[bld][3]
            d_4 = self.block13_data_list[bld][4]
            d_5 = self.block13_data_list[bld][5]
            d_6 = self.block13_data_list[bld][6]
            d_7 = self.block13_data_list[bld][7]
            export_file.write(pack("4f", d_0, d_1, d_2, d_3))
            export_file.write(pack("4f", d_4, d_5, d_6, d_7))

        for bot in range(self.section0_block_list[14][1]):  # missing 4 bytes before this block
            unknown_int = ex_buffer_offset_list[bot][0]  # possible end of file flag
            buffer_size = ex_buffer_offset_list[bot][1]
            buffer_offset = ex_buffer_offset_list[bot][2]

            export_file.write(pack("3I4x", unknown_int, buffer_size, buffer_offset))
            log("ex buff offset table", unknown_int, buffer_size, buffer_offset)

        for lfi in range(self.section0_block_list[16][1]):
            lod_count = self.lod_list[lfi][0]
            hd_distance = self.lod_list[lfi][1]
            sd_distance = self.lod_list[lfi][2]
            lo_distance = self.lod_list[lfi][3]
            export_file.write(pack("I3f", lod_count, hd_distance, sd_distance, lo_distance))
            log("Lod data", lod_count, hd_distance, sd_distance, lo_distance)

        # FOR testing PURPOSES: overwriting lod values, old copy code preserved in comment below
        log("Warning, LoDs eliminated")
        for blfi in range(int(self.section0_block_list[17][1] / 8)):  # presumably 8 entries per sub mesh
            preceeding_face_vert_count = 0
            face_vert_count = len(ex_submesh_face_tuple_list[blfi]) * 3
            export_file.write(
                pack("2I", preceeding_face_vert_count, face_vert_count))  # really lazy way of eliminating lods
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))

            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            export_file.write(pack("2I", preceeding_face_vert_count, face_vert_count))
            log("face index table", preceeding_face_vert_count, face_vert_count)

        for bln in range(self.section0_block_list[18][1]):
            entry_bin = self.block18_data_list[bln]
            export_file.write(entry_bin)

        for bln in range(self.section0_block_list[20][1]):
            entry_bin = self.block20_data_list[bln]
            export_file.write(entry_bin)

        while (export_file.tell() % 16) != 0:  # round out the bytes to 16
            export_file.write(pack("2x"))

        export_file.write(pack("96x"))

        # section 1-0
        log("Writing 1-0 @", export_file.tell())
        export_file.write(self.block1_0_data_list[0])
        log("1-0 bin", self.block1_0_data_list[0])
        log("1-0 len", len(self.block1_0_data_list[0]))

        # section 1-1
        log("Writing 1-1 @", export_file.tell())
        if self.section1_block_list.get(1) is not None:  # currently no idea of what this section does
            export_file.write(self.block1_1_data_list[0])
            log("1-1 bin", self.block1_1_data_list[0])

        # section 1-2 mesh data
        log("Writing 1-2 @", export_file.tell())
        # vertexes
        for sbm in range(ex_submesh_count):
            for vert in range(len(submesh_vertex_list[sbm])):
                x, y, z = submesh_vertex_list[sbm][vert].co
                export_file.write(pack("3f", x, z, y * -1))  # flip to fox engine orientation
            while (export_file.tell() % 16) != 0:  # round out the bytes to 16
                export_file.write(pack("2x"))

        # UV, normals, weighting, bone ids, etc
        if self.process_normals:
            normals_data_file = open(os.path.join(self.temp_path, self.model_type.lower() + "_normals_data.bin"), "rb")
            tangents_data_file = open(os.path.join(self.temp_path, self.model_type.lower() + "_tangents_data.bin"),
                                      "rb")
        for sbm in range(ex_submesh_count):
            sub_mesh_format = self.vformat_per_submesh_list[sbm]
            for vert in range(len(submesh_vertex_list[sbm])):
                for ent in range(len(sub_mesh_format)):
                    current_usage = sub_mesh_format[ent]
                    if current_usage == 2:  # normals
                        if self.process_normals:
                            try:
                                norm_x, norm_y, norm_z, norm_w = unpack("4H", normals_data_file.read(
                                    8))  # actually half floats
                                export_file.write(pack("4H", norm_x, norm_y, norm_z, norm_w))
                            except:
                                norm_x, norm_y, norm_z = ex_custom_normals_list[sbm][vert][1]
                                norm_w = 1.0
                                export_file.write(pack("4H", norm_x, norm_y, norm_z, norm_w))
                        else:
                            norm_x, norm_y, norm_z = ex_custom_normals_list[sbm][vert][1]
                            norm_w = 1.0
                            hf_x = float2halffloat(norm_x)
                            hf_y = float2halffloat(norm_z)  # flip to fox engine orientation
                            hf_z = float2halffloat(norm_y * -1)
                            hf_w = float2halffloat(norm_w)
                            export_file.write(pack("4H", hf_x, hf_y, hf_z, hf_w))

                    if current_usage == 14:  # tangents
                        if self.process_normals:
                            try:
                                tan_x, tan_y, tan_z, tan_w = unpack("4H", tangents_data_file.read(8))
                                export_file.write(pack("4H", tan_x, tan_y, tan_z, tan_w))
                            except:
                                tan_x, tan_y, tan_z = ex_custom_tangents_list[sbm][vert][1]
                                tan = normalize_tangents(tan_x, tan_y, tan_z)
                                tan_w = 1.0
                                hf_x = float2halffloat(tan[0])
                                hf_y = float2halffloat(tan[1] * -1)  # flip to fox engine orientation
                                hf_z = float2halffloat(tan[2] * -1)
                                hf_w = float2halffloat(tan_w)
                                export_file.write(pack("4H", hf_x, hf_z, hf_y, hf_w))
                        else:
                            tan_x, tan_y, tan_z = ex_custom_tangents_list[sbm][vert][1]
                            tan = normalize_tangents(tan_x, tan_y, tan_z)
                            tan_w = 1.0
                            hf_x = float2halffloat(tan[0])
                            hf_y = float2halffloat(tan[1] * -1)  # flip to fox engine orientation
                            hf_z = float2halffloat(tan[2] * -1)
                            hf_w = float2halffloat(tan_w)
                            export_file.write(pack("4H", hf_x, hf_z, hf_y, hf_w))

                    if current_usage == 3:  # color
                        ex_r = int(ex_submesh_vert_color_list[sbm][vert][0] * 255)
                        ex_g = int(ex_submesh_vert_color_list[sbm][vert][1] * 255)
                        ex_b = int(ex_submesh_vert_color_list[sbm][vert][2] * 255)
                        ex_a = 255
                        export_file.write(pack("4B", ex_r, ex_g, ex_b, ex_a))

                    if current_usage == 1:  # bone weight
                        if False:  # bpy.context.scene.vertexgroup:
                            bw_0 = int(
                                ex_submesh_vert_weights_list[sbm][vert][0][1] * 255)  # mesh, vertex, group, then weight
                            bw_1 = int(ex_submesh_vert_weights_list[sbm][vert][1][
                                           1] * 255)  # x255 to convert float value to byte
                            bw_2 = int(ex_submesh_vert_weights_list[sbm][vert][2][1] * 255)
                            bw_3 = int(ex_submesh_vert_weights_list[sbm][vert][3][1] * 255)
                            export_file.write(pack("4B", bw_0, bw_1, bw_2, bw_3))
                        else:
                            bw_0 = int(self.internal_ex_submesh_vert_weights_list[sbm][vert][0][
                                           1] * 255)  # mesh, vertex, group, then weight
                            bw_1 = int(self.internal_ex_submesh_vert_weights_list[sbm][vert][1][
                                           1] * 255)  # x255 to convert float value to byte
                            bw_2 = int(self.internal_ex_submesh_vert_weights_list[sbm][vert][2][1] * 255)
                            bw_3 = int(self.internal_ex_submesh_vert_weights_list[sbm][vert][3][1] * 255)
                            export_file.write(pack("4B", bw_0, bw_1, bw_2, bw_3))
                    if current_usage == 7:  # bone ids
                        if False:  # bpy.context.scene.vertexgroup:
                            bid_0 = ex_submesh_vert_weights_list[sbm][vert][0][0]  # mesh, vertex, group, then id
                            bid_1 = ex_submesh_vert_weights_list[sbm][vert][1][0]
                            bid_2 = ex_submesh_vert_weights_list[sbm][vert][2][0]
                            bid_3 = ex_submesh_vert_weights_list[sbm][vert][3][0]
                            export_file.write(pack("4B", bid_0, bid_1, bid_2, bid_3))
                        else:
                            bid_0 = self.internal_ex_submesh_vert_weights_list[sbm][vert][0][
                                0]  # mesh, vertex, group, then id
                            bid_1 = self.internal_ex_submesh_vert_weights_list[sbm][vert][1][0]
                            bid_2 = self.internal_ex_submesh_vert_weights_list[sbm][vert][2][0]
                            bid_3 = self.internal_ex_submesh_vert_weights_list[sbm][vert][3][0]
                            export_file.write(pack("4B", bid_0, bid_1, bid_2, bid_3))
                    if current_usage == 8:  # UV
                        coord_u = ex_submesh_uv_list[sbm][vert][0]
                        coord_v = ex_submesh_uv_list[sbm][vert][1]
                        hf_u = float2halffloat(coord_u)
                        hf_v = float2halffloat((coord_v - 1) * -1)
                        export_file.write(pack("2H", hf_u, hf_v))
                    if current_usage == 9:  # UV2
                        coord_u = ex_submesh_nrm_uv_list[sbm][vert][0]
                        coord_v = ex_submesh_nrm_uv_list[sbm][vert][1]
                        hf_u = float2halffloat(coord_u)
                        hf_v = float2halffloat((coord_v - 1) * -1)
                        export_file.write(pack("2H", hf_u, hf_v))
                    if current_usage == 10:  # UV3
                        export_file.write(pack("4x"))
                        log("3rd UV not implemented")
                    if current_usage == 11:  # UV4
                        export_file.write(pack("4x"))
                        log("4th UV not implemented")
                    if current_usage == 12:  # bone weight?
                        export_file.write(pack("4x"))
                        log("Secondary bone wieghts not implemented")
                    if current_usage == 13:  # bone id?
                        export_file.write(pack("4x"))
                        log("Secondary bone ids not implemented")

            while (export_file.tell() % 16) != 0:  # round out the bytes to 16
                export_file.write(pack("2x"))

        for sbm in range(ex_submesh_count):
            for ftl in range(len(ex_submesh_face_tuple_list[sbm])):
                f3 = ex_submesh_face_tuple_list[sbm][ftl][0]
                f2 = ex_submesh_face_tuple_list[sbm][ftl][1]
                f1 = ex_submesh_face_tuple_list[sbm][ftl][2]
                export_file.write(pack("3H", f1, f2, f3))
        while (export_file.tell() % 16) != 0:  # round out the bytes to 16
            export_file.write(pack("2x"))

        export_file.write(pack("32x"))  # FOR testing PURPOSES: possible lod related block, zeros for filler for now

        log("Writing 1-3 @", export_file.tell())
        for sa in range(self.section0_block_list[12][1]):
            pack_string = str(len(ex_string_list[sa])) + "sx"
            temp_string = ex_string_list[sa]
            export_file.write(pack(pack_string, temp_string.encode("utf-8")))
        export_file.flush()
        export_file.close()

    def color_vertex(self, obj_data):
        obj_data.vertex_colors.new(name=self.model_type + '_Anim')
        color_layer = obj_data.vertex_colors.active
        for poly in obj_data.polygons:
            for idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                color_layer.data[idx].color = (1.0, 1.0, 1.0, 1.0)

    def show_materials(self):
        print("Material assignment: ", self.material_assignment)
        print("Textures: ", self.textures)

        print("\tFound %d textures" % (len(self.textures)))
        print("\t\tblock 6: ", self.block6_data_list)
        print("\t\tblock 7: ", self.mat_param_data_list)
        for tup in self.block4_data_list:
            (name_index, mat_index, texture_count, param_count, first_texture_index, first_param_index) = tup
            material_name = self.string_list[name_index]
            print("\t%d - Texture: %s" % (name_index, material_name))

            texture_assignments = self.mat_param_data_list
            for texture_index in range(first_texture_index, first_texture_index + texture_count):
                if texture_index >= len(texture_assignments):
                    print("Texture index not found in block6? %d > %d" % (texture_index, len(texture_assignments)))
                else:
                    type_name_index, texture_definition_index = texture_assignments[texture_index]
                    texture_file_name_index, texture_folder_name_index = self.block6_data_list[texture_definition_index]
                    texture_file_name = self.string_list[texture_file_name_index]
                    type_name = self.string_list[type_name_index]
                    print("\t\t\tTexture type %s : %s" % (type_name, texture_file_name))
                    file_without_ext, ext = os.path.splitext(
                        os.path.join(os.path.normpath(self.sourceimages_path), texture_file_name))
                    png_file = file_without_ext + '.PNG'
                    if os.path.exists(png_file):
                        print("\t\tTexture applied to material '%s'" % png_file)
                    else:
                        print("\t\t--> file not found: '%s'", png_file)

        print("Default material assignments:")
        i = 0
        for mesh in self.internal_mesh_list:
            material_name = self.string_list[self.material_assignment[i].name_index]
            print("\tTexture '%s' assigned to mesh %d" % (material_name, i))
            i = i + 1
