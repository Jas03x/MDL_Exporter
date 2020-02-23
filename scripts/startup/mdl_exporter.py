
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
    "support": 'COMMUNITY',
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

class MDL_Bone:
    def __init__(self, name):
        self.name = name

class MDL_Node:
    def __init__(self, name, parent, location, rotation, scale):
        self.name = name
        self.parent = parent
        self.location = location
        self.rotation = rotation
        self.scale = scale

class MDL_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL"

    filename_ext = ".mdl"

    def execute(self, context):
        f = open(self.filepath, "w")

        bone_map  = {}
        bone_list = []
        node_map  = {}
        node_list = []

        for obj in bpy.data.objects:
            if obj.rotation_mode != 'XYZ':
                self.report({"ERROR"}, "Invalid rotation mode")
                return {"CANCELLED"}
            node_map[obj.name] = len(node_list)
            node_list.append(MDL_Node(obj.name, -1 if obj.parent == None else node_map[obj.parent.name], obj.location, obj.rotation_euler, obj.scale))

        for armature in bpy.data.armatures:
            for bone in armature.bones:
                bone_map[bone.name] = len(bone_list)
                bone_list.append(MDL_Bone(bone.name))

        obj_map = {}
        for obj in bpy.data.objects:
            f.write("node {}:\n".format(obj.name))
            obj_map[obj.name] = obj
            matrix = obj.matrix_world.transposed()
            for i in range(4):
                f.write("[{0:.6f}, {1:.6f}, {2:.6f}, {3:.6f}]\n".format(matrix[i][0], matrix[i][1], matrix[i][2], matrix[i][3]))
            f.write("\n")
        
        for armature in bpy.data.armatures:
            for bone in armature.bones:
                f.write("node {}:\n".format(bone.name))

                matrix = None
                if bone.parent is None:
                    matrix = bone.matrix_local
                else:
                    matrix = bone.parent.matrix_local.inverted()
                    matrix = matrix @ bone.matrix_local
                matrix = matrix.transposed()

                for i in range(4):
                    f.write("[{0:.6f}, {1:.6f}, {2:.6f}, {3:.6f}]\n".format(matrix[i][0], matrix[i][1], matrix[i][2], matrix[i][3]))
                f.write("\n")

        for armature in bpy.data.armatures:
            armature_matrix = obj_map[armature.name].matrix_world

            children = obj_map[armature.name].children
            if len(children) != 1:
                self.report({"ERROR"}, "Armature has invalid number of children")
                return {"CANCELLED"}

            f.write("{} - {}\n".format(children[0].matrix_world.to_translation(), obj_map[armature.name].matrix_world.to_translation()))
            offset = children[0].matrix_world.to_translation() - obj_map[armature.name].matrix_world.to_translation()
            bind_shape_matrix = Matrix()
            bind_shape_matrix[0] = [1, 0, 0, 0]
            bind_shape_matrix[1] = [0, 0, 1, 0]
            bind_shape_matrix[2] = [0, -1, 0, 0]
            bind_shape_matrix[3] = [offset[0], offset[1], offset[2], 1]

            f.write("bind shape matrix:\n")
            for i in range(4):
                f.write("[{0:.6f}, {1:.6f}, {2:.6f}, {3:.6f}]\n".format(bind_shape_matrix[i][0], bind_shape_matrix[i][1], bind_shape_matrix[i][2], bind_shape_matrix[i][3]))
            f.write("\n")

            for bone in armature.bones:
                f.write("bone {}:\n".format(bone.name))
                matrix = armature_matrix @ bone.matrix_local
                matrix.invert()
                matrix.transpose()
                for i in range(4):
                    f.write("[{0:.6f}, {1:.6f}, {2:.6f}, {3:.6f}]\n".format(matrix[i][0], matrix[i][1], matrix[i][2], matrix[i][3]))
                f.write("\n")
        
        for mesh in bpy.data.meshes:
            uv_layer = mesh.uv_layers.active.data

            vertex_group_map = [] # maps the group index to the bone index
            for group in bpy.data.objects[mesh.name].vertex_groups:
                vertex_group_map.append(bone_map[group.name])

            vertex_list = []
            vertex_map  = {}
            indices = []
            for face in mesh.polygons:
                if face.loop_total != 3:
                    self.report({"ERROR"}, "Mesh has non-triangular polygons")
                    return {"CANCELLED"}
                for i in range(face.loop_start, face.loop_start + face.loop_total):
                    v = mesh.vertices[mesh.loops[i].vertex_index]
                    if len(v.groups) > 4:
                        self.report({"ERROR"}, "A vertex has more than 4 bones")
                        return {"CANCELLED"}
                    vertex = MDL_Vertex(v.co, v.normal, uv_layer[i].uv)
                    for g in v.groups:
                        vertex.bone_indices[vertex.bone_count] = vertex_group_map[g.group]
                        vertex.bone_weights[vertex.bone_count] = g.weight
                        vertex.bone_count += 1
                    vertex.finalize()

                    index = vertex_map.get(vertex, -1)
                    if index == -1:
                        vertex_map[vertex] = len(vertex_list)
                        vertex_list.append(vertex)
                    indices.append(index)
            for vertex in vertex_list:
                f.write("({0:.6f}, {1:.6f}, {2:.6f}), ({3:.6f}, {4:.6f}, {5:.6f}), ({6:.6f}, {7:.6f}), ({8:.6f}, {9:.6f}, {10:.6f}, {11:.6f}), ({12:.6f}, {13:.6f}, {14:.6f}, {15:.6f}), {16:.6f}\n".format(
                    vertex.position[0], vertex.position[1], vertex.position[2],
                    vertex.normal[0], vertex.normal[1], vertex.normal[2],
                    vertex.uv[0], vertex.uv[1],
                    vertex.bone_indices[0], vertex.bone_indices[1], vertex.bone_indices[2], vertex.bone_indices[3],
                    vertex.bone_weights[0], vertex.bone_weights[1], vertex.bone_weights[2], vertex.bone_weights[3],
                    vertex.bone_count
                ))
            f.write("SAVED {} WRITES\n".format(len(indices) - len(vertex_list)))

        f.close()
        
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
