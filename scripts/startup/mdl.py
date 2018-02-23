
import bpy

class MDL_Exporter(bpy.types.Operator):
    bl_idname = "export.mdl"
    bl_label = "Export MDL"

    filepath = bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        out = open(self.filepath, 'w')

        for obj in bpy.data.objects:
            if obj.name in ['Lamp', 'Camera']:
                continue
            mesh = bpy.data.meshes[obj.name]
            out.write(obj.name + ":\n")
            out.write("Vertices:\n")
            for vertex in mesh.vertices:
                out.write(str(vertex.co[0]) + "," + str(vertex.co[1]) + "," + str(vertex.co[2]) + "\n")
            out.write("Polygons:\n")
            for face in mesh.polygons:
                out.write(str(face.vertices[0]) + "," + str(face.vertices[1]) + "," + str(face.vertices[2]) + "\n")

        out.close()
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def export_func(self, context):
    self.layout.operator(MDL_Exporter.bl_idname, text="MDL Exporter")

bpy.utils.register_class(MDL_Exporter)
bpy.types.INFO_MT_file_export.append(export_func)

