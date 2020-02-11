
import bpy
from bpy.props import (BoolProperty, FloatProperty, StringProperty, EnumProperty)
from bpy_extras.io_utils import (ImportHelper, ExportHelper, orientation_helper, path_reference_mode, axis_conversion)

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

class MDL_Exporter(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export MDL"

    filename_ext = ".mdl"

    def execute(self, context):
        f = open(self.filepath, "w")
        
        for mesh in bpy.data.meshes:
            for face in mesh.polygons:
                if len(face.vertices) > 3:
                    self.report({"ERROR"}, "Mesh has non-triangular polygons")
                    return {"CANCELLED"}
                for i in range(0, 3):
                    v = face.vertices[i]
                    
                    f.write("v (({}, {}, {}), ({}, {}, {}), ({}, {}))".format())

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
