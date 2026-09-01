bl_info = {
    "name": "Sticky Grease Pencil",
    "author": "Antigravity",
    "version": (1, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Sticky GP",
    "description": "Binds newly drawn Grease Pencil strokes to a deforming target mesh.",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy
import bmesh
import mathutils

def get_evaluated_mesh(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    return eval_obj.to_mesh()

def create_sticky_gn_modifier(gp_obj, target_obj):
    mod_name = "Sticky_GP"
    if mod_name in gp_obj.modifiers:
        mod = gp_obj.modifiers[mod_name]
    else:
        mod = gp_obj.modifiers.new(name=mod_name, type='NODES')
    
    group_name = f"Sticky_GP_Nodes_{gp_obj.name}"
    if group_name in bpy.data.node_groups:
        node_group = bpy.data.node_groups[group_name]
    else:
        node_group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
        
        node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        
        nodes = node_group.nodes
        links = node_group.links
        
        group_in = nodes.new('NodeGroupInput')
        group_out = nodes.new('NodeGroupOutput')
        
        obj_info = nodes.new('GeometryNodeObjectInfo')
        obj_info.transform_space = 'RELATIVE'
        
        sample_pos = nodes.new('GeometryNodeSampleUVSurface')
        sample_pos.data_type = 'FLOAT_VECTOR'
        input_pos = nodes.new('GeometryNodeInputPosition')
        
        sample_normal = nodes.new('GeometryNodeSampleUVSurface')
        sample_normal.data_type = 'FLOAT_VECTOR'
        input_normal = nodes.new('GeometryNodeInputNormal')
        
        uv_map_attr = nodes.new('GeometryNodeInputNamedAttribute')
        uv_map_attr.data_type = 'FLOAT_VECTOR'
        uv_map_attr.inputs['Name'].default_value = 'UVMap'
        
        bind_uv = nodes.new('GeometryNodeInputNamedAttribute')
        bind_uv.data_type = 'FLOAT_VECTOR'
        bind_uv.inputs['Name'].default_value = 'bind_uv'
        
        bind_dist = nodes.new('GeometryNodeInputNamedAttribute')
        bind_dist.data_type = 'FLOAT'
        bind_dist.inputs['Name'].default_value = 'bind_dist'
        
        is_bound = nodes.new('GeometryNodeInputNamedAttribute')
        is_bound.data_type = 'BOOLEAN'
        is_bound.inputs['Name'].default_value = 'is_bound'
        
        math_scale = nodes.new('ShaderNodeVectorMath')
        math_scale.operation = 'SCALE'
        
        math_add = nodes.new('ShaderNodeVectorMath')
        math_add.operation = 'ADD'
        
        set_pos = nodes.new('GeometryNodeSetPosition')
        
        links.new(obj_info.outputs['Geometry'], sample_pos.inputs['Mesh'])
        links.new(obj_info.outputs['Geometry'], sample_normal.inputs['Mesh'])
        
        links.new(input_pos.outputs['Position'], sample_pos.inputs['Value'])
        links.new(input_normal.outputs['Normal'], sample_normal.inputs['Value'])
        
        links.new(uv_map_attr.outputs['Attribute'], sample_pos.inputs['UV Map'])
        links.new(uv_map_attr.outputs['Attribute'], sample_normal.inputs['UV Map'])
        
        links.new(bind_uv.outputs['Attribute'], sample_pos.inputs['Sample UV'])
        links.new(bind_uv.outputs['Attribute'], sample_normal.inputs['Sample UV'])
        
        links.new(sample_normal.outputs['Value'], math_scale.inputs[0])
        links.new(bind_dist.outputs['Attribute'], math_scale.inputs['Scale'])
        
        links.new(sample_pos.outputs['Value'], math_add.inputs[0])
        links.new(math_scale.outputs['Vector'], math_add.inputs[1])
        
        links.new(group_in.outputs['Geometry'], set_pos.inputs['Geometry'])
        links.new(is_bound.outputs['Attribute'], set_pos.inputs['Selection'])
        links.new(math_add.outputs['Vector'], set_pos.inputs['Position'])
        
        links.new(set_pos.outputs['Geometry'], group_out.inputs['Geometry'])
        
    mod.node_group = node_group
    
    for node in node_group.nodes:
        if node.type == 'OBJECT_INFO':
            node.inputs['Object'].default_value = target_obj

def bind_unbound_strokes(gp_obj, target_obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    
    mesh = get_evaluated_mesh(target_obj, depsgraph)
    
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
        
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.verify()
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.faces.ensure_lookup_table()
    bvh = mathutils.bvhtree.BVHTree.FromBMesh(bm)
    
    gp_data = gp_obj.data
    
    gp_to_world = gp_obj.matrix_world
    world_to_target = target_obj.matrix_world.inverted()
    gp_to_target = world_to_target @ gp_to_world
    
    bound_count = 0
    for layer in gp_data.layers:
        for frame in layer.frames:
            drawing = frame.drawing
            
            if 'bind_uv' not in drawing.attributes:
                drawing.attributes.new(name='bind_uv', type='FLOAT2', domain='POINT')
            if 'bind_dist' not in drawing.attributes:
                drawing.attributes.new(name='bind_dist', type='FLOAT', domain='POINT')
            if 'is_bound' not in drawing.attributes:
                drawing.attributes.new(name='is_bound', type='BOOLEAN', domain='POINT')
                
            attr_uv = drawing.attributes['bind_uv'].data
            attr_dist = drawing.attributes['bind_dist'].data
            attr_bound = drawing.attributes['is_bound'].data
            
            if 'position' in drawing.attributes:
                points = drawing.attributes['position'].data
                for i in range(len(points)):
                    if not attr_bound[i].value:
                        pos_gp = points[i].vector
                        pos_target = gp_to_target @ pos_gp
                        
                        location, normal, index, distance = bvh.find_nearest(pos_target)
                        if location is not None:
                            face = bm.faces[index]
                            v1, v2, v3 = (v.co for v in face.verts[:3])
                            bary = mathutils.geometry.barycentric_transform(location, v1, v2, v3, mathutils.Vector((1,0,0)), mathutils.Vector((0,1,0)), mathutils.Vector((0,0,1)))
                            
                            uvs = []
                            for loop in face.loops:
                                uvs.append(loop[uv_layer].uv)
                            
                            if len(uvs) >= 3:
                                final_uv = uvs[0] * bary.x + uvs[1] * bary.y + uvs[2] * bary.z
                                attr_uv[i].vector = final_uv
                                attr_dist[i].value = distance
                                attr_bound[i].value = True
                                bound_count += 1
                                
    bm.free()
    target_obj.evaluated_get(depsgraph).to_mesh_clear()
    
    return bound_count

class STICKYGP_OT_bind(bpy.types.Operator):
    """Bind newly drawn GP strokes to the target mesh"""
    bl_idname = "object.bind_sticky_gp"
    bl_label = "Bind New Strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'GREASEPENCIL' and context.active_object.sticky_gp_target is not None

    def execute(self, context):
        target_obj = context.active_object.sticky_gp_target
        gp_obj = context.active_object
        
        create_sticky_gn_modifier(gp_obj, target_obj)
        count = bind_unbound_strokes(gp_obj, target_obj)
        
        self.report({'INFO'}, f"Bound {count} new stroke points to {target_obj.name}")
        return {'FINISHED'}

class STICKYGP_PT_panel(bpy.types.Panel):
    """Creates a Panel in the scene context of the properties editor"""
    bl_label = "Sticky GP"
    bl_idname = "STICKYGP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Sticky GP"

    def draw(self, context):
        layout = self.layout
        if context.active_object and context.active_object.type == 'GREASEPENCIL':
            layout.prop(context.active_object, "sticky_gp_target")
        else:
            layout.label(text="Please select a GPencil object.", icon='ERROR')
            return
        
        row = layout.row()
        row.operator("object.bind_sticky_gp")
        


def register():
    bpy.utils.register_class(STICKYGP_OT_bind)
    bpy.utils.register_class(STICKYGP_PT_panel)
    bpy.types.Object.sticky_gp_target = bpy.props.PointerProperty(
        name="Target Mesh",
        type=bpy.types.Object,
        description="The mesh to stick the Grease Pencil strokes to"
    )

def unregister():
    bpy.utils.unregister_class(STICKYGP_OT_bind)
    bpy.utils.unregister_class(STICKYGP_PT_panel)
    del bpy.types.Object.sticky_gp_target

if __name__ == "__main__":
    register()
