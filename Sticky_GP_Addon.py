bl_info = {
    "name": "Sticky Grease Pencil",
    "author": "Antigravity",
    "version": (1, 2),
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

def generate_sticky_uvs(obj):
    import math
    mesh = obj.data
    uv_name = "Sticky_GP_UVMap"
    
    if uv_name in mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[uv_name])
    uv_layer = mesh.uv_layers.new(name=uv_name)
    
    poly_count = len(mesh.polygons)
    if poly_count == 0:
        return
        
    grid_size = math.ceil(math.sqrt(poly_count))
    
    for poly in mesh.polygons:
        idx = poly.index
        grid_x = idx % grid_size
        grid_y = idx // grid_size
        
        u_base = grid_x / grid_size
        v_base = grid_y / grid_size
        step = 1.0 / grid_size
        
        verts_3d = [mesh.vertices[v].co for v in poly.vertices]
        center = poly.center
        normal = poly.normal
        
        if normal.length < 0.0001:
            tangent = mathutils.Vector((1,0,0))
            bitangent = mathutils.Vector((0,1,0))
        else:
            v_up = mathutils.Vector((0,0,1))
            if abs(normal.dot(v_up)) > 0.99:
                v_up = mathutils.Vector((1,0,0))
            tangent = v_up.cross(normal).normalized()
            bitangent = normal.cross(tangent).normalized()
            
        coords_2d = []
        max_dist = 0.0001
        for v3d in verts_3d:
            rel = v3d - center
            u_local = rel.dot(tangent)
            v_local = rel.dot(bitangent)
            coords_2d.append((u_local, v_local))
            max_dist = max(max_dist, abs(u_local), abs(v_local))
            
        scale = (step / 2) * 0.9 / max_dist
        
        for i, loop_idx in enumerate(poly.loop_indices):
            u = u_base + (step / 2) + coords_2d[i][0] * scale
            v = v_base + (step / 2) + coords_2d[i][1] * scale
            uv_layer.data[loop_idx].uv = (u, v)

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
        uv_map_attr.inputs['Name'].default_value = 'Sticky_GP_UVMap'
        
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
        
        # FALLBACK LOGIC: If Sample UV Surface fails due to boundary float precision, fallback to Sample Index
        bind_face_idx = nodes.new('GeometryNodeInputNamedAttribute')
        bind_face_idx.data_type = 'INT'
        bind_face_idx.inputs['Name'].default_value = 'bind_face_idx'
        
        sample_idx_pos = nodes.new('GeometryNodeSampleIndex')
        sample_idx_pos.data_type = 'FLOAT_VECTOR'
        sample_idx_pos.domain = 'FACE'
        
        sample_idx_normal = nodes.new('GeometryNodeSampleIndex')
        sample_idx_normal.data_type = 'FLOAT_VECTOR'
        sample_idx_normal.domain = 'FACE'
        
        len_pos = nodes.new('ShaderNodeVectorMath')
        len_pos.operation = 'LENGTH'
        
        cmp_pos = nodes.new('FunctionNodeCompare')
        cmp_pos.data_type = 'FLOAT'
        cmp_pos.operation = 'LESS_THAN'
        cmp_pos.inputs[1].default_value = 0.001
        
        switch_pos = nodes.new('GeometryNodeSwitch')
        switch_pos.input_type = 'VECTOR'
        
        switch_normal = nodes.new('GeometryNodeSwitch')
        switch_normal.input_type = 'VECTOR'
        
        links.new(obj_info.outputs['Geometry'], sample_pos.inputs['Mesh'])
        links.new(obj_info.outputs['Geometry'], sample_normal.inputs['Mesh'])
        
        links.new(obj_info.outputs['Geometry'], sample_idx_pos.inputs['Geometry'])
        links.new(input_pos.outputs['Position'], sample_idx_pos.inputs['Value'])
        links.new(bind_face_idx.outputs['Attribute'], sample_idx_pos.inputs['Index'])
        
        links.new(obj_info.outputs['Geometry'], sample_idx_normal.inputs['Geometry'])
        links.new(input_normal.outputs['Normal'], sample_idx_normal.inputs['Value'])
        links.new(bind_face_idx.outputs['Attribute'], sample_idx_normal.inputs['Index'])
        
        links.new(input_pos.outputs['Position'], sample_pos.inputs['Value'])
        links.new(input_normal.outputs['Normal'], sample_normal.inputs['Value'])
        
        links.new(uv_map_attr.outputs['Attribute'], sample_pos.inputs['UV Map'])
        links.new(uv_map_attr.outputs['Attribute'], sample_normal.inputs['UV Map'])
        
        links.new(bind_uv.outputs['Attribute'], sample_pos.inputs['Sample UV'])
        links.new(bind_uv.outputs['Attribute'], sample_normal.inputs['Sample UV'])
        
        links.new(sample_pos.outputs['Value'], len_pos.inputs[0])
        links.new(len_pos.outputs['Value'], cmp_pos.inputs[0])
        
        links.new(cmp_pos.outputs['Result'], switch_pos.inputs['Switch'])
        links.new(sample_pos.outputs['Value'], switch_pos.inputs['False'])
        links.new(sample_idx_pos.outputs['Value'], switch_pos.inputs['True'])
        
        links.new(cmp_pos.outputs['Result'], switch_normal.inputs['Switch'])
        links.new(sample_normal.outputs['Value'], switch_normal.inputs['False'])
        links.new(sample_idx_normal.outputs['Value'], switch_normal.inputs['True'])
        
        links.new(switch_normal.outputs['Output'], math_scale.inputs[0])
        links.new(bind_dist.outputs['Attribute'], math_scale.inputs['Scale'])
        
        links.new(switch_pos.outputs['Output'], math_add.inputs[0])
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
    if "Sticky_GP_UVMap" not in target_obj.data.uv_layers:
        generate_sticky_uvs(target_obj)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    
    mesh = get_evaluated_mesh(target_obj, depsgraph)
    
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.get("Sticky_GP_UVMap")
    if not uv_layer:
        uv_layer = bm.loops.layers.uv.verify()
        
    idx_layer = bm.faces.layers.int.new("orig_idx")
    for f in bm.faces:
        f[idx_layer] = f.index
        
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
            if 'bind_face_idx' not in drawing.attributes:
                drawing.attributes.new(name='bind_face_idx', type='INT', domain='POINT')
                
            attr_uv = drawing.attributes['bind_uv'].data
            attr_dist = drawing.attributes['bind_dist'].data
            attr_bound = drawing.attributes['is_bound'].data
            attr_idx = drawing.attributes['bind_face_idx'].data
            
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
                                attr_idx[i].value = face[idx_layer]
                                bound_count += 1
                                
    bm.free()
    target_obj.evaluated_get(depsgraph).to_mesh_clear()
    
    return bound_count

def unbind_strokes_on_frame(gp_obj, frame_num):
    gp_data = gp_obj.data
    unbound_count = 0
    
    for layer in gp_data.layers:
        for frame in layer.frames:
            if frame.frame_number == frame_num:
                drawing = frame.drawing
                if 'is_bound' in drawing.attributes:
                    attr_bound = drawing.attributes['is_bound'].data
                    for i in range(len(attr_bound)):
                        if attr_bound[i].value:
                            attr_bound[i].value = False
                            unbound_count += 1
                            
    return unbound_count

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

class STICKYGP_OT_unbind(bpy.types.Operator):
    """Unbind all GP strokes on the current frame"""
    bl_idname = "object.unbind_sticky_gp"
    bl_label = "Unbind Current Frame"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'GREASEPENCIL'

    def execute(self, context):
        gp_obj = context.active_object
        frame_num = context.scene.frame_current
        
        count = unbind_strokes_on_frame(gp_obj, frame_num)
        
        self.report({'INFO'}, f"Unbound {count} stroke points on frame {frame_num}")
        return {'FINISHED'}

class STICKYGP_OT_regenerate_uvs(bpy.types.Operator):
    """Regenerate the custom UV map (WARNING: Breaks existing strokes if topology changed)"""
    bl_idname = "object.regenerate_sticky_uvs"
    bl_label = "Regenerate Sticky UVs"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL' or not obj.sticky_gp_target:
            return False
        return "Sticky_GP_UVMap" in obj.sticky_gp_target.data.uv_layers

    def execute(self, context):
        target_obj = context.active_object.sticky_gp_target
        generate_sticky_uvs(target_obj)
        self.report({'INFO'}, f"Regenerated Sticky UVs for {target_obj.name}")
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
            target_obj = context.active_object.sticky_gp_target
        else:
            layout.label(text="Please select a GPencil object.", icon='ERROR')
            return
        
        row = layout.row()
        row.operator("object.bind_sticky_gp")
        
        row = layout.row()
        row.operator("object.unbind_sticky_gp")

        if target_obj and "Sticky_GP_UVMap" in target_obj.data.uv_layers:
            row = layout.row()
            row.operator("object.regenerate_sticky_uvs", icon='FILE_REFRESH')


def register():
    bpy.utils.register_class(STICKYGP_OT_bind)
    bpy.utils.register_class(STICKYGP_OT_unbind)
    bpy.utils.register_class(STICKYGP_OT_regenerate_uvs)
    bpy.utils.register_class(STICKYGP_PT_panel)
    bpy.types.Object.sticky_gp_target = bpy.props.PointerProperty(
        name="Target Mesh",
        type=bpy.types.Object,
        description="The mesh to stick the Grease Pencil strokes to"
    )

def unregister():
    bpy.utils.unregister_class(STICKYGP_OT_bind)
    bpy.utils.unregister_class(STICKYGP_OT_unbind)
    bpy.utils.unregister_class(STICKYGP_OT_regenerate_uvs)
    bpy.utils.unregister_class(STICKYGP_PT_panel)
    del bpy.types.Object.sticky_gp_target

if __name__ == "__main__":
    register()
