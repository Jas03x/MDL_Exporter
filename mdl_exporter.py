
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
from mathutils import Matrix

import os
import struct

bl_info = {
    "name": "MDL format",
    "author": "Jas",
    "version": (0, 0, 1),
    "blender": (3, 6, 2),
    "location": "File > Import-Export",
    "description": "MDL scene exporter",
    "warning": "",
    "support": "COMMUNITY",
    "category": "Import-Export"
}

MDL_SIG     = 0x004C444D # 'MDL'
MDL_EOF     = 0x00464F45 # 'EOF'
MDL_LIST    = 0x5354494C # 'LIST'
MDL_BLOCK   = 0x004B4C42 # 'BLK'
MDL_VERTEX  = 0x00005856 # 'VX'
MDL_POLYGON = 0x00004750 # 'PG'
MDL_STRING  = 0x00525453 # 'STR'
MDL_MATRIX4 = 0x0034584D # 'MX4'
MDL_BONE    = 0x454E4F42 # 'BONE'
MDL_NODE    = 0x45444F4E # 'NODE'
MDL_MTL     = 0x004C544D # 'MTL'
MDL_MESH    = 0x4853454D # 'MESH'
MDL_TEXTURE = 0x54584554 # 'TEXT'
MDL_END     = 0x00444E45 # 'END'

class MDL_Vertex:
    def __init__(self, p, n, uv, node_index):
        self.position = tuple(p)
        self.normal = tuple(n)
        self.uv = tuple(uv)
        self.node_index = node_index
        self.bone_indices = [0, 0, 0, 0]
        self.bone_weights = [0, 0, 0, 0]
        self.bone_count = 0
        self.hash_value = 0
    
    def finalize(self):
        # make sure the weights sum to 1.0
        if self.bone_count > 0:
            weight_sum = sum(self.bone_weights)
            if weight_sum < 1.0:
                biggest_weight = max(self.bone_weights)
                self.bone_weights[self.bone_weights.index(biggest_weight)] += 1.0 - weight_sum

        self.bone_indices = tuple(self.bone_indices)
        self.bone_weights = tuple(self.bone_weights)
        self.hash_value = hash((self.position, self.normal, self.uv, self.node_index, self.bone_indices, self.bone_weights, self.bone_count))

    def __eq__(self, other):
        return (self.position == other.position) and (self.normal == other.normal) and (self.uv == other.uv) and (self.node_index == other.node_index) \
            and (self.bone_indices == other.bone_indices) and (self.bone_weights == other.bone_weights) and (self.bone_count == other.bone_count)

    def __hash__(self):
        return self.hash_value

class MDL_Polygon:
    def __init__(self):
        self.index_count = 0
        self.index_array = []

class MDL_Node:
    def __init__(self, name, parent, transform):
        self.name = name
        self.parent = parent
        self.transform = transform

class MDL_Bone:
    def __init__(self, name, offset_matrix):
        self.name = name
        self.offset_matrix = offset_matrix

class Index:
    def __init__(self):
        self.map = {}
        self.array = []

    def add(self, key, value):
        if self.map.get(key) != None:
            raise Exception("item {} already exists in index".format(key))
        self.map[key] = len(self.array)
        self.array.append(value)

    def get(self, key):
        return self.array[self.find(key)]
    
    def find(self, key):
        index = self.map.get(key, -1)
        if index == -1:
            raise Exception("item {} does not exist in index".format(key))
        return index
    
class MDL_Mesh:
    def __init__(self, name):
        self.name = name
        self.vertex_set = []
        self.vertex_map = {}
        self.polygon_array = []

class MDL_Model:
    def __init__(self):
        self.ambient_texture = None
        self.diffuse_texture = None
        self.specular_texture = None
        self.mesh_array = []
        self.bone_index = Index()
        self.node_index = Index()

class MDL_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL"

    filename_ext = ".mdl"

    def write_string(self, f, str):
        f.write(struct.pack("=I", MDL_STRING))
        if str == None:
            f.write(struct.pack("=BB", 0, 0))
        else:
            f.write(struct.pack("=B", len(str)))
            f.write(struct.pack("={}sB".format(len(str)), str.encode("utf-8"), 0))
        f.write(struct.pack("=I", MDL_END))
    
    def write_matrix(self, f, matrix):
        f.write(struct.pack("=I", MDL_MATRIX4))
        f.write(struct.pack("=4f4f4f4f", *matrix[0], *matrix[1], *matrix[2], *matrix[3]))
        f.write(struct.pack("=I", MDL_END))

    def write_node_block(self, f, node_array):
        f.write(struct.pack("=IIII", MDL_BLOCK, MDL_NODE, 0, 0))

        f.write(struct.pack("=IIII", MDL_LIST, MDL_NODE, len(node_array), 0))
        for node in node_array:
            f.write(struct.pack("=I", MDL_NODE))
            self.write_string(f, node.name)
            self.write_string(f, node.parent)
            self.write_matrix(f, node.transform)
            f.write(struct.pack("=I", MDL_END))
        f.write(struct.pack("=I", MDL_END))

        f.write(struct.pack("=I", MDL_END))

    def write_bone_block(self, f, bone_array):
        f.write(struct.pack("=IIII", MDL_BLOCK, MDL_BONE, 0, 0))

        f.write(struct.pack("=IIII", MDL_LIST, MDL_BONE, len(bone_array), 0))
        for bone in bone_array:
            f.write(struct.pack("=I", MDL_BONE))
            self.write_string(f, bone.name)
            self.write_matrix(f, bone.offset_matrix)
            f.write(struct.pack("=I", MDL_END))
        f.write(struct.pack("=I", MDL_END))

        f.write(struct.pack("=I", MDL_END))
    
    def write_material_block(self, f, ambient_texture, diffuse_texture, specular_texture):
        f.write(struct.pack("=IIII", MDL_BLOCK, MDL_MTL, 0, 0))

        material_array = []
        material_array.append(("Diffuse", diffuse_texture))

        if (ambient_texture != None):
            material_array.append(("Ambient", ambient_texture))

        if (specular_texture != None):
            material_array.append(("Specular", specular_texture))

        f.write(struct.pack("=IIII", MDL_LIST, MDL_MTL, len(material_array), 0))
        for mtl in material_array:
            f.write(struct.pack("=I", MDL_MTL))
            self.write_string(f, mtl[0])
            self.write_string(f, mtl[1])
            f.write(struct.pack("=I", MDL_END))
        f.write(struct.pack("=I", MDL_END))

        f.write(struct.pack("=I", MDL_END))
    
    def write_mesh_block(self, f, mesh_array):
        f.write(struct.pack("=IIII", MDL_BLOCK, MDL_MESH, 0, 0))

        f.write(struct.pack("=IIII", MDL_LIST, MDL_MESH, len(mesh_array), 0))
        for mesh in mesh_array:
            f.write(struct.pack("=I", MDL_MESH))
            self.write_string(f, mesh.name)

            f.write(struct.pack("=IIII", MDL_LIST, MDL_VERTEX, len(mesh.vertex_set), 0))
            for vertex in mesh.vertex_set:
                f.write(struct.pack("=H", MDL_VERTEX))
                f.write(struct.pack("=3f3f2fBB4B4f", *vertex.position, *vertex.normal, *vertex.uv, vertex.node_index, vertex.bone_count, *vertex.bone_indices, *vertex.bone_weights))
            f.write(struct.pack("=I", MDL_END))

            f.write(struct.pack("=IIII", MDL_LIST, MDL_POLYGON, len(mesh.polygon_array), 0))
            for polygon in mesh.polygon_array:
                f.write(struct.pack("=HBB", MDL_POLYGON, polygon.index_count, 0))
                f.write(struct.pack("={}H".format(polygon.index_count), *polygon.index_array))
                if (polygon.index_count == 3): # if there are 3 indices, pad to 4
                    f.write(struct.pack("=H", 0xFFFF))
            f.write(struct.pack("=I", MDL_END))

            f.write(struct.pack("=I", MDL_END))
        f.write(struct.pack("=I", MDL_END))

        f.write(struct.pack("=I", MDL_END))

    def write_file(self, data):
        f = open(self.filepath, "wb")
        f.write(struct.pack("=IIIIIIII", MDL_SIG, 1, 0, 0, 0, 0, 0, 0))
        self.write_node_block(f, data.node_index.array)
        self.write_bone_block(f, data.bone_index.array)
        self.write_material_block(f, data.ambient_texture, data.diffuse_texture, data.specular_texture)
        self.write_mesh_block(f, data.mesh_array)
        f.write(struct.pack("=I", MDL_EOF))
        f.close()

    def process(self):
        mdl_data = MDL_Model()

        for obj in bpy.data.objects:
            parent = None if obj.parent is None else obj.parent.name
            mdl_data.node_index.add(obj.name, MDL_Node(obj.name, parent, obj.matrix_local.transposed()))

        armature = None
        num_armatures = len(bpy.data.armatures)
        
        if num_armatures == 1:
            armature = bpy.data.armatures[0]
        elif num_armatures > 1:
            raise Exception("more than one armature present")

        if armature != None:
            armature_matrix = bpy.data.objects[armature.name].matrix_world
            for bone in armature.bones:
                matrix_local = bone.matrix_local
                parent = armature.name
                if bone.parent != None:
                    # bone.matrix_local is relative to the armature - multiply by the parent bone's inverse
                    matrix_local = bone.parent.matrix_local.inverted() @ matrix_local
                    parent = bone.parent.name
                mdl_data.node_index.add(bone.name, MDL_Node(bone.name, parent, matrix_local.transposed()))

                offset_matrix = armature_matrix @ bone.matrix_local
                offset_matrix.invert()
                offset_matrix.transpose()
                mdl_data.bone_index.add(bone.name, MDL_Bone(bone.name, offset_matrix))
        
        diffuse_texture = bpy.data.images.get("Diffuse")
        if diffuse_texture != None:
            mdl_data.diffuse_texture = os.path.basename(diffuse_texture.filepath)
        else:
            raise Exception("could not find the diffuse texture")

        ambient_texture = bpy.data.images.get("Ambient")
        if ambient_texture != None:
            mdl_data.ambient_texture = os.path.basename(ambient_texture.filepath)
        else:
            mdl_data.ambient_texture = None

        specular_texture = bpy.data.images.get("Specular")
        if specular_texture != None:
            mdl_data.specular_texture = os.path.basename(specular_texture.filepath)
        else:
            mdl_data.specular_texture = None

        for mesh in bpy.data.meshes:
            mesh.calc_normals_split()
            mesh_object = bpy.data.objects[mesh.name]
            mesh_armature = mesh_object.find_armature()
            
            bind_shape_matrix = Matrix.Identity(4)
            if mesh_armature != None:
                skin_offset = bpy.data.objects[mesh.name].matrix_world.to_translation()
                skeleton_offset = bpy.data.objects[armature.name].matrix_world.to_translation()
                offset = skin_offset - skeleton_offset
                
                bind_shape_matrix[0] = [1, 0, 0, 0]
                bind_shape_matrix[1] = [0, 0, 1, 0]
                bind_shape_matrix[2] = [0, -1, 0, 0]
                bind_shape_matrix[3] = [offset[0], offset[1], offset[2], 1]

            uv_layer = mesh.uv_layers.active.data

            vertex_group_map = [] # maps the group index to the bone index
            for group in bpy.data.objects[mesh.name].vertex_groups:
                vertex_group_map.append(mdl_data.bone_index.map.get(group.name, -1))

            mdl_mesh = MDL_Mesh(mesh.name)
            node_index = mdl_data.node_index.find(mesh.name)
            for p in mesh.polygons:
                if p.loop_total != 3 and p.loop_total != 4:
                    raise Exception("mesh has unsupported polygons (count={})".format(p.loop_total))

                polygon = MDL_Polygon()
                for i in range(p.loop_start, p.loop_start + p.loop_total):
                    n = mesh.loops[i].normal
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    num_groups = len(v.groups)
                    vertex = None

                    if num_groups > 4:
                        raise Exception("a vertex has invalid bones")
                    elif num_groups == 0:
                        vertex = MDL_Vertex(bind_shape_matrix @ v.co, n, uv_layer[i].uv, node_index)
                        vertex.bone_count = 0
                    else:
                        vertex = MDL_Vertex(bind_shape_matrix @ v.co, n, uv_layer[i].uv, node_index)
                        for g in v.groups:
                            if (vertex_group_map[g.group] != -1): # if this vertex group has a valid bone
                                vertex.bone_indices[vertex.bone_count] = vertex_group_map[g.group]
                                vertex.bone_weights[vertex.bone_count] = g.weight
                                vertex.bone_count += 1
                    vertex.finalize()

                    index = mdl_mesh.vertex_map.get(vertex, -1)
                    if index == -1:
                        index = len(mdl_mesh.vertex_set)
                        mdl_mesh.vertex_map[vertex] = index
                        mdl_mesh.vertex_set.append(vertex)
                    polygon.index_count += 1
                    polygon.index_array.append(index)
                mdl_mesh.polygon_array.append(polygon)
            
            mdl_data.mesh_array.append(mdl_mesh)
            mesh.free_normals_split()

        return mdl_data

    def execute(self, context):
        try:
            mdl = self.process()
            self.write_file(mdl)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

def menu_func_export(self, context):
    self.layout.operator(MDL_Exporter.bl_idname, text="MDL (.mdl)")

def register():
    bpy.utils.register_class(MDL_Exporter)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(MDL_Exporter)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
