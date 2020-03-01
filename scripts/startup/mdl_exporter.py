
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)
from mathutils import Matrix

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

class MDL_Vertex:
    def __init__(self, p, n, uv):
        self.position = tuple(p)
        self.normal = tuple(n)
        self.uv = tuple(uv)
        self.bone_indices = [0, 0, 0, 0]
        self.bone_weights = [0, 0, 0, 0]
        self.bone_count = 0
        self.hash_value = 0
    
    def finalize(self):
        self.bone_indices = tuple(self.bone_indices)
        self.bone_weights = tuple(self.bone_weights)
        self.hash_value = hash((self.position, self.normal, self.uv, self.bone_indices, self.bone_weights, self.bone_count))

    def __eq__(self, other):
        return (self.position == other.position) and (self.normal == other.normal) and (self.uv == other.uv) and \
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
    def __init__(self):
        self.index_array = []

class MDL_Model:
    def __init__(self):
        self.vertex_set = []
        self.vertex_map = {}
        self.mesh_array = []
        self.bone_index = Index()
        self.node_index = Index()

def write_matrix(f, text, matrix):
    f.write("{}\n".format(text))
    for i in range(4):
        f.write("[{0:.6f}, {1:.6f}, {2:.6f}, {3:.6f}]\n".format(matrix[i][0], matrix[i][1], matrix[i][2], matrix[i][3]))
    f.write("\n")

class MDL_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL"

    filename_ext = ".mdl"

    def process(self):
        f = open(self.filepath, "w")

        data = MDL_Model()

        for obj in bpy.data.objects:
            data.node_index.add(obj.name, MDL_Node(obj.name, obj.parent, obj.matrix_local.transposed()))

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
                data.node_index.add(bone.name, MDL_Node(bone.name, parent, matrix_local.transposed()))

                offset_matrix = armature_matrix @ bone.matrix_local
                offset_matrix.invert()
                offset_matrix.transpose()
                data.bone_index.add(bone.name, MDL_Bone(bone.name, offset_matrix))
        
        for node in data.node_index.array:
            write_matrix(f, "node {}:".format(node.name), node.transform)
        for bone in data.bone_index.array:
            write_matrix(f, "bone {}:".format(bone.name), bone.offset_matrix)
        
        texture = bpy.data.images.get("Texture")
        if texture != None:
            f.write("texture path: {}\n".format(texture.filepath))
        else:
            raise Exception("texture not found")

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
            write_matrix(f, "bind shape matrix:", bind_shape_matrix)

            uv_layer = mesh.uv_layers.active.data

            vertex_group_map = [] # maps the group index to the bone index
            for group in bpy.data.objects[mesh.name].vertex_groups:
                vertex_group_map.append(data.bone_index.find(group.name))

            mesh = MDL_Mesh()
            for face in mesh.polygons:
                if face.loop_total != 3:
                    raise Exception("mesh has non-triangular polygons")
                for i in range(face.loop_start, face.loop_start + face.loop_total):
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    if len(v.groups) > 4:
                        raise Exception("a vertex has more than 4 bones")
                    vertex = MDL_Vertex(bind_shape_matrix @ v.co, v.normal, uv_layer[i].uv)
                    for g in v.groups:
                        vertex.bone_indices[vertex.bone_count] = vertex_group_map[g.group]
                        vertex.bone_weights[vertex.bone_count] = g.weight
                        vertex.bone_count += 1
                    vertex.finalize()

                    index = data.vertex_map.get(vertex, -1)
                    if index == -1:
                        index = len(data.vertex_set)
                        data.vertex_map[vertex] = index
                        data.vertex_set.append(vertex)
                    mesh.index_array.append(index)
            
            data.mesh_array.append(mesh)
            
        for vertex in data.vertex_set:
            f.write("({0:.6f}, {1:.6f}, {2:.6f}), ({3:.6f}, {4:.6f}, {5:.6f}), ({6:.6f}, {7:.6f}), ({8:.6f}, {9:.6f}, {10:.6f}, {11:.6f}), ({12:.6f}, {13:.6f}, {14:.6f}, {15:.6f}), {16:.6f}\n".format(
                vertex.position[0], vertex.position[1], vertex.position[2],
                vertex.normal[0], vertex.normal[1], vertex.normal[2],
                vertex.uv[0], vertex.uv[1],
                vertex.bone_indices[0], vertex.bone_indices[1], vertex.bone_indices[2], vertex.bone_indices[3],
                vertex.bone_weights[0], vertex.bone_weights[1], vertex.bone_weights[2], vertex.bone_weights[3],
                vertex.bone_count
            ))
        f.write("SAVED {} WRITES\n".format(len(data.index_array) - len(data.vertex_set)))
        f.close()

    def execute(self, context):
        try:
            self.process()
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

def menu_func_export(self, context):
    self.layout.operator(MDL_Exporter.bl_idname, text="MDL Exporter (.mdl)")    

def register():
    bpy.utils.register_class(MDL_Exporter)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(MDL_Exporter)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
