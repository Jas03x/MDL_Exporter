
import bpy

class MDL_Exporter(bpy.types.Operator):
    bl_idname = "export.mdl"
    bl_label = "Export MDL"

    filepath = bpy.props.StringProperty(subtype="FILE_PATH")
    
    def execute(self, context):
        out = open(self.filepath, 'w')
        for object in bpy.data.objects:
            out.write("" + str(object.name))
        out.close()
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def export_func(self, context):
    self.layout.operator(MDL_Exporter.bl_idname, text="MDL Exporter")

bpy.utils.register_class(MDL_Exporter)
bpy.types.INFO_MT_file_export.append(export_func)

