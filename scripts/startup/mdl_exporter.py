
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
from mathutils import Matrix
import struct

bl_info = {
    "name": "MDL format",
    "author": "Jas",
    "version": (0, 0, 1),
    "blender": (2, 81, 6),
    "location": "File > Import-Export",
    "description": "MDL scene exporter",
    "warning": "",
    "support": "COMMUNITY",
    "category": "Import-Export"
}

MDL_SIGNATURE   = 0x004C444D # 'MDL'
MDL_END_OF_FILE = 0x00464F45 # 'EOF'

class Flag:
    CLASS = 0x20
    ARRAY = 0x40
    BLOCK = 0x60
    TERMINATOR = 0x80

class ID:
    STRING   = 0x1
    NODE     = 0x2
    BONE     = 0x3
    VERTEX   = 0x4
    MATERIAL = 0x5
    MESH     = 0x6
    INDEX    = 0x7
    MATRIX   = 0x8

class MDL:
    NODE_BLOCK     = Flag.BLOCK | ID.NODE
    MATERIAL_BLOCK = Flag.BLOCK | ID.MATERIAL
    MESH_BLOCK     = Flag.BLOCK | ID.MESH
    NODE_ARRAY     = Flag.ARRAY | ID.NODE
    BONE_ARRAY     = Flag.ARRAY | ID.BONE
    VERTEX_ARRAY   = Flag.ARRAY | ID.VERTEX
    INDEX_ARRAY    = Flag.ARRAY | ID.INDEX
    MESH_ARRAY     = Flag.ARRAY | ID.MESH
    STRING         = Flag.CLASS | ID.STRING
    NODE           = Flag.CLASS | ID.NODE
    BONE           = Flag.CLASS | ID.BONE
    VERTEX         = Flag.CLASS | ID.VERTEX
    MESH           = Flag.CLASS | ID.MESH
    MATRIX         = Flag.CLASS | ID.MATRIX

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
        return (self.position == other.position) and (self.normal == other.normal) and (self.uv == other.uv) and (self.node_index == other.node_index) and \
            (self.bone_indices == other.bone_indices) and (self.bone_weights == other.bone_weights) and (self.bone_count == other.bone_count)

    def __hash__(self):
        return self.hash_value

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
        self.index_array = []

class MDL_Model:
    def __init__(self):
        self.ambient_texture = None
        self.diffuse_texture = None
        self.specular_texture = None
        self.vertex_set = []
        self.vertex_map = {}
        self.mesh_array = []
        self.bone_index = Index()
        self.node_index = Index()

class MDL_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL"

    filename_ext = ".mdl"

    def write_string(self, f, str):
        f.write(struct.pack("B", MDL.STRING))
        if str == None:
            f.write(struct.pack("BB", 0, 0))
        else:
            f.write(struct.pack("B", len(str) + 1))
            f.write(struct.pack("{}s".format(len(str) + 1), str.encode("utf-8")))
    
    def write_matrix(self, f, matrix):
        f.write(struct.pack("B", MDL.MATRIX))
        f.write(struct.pack("4f4f4f4f", *matrix[0], *matrix[1], *matrix[2], *matrix[3]))

    def write_node_block(self, f, node_array, bone_array):
        f.write(struct.pack("B", MDL.NODE_BLOCK))
        
        f.write(struct.pack("B", MDL.NODE_ARRAY))
        f.write(struct.pack("H", len(node_array)))
        for node in node_array:
            f.write(struct.pack("B", MDL.NODE))
            self.write_string(f, node.name)
            self.write_string(f, node.parent)
            self.write_matrix(f, node.transform)
        f.write(struct.pack("B", Flag.TERMINATOR | MDL.NODE_ARRAY))

        f.write(struct.pack("B", MDL.BONE_ARRAY))
        f.write(struct.pack("H", len(bone_array)))
        for bone in bone_array:
            f.write(struct.pack("B", MDL.BONE))
            self.write_string(f, bone.name)
            self.write_matrix(f, bone.offset_matrix)
        f.write(struct.pack("B", Flag.TERMINATOR | MDL.BONE_ARRAY))

        f.write(struct.pack("B", Flag.TERMINATOR | MDL.NODE_BLOCK))
    
    def write_material_block(self, f, ambient_texture, diffuse_texture, specular_texture):
        f.write(struct.pack("B", MDL.MATERIAL_BLOCK))
        self.write_string(f, ambient_texture)
        self.write_string(f, diffuse_texture)
        self.write_string(f, specular_texture)
        f.write(struct.pack("B", Flag.TERMINATOR | MDL.MATERIAL_BLOCK))
    
    def write_mesh_block(self, f, vertex_array, mesh_array):
        f.write(struct.pack("B", MDL.MESH_BLOCK))
        
        f.write(struct.pack("B", MDL.VERTEX_ARRAY))
        f.write(struct.pack("H", len(vertex_array)))
        for vertex in vertex_array:
            f.write(struct.pack("B", MDL.VERTEX))
            f.write(struct.pack("3f3f2f", *vertex.position, *vertex.normal, *vertex.uv))
            f.write(struct.pack("I4B4fI", vertex.node_index, *vertex.bone_indices, *vertex.bone_weights, vertex.bone_count))
        f.write(struct.pack("B", Flag.TERMINATOR | MDL.VERTEX_ARRAY))

        f.write(struct.pack("B", MDL.MESH_ARRAY))
        f.write(struct.pack("H", len(mesh_array)))
        for mesh in mesh_array:
            f.write(struct.pack("B", MDL.MESH))
            self.write_string(f, mesh.name)
            f.write(struct.pack("B", MDL.INDEX_ARRAY))
            f.write(struct.pack("H", len(mesh.index_array)))
            f.write(struct.pack("{}H".format(len(mesh.index_array)), *mesh.index_array))
            f.write(struct.pack("B", Flag.TERMINATOR | MDL.INDEX_ARRAY))
        f.write(struct.pack("B", Flag.TERMINATOR | MDL.MESH_ARRAY))

        f.write(struct.pack("B", Flag.TERMINATOR | MDL.MESH_BLOCK))

    def write_file(self, data):
        f = open(self.filepath, "wb")
        f.write(struct.pack("I", MDL_SIGNATURE))
        self.write_node_block(f, data.node_index.array, data.bone_index.array)
        self.write_material_block(f, data.ambient_texture, data.diffuse_texture, data.specular_texture)
        self.write_mesh_block(f, data.vertex_set, data.mesh_array)
        f.write(struct.pack("I", MDL_END_OF_FILE))
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
        
        ambient_texture = bpy.data.images.get("Ambient")
        if ambient_texture != None:
            mdl_data.ambient_texture = ambient_texture.filepath
        else:
            raise Exception("could not find the ambient texture")

        diffuse_texture = bpy.data.images.get("Diffuse")
        if diffuse_texture != None:
            mdl_data.diffuse_texture = diffuse_texture.filepath
        else:
            raise Exception("could not find the diffuse texture")

        specular_texture = bpy.data.images.get("Specular")
        if specular_texture != None:
            mdl_data.specular_texture = specular_texture.filepath
        else:
            raise Exception("could not find the specular texture")

        for mesh in bpy.data.meshes:
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
                vertex_group_map.append(mdl_data.bone_index.find(group.name))

            mdl_mesh = MDL_Mesh(mesh.name)
            node_index = mdl_data.node_index.find(mesh.name)
            for face in mesh.polygons:
                if face.loop_total != 3:
                    raise Exception("mesh has non-triangular polygons")
                for i in range(face.loop_start, face.loop_start + face.loop_total):
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    num_groups = len(v.groups)
                    vertex = None

                    if num_groups > 4:
                        raise Exception("a vertex has invalid bones")
                    elif num_groups == 0:
                        vertex = MDL_Vertex(bind_shape_matrix @ v.co, v.normal, uv_layer[i].uv, node_index)
                        vertex.bone_count = 0
                    else:
                        vertex = MDL_Vertex(bind_shape_matrix @ v.co, v.normal, uv_layer[i].uv, node_index)
                        for g in v.groups:
                            vertex.bone_indices[vertex.bone_count] = vertex_group_map[g.group]
                            vertex.bone_weights[vertex.bone_count] = g.weight
                            vertex.bone_count += 1
                    vertex.finalize()

                    index = mdl_data.vertex_map.get(vertex, -1)
                    if index == -1:
                        index = len(mdl_data.vertex_set)
                        mdl_data.vertex_map[vertex] = index
                        mdl_data.vertex_set.append(vertex)
                    mdl_mesh.index_array.append(index)
            mdl_data.mesh_array.append(mdl_mesh)

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
