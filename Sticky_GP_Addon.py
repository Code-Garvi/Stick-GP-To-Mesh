bl_info = {
    "name": "Sticky Grease Pencil",
    "author": "Antigravity",
    "version": (1, 8),
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

def get_layer_target(gp_obj, layer_name):
    for item in gp_obj.sticky_gp_layer_targets:
        if item.layer_name == layer_name:
            return item.target_mesh
    return None

def generate_sticky_uvs(obj):
    import math
    mesh = obj.data
    uv_name = "Sticky_GP_UVMap"
    
    if uv_name in mesh.uv_layers:
        uv_layer = mesh.uv_layers[uv_name]
    else:
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

def create_sticky_gn_modifier(gp_obj, target_dict):
    mod_name = "Sticky_GP"
    if mod_name in gp_obj.modifiers:
        mod = gp_obj.modifiers[mod_name]
    else:
        mod = gp_obj.modifiers.new(name=mod_name, type='NODES')
    
    group_name = f"Sticky_GP_Nodes_{gp_obj.name}"
    if group_name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[group_name])
    
    node_group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
    
    node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    
    nodes = node_group.nodes
    links = node_group.links
    
    group_in = nodes.new('NodeGroupInput')
    group_out = nodes.new('NodeGroupOutput')
    
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
    
    bind_face_idx = nodes.new('GeometryNodeInputNamedAttribute')
    bind_face_idx.data_type = 'INT'
    bind_face_idx.inputs['Name'].default_value = 'bind_face_idx'
    
    bind_target_idx = nodes.new('GeometryNodeInputNamedAttribute')
    bind_target_idx.data_type = 'INT'
    bind_target_idx.inputs['Name'].default_value = 'bind_target_idx'
    
    input_pos = nodes.new('GeometryNodeInputPosition')
    input_normal = nodes.new('GeometryNodeInputNormal')
    
    last_geom_output = group_in.outputs['Geometry']
    
    for target_obj, idx in target_dict.items():
        obj_info = nodes.new('GeometryNodeObjectInfo')
        obj_info.transform_space = 'RELATIVE'
        obj_info.inputs['Object'].default_value = target_obj
        
        sample_pos = nodes.new('GeometryNodeSampleUVSurface')
        sample_pos.data_type = 'FLOAT_VECTOR'
        sample_normal = nodes.new('GeometryNodeSampleUVSurface')
        sample_normal.data_type = 'FLOAT_VECTOR'
        
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
        
        math_scale = nodes.new('ShaderNodeVectorMath')
        math_scale.operation = 'SCALE'
        math_add = nodes.new('ShaderNodeVectorMath')
        math_add.operation = 'ADD'
        
        cmp_target = nodes.new('FunctionNodeCompare')
        cmp_target.data_type = 'INT'
        cmp_target.operation = 'EQUAL'
        cmp_target.inputs[1].default_value = idx
        
        and_bound = nodes.new('FunctionNodeBooleanMath')
        and_bound.operation = 'AND'
        
        set_pos = nodes.new('GeometryNodeSetPosition')
        
        # Wiring
        links.new(obj_info.outputs['Geometry'], sample_pos.inputs['Mesh'])
        links.new(obj_info.outputs['Geometry'], sample_normal.inputs['Mesh'])
        links.new(obj_info.outputs['Geometry'], sample_idx_pos.inputs['Geometry'])
        links.new(obj_info.outputs['Geometry'], sample_idx_normal.inputs['Geometry'])
        
        links.new(input_pos.outputs['Position'], sample_idx_pos.inputs['Value'])
        links.new(bind_face_idx.outputs['Attribute'], sample_idx_pos.inputs['Index'])
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
        
        links.new(bind_target_idx.outputs['Attribute'], cmp_target.inputs[0])
        links.new(is_bound.outputs['Attribute'], and_bound.inputs[0])
        links.new(cmp_target.outputs['Result'], and_bound.inputs[1])
        
        links.new(last_geom_output, set_pos.inputs['Geometry'])
        links.new(and_bound.outputs['Boolean'], set_pos.inputs['Selection'])
        links.new(math_add.outputs['Vector'], set_pos.inputs['Position'])
        
        last_geom_output = set_pos.outputs['Geometry']
        
    links.new(last_geom_output, group_out.inputs['Geometry'])
    mod.node_group = node_group

def bind_unbound_strokes(gp_obj, frame_num=None):
    gp_data = gp_obj.data
    
    target_dict = {}
    idx = 1
    for layer in gp_data.layers:
        target = get_layer_target(gp_obj, layer.name)
        if target:
            if target not in target_dict:
                target_dict[target] = idx
                idx += 1
                
    if not target_dict:
        return 0, {}
        
    create_sticky_gn_modifier(gp_obj, target_dict)
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh_cache = {}
    
    for target_obj in target_dict.keys():
        if "Sticky_GP_UVMap" not in target_obj.data.uv_layers:
            generate_sticky_uvs(target_obj)
            
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
        
        gp_to_world = gp_obj.matrix_world
        world_to_target = target_obj.matrix_world.inverted()
        gp_to_target = world_to_target @ gp_to_world
        
        bvh_cache[target_obj] = (bvh, bm, uv_layer, idx_layer, gp_to_target)

    bound_count = 0
    current_scene_frame = bpy.context.scene.frame_current
    for layer in gp_data.layers:
        target_obj = get_layer_target(gp_obj, layer.name)
        if not target_obj:
            continue
            
        target_idx = target_dict[target_obj]
        bvh, bm, uv_layer, idx_layer, gp_to_target = bvh_cache[target_obj]
        
        target_frames = set()
        if frame_num is not None:
            target_frames.add(frame_num)
        else:
            active_f_num = -999999
            for f in layer.frames:
                if f.frame_number <= current_scene_frame and f.frame_number > active_f_num:
                    active_f_num = f.frame_number
            if active_f_num != -999999:
                target_frames.add(active_f_num)
                
        for frame in layer.frames:
            if frame.frame_number not in target_frames:
                continue
            drawing = frame.drawing
            
            if 'bind_uv' not in drawing.attributes:
                drawing.attributes.new(name='bind_uv', type='FLOAT2', domain='POINT')
            if 'bind_dist' not in drawing.attributes:
                drawing.attributes.new(name='bind_dist', type='FLOAT', domain='POINT')
            if 'is_bound' not in drawing.attributes:
                drawing.attributes.new(name='is_bound', type='BOOLEAN', domain='POINT')
            if 'bind_face_idx' not in drawing.attributes:
                drawing.attributes.new(name='bind_face_idx', type='INT', domain='POINT')
            if 'bind_target_idx' not in drawing.attributes:
                drawing.attributes.new(name='bind_target_idx', type='INT', domain='POINT')
                
            attr_uv = drawing.attributes['bind_uv'].data
            attr_dist = drawing.attributes['bind_dist'].data
            attr_bound = drawing.attributes['is_bound'].data
            attr_idx = drawing.attributes['bind_face_idx'].data
            attr_target_idx = drawing.attributes['bind_target_idx'].data
            
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
                                attr_target_idx[i].value = target_idx
                                bound_count += 1
                                
    for target_obj, cache_data in bvh_cache.items():
        cache_data[1].free()
        target_obj.evaluated_get(depsgraph).to_mesh_clear()
        target_obj.sticky_gp_polycount = len(target_obj.data.polygons)
        
    return bound_count, target_dict

def unbind_strokes_on_frame(gp_obj, frame_num=None):
    gp_data = gp_obj.data
    unbound_count = 0
    current_scene_frame = bpy.context.scene.frame_current
    
    for layer in gp_data.layers:
        target_frames = set()
        if frame_num is not None:
            target_frames.add(frame_num)
        else:
            active_f_num = -999999
            for f in layer.frames:
                if f.frame_number <= current_scene_frame and f.frame_number > active_f_num:
                    active_f_num = f.frame_number
            if active_f_num != -999999:
                target_frames.add(active_f_num)
                
        for frame in layer.frames:
            if frame.frame_number in target_frames:
                drawing = frame.drawing
                if 'is_bound' in drawing.attributes:
                    attr_bound = drawing.attributes['is_bound'].data
                    for i in range(len(attr_bound)):
                        if attr_bound[i].value:
                            attr_bound[i].value = False
                            unbound_count += 1
                            
    return unbound_count

class STICKYGP_OT_bind(bpy.types.Operator):
    """Bind newly drawn GP strokes to their target meshes"""
    bl_idname = "object.bind_sticky_gp"
    bl_label = "Bind Visible Strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            return False
        return any(get_layer_target(obj, layer.name) for layer in obj.data.layers)

    def execute(self, context):
        gp_obj = context.active_object
        
        count, targets = bind_unbound_strokes(gp_obj)
        
        self.report({'INFO'}, f"Bound {count} stroke points across {len(targets)} meshes")
        return {'FINISHED'}

class STICKYGP_OT_unbind(bpy.types.Operator):
    """Unbind all visible GP strokes"""
    bl_idname = "object.unbind_sticky_gp"
    bl_label = "Unbind Visible Strokes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'GREASEPENCIL'

    def execute(self, context):
        gp_obj = context.active_object
        
        count = unbind_strokes_on_frame(gp_obj)
        
        self.report({'INFO'}, f"Unbound {count} visible stroke points")
        return {'FINISHED'}

class STICKYGP_OT_fix_strokes(bpy.types.Operator):
    """Mesh changed! Regenerate UVs and restick all existing keyframes"""
    bl_idname = "object.fix_sticky_gp_strokes"
    bl_label = "Fix Strokes (Mesh Changed)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            return False
        return any(get_layer_target(obj, layer.name) for layer in obj.data.layers)

    def execute(self, context):
        gp_obj = context.active_object
        
        # Collect all targeted meshes
        target_meshes = set()
        for layer in gp_obj.data.layers:
            target = get_layer_target(gp_obj, layer.name)
            if target:
                target_meshes.add(target)
                
        for target_obj in target_meshes:
            generate_sticky_uvs(target_obj)
        
        # Collect all unique frames that have strokes
        frame_nums = set()
        for layer in gp_obj.data.layers:
            for frame in layer.frames:
                frame_nums.add(frame.frame_number)
                
        original_frame = context.scene.frame_current
        
        rebound_count = 0
        for f_num in sorted(list(frame_nums)):
            context.scene.frame_set(f_num)
            
            # Unbind strokes on this frame
            for layer in gp_obj.data.layers:
                for frame in layer.frames:
                    if frame.frame_number == f_num:
                        drawing = frame.drawing
                        if 'is_bound' in drawing.attributes:
                            attr_bound = drawing.attributes['is_bound'].data
                            for i in range(len(attr_bound)):
                                attr_bound[i].value = False
                                
            # Rebind on this frame
            count, _ = bind_unbound_strokes(gp_obj, f_num)
            rebound_count += count
            
        context.scene.frame_set(original_frame)
        
        self.report({'INFO'}, f"Fixed {rebound_count} stroke points after mesh change.")
        return {'FINISHED'}

class STICKYGP_OT_add_layer_target(bpy.types.Operator):
    """Assign a target mesh to this layer"""
    bl_idname = "object.add_sticky_gp_layer_target"
    bl_label = "Add Target Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    layer_name: bpy.props.StringProperty()
    
    def execute(self, context):
        obj = context.active_object
        item = obj.sticky_gp_layer_targets.add()
        item.layer_name = self.layer_name
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
        obj = context.active_object
        
        if not obj or obj.type != 'GREASEPENCIL':
            layout.label(text="Please select a GPencil object.", icon='ERROR')
            return
            
        box = layout.box()
        box.label(text="Layer Targets:", icon='GROUP_VERTEX')
        for layer in obj.data.layers:
            row = box.row()
            item = None
            for it in obj.sticky_gp_layer_targets:
                if it.layer_name == layer.name:
                    item = it
                    break
            
            if item:
                row.prop(item, "target_mesh", text=layer.name)
            else:
                row.label(text=layer.name)
                op = row.operator("object.add_sticky_gp_layer_target", text="Assign Mesh")
                op.layer_name = layer.name
            
        layout.separator()
        
        row = layout.row()
        row.operator("object.bind_sticky_gp")
        
        row = layout.row()
        row.operator("object.unbind_sticky_gp")

        # Global polycount check
        needs_fix = False
        for layer in obj.data.layers:
            target = get_layer_target(obj, layer.name)
            if target:
                if len(target.data.polygons) != target.sticky_gp_polycount:
                    needs_fix = True
                    break
                    
        if needs_fix:
            row = layout.row()
            row.alert = True
            row.operator("object.fix_sticky_gp_strokes", icon='ERROR')
            
        layout.separator()
        help_box = layout.box()
        help_box.label(text="How to Use:", icon='INFO')
        col = help_box.column(align=True)
        col.label(text="1. Assign target meshes to your layers.")
        col.label(text="2. Draw on your character.")
        col.label(text="3. Click 'Bind Visible Strokes'.")
        col.label(text="4. Sculpt and animate freely!")
        col.label(text="Note: If you add/delete polygons,")
        col.label(text="the red Fix Strokes button will")
        col.label(text="appear. Click it to auto-fix!")


class STICKYGP_LayerTarget(bpy.types.PropertyGroup):
    layer_name: bpy.props.StringProperty()
    target_mesh: bpy.props.PointerProperty(type=bpy.types.Object)

def register():
    bpy.utils.register_class(STICKYGP_LayerTarget)
    bpy.utils.register_class(STICKYGP_OT_add_layer_target)
    bpy.utils.register_class(STICKYGP_OT_bind)
    bpy.utils.register_class(STICKYGP_OT_unbind)
    bpy.utils.register_class(STICKYGP_OT_fix_strokes)
    bpy.utils.register_class(STICKYGP_PT_panel)
    bpy.types.Object.sticky_gp_layer_targets = bpy.props.CollectionProperty(
        type=STICKYGP_LayerTarget,
        name="Layer Targets"
    )
    bpy.types.Object.sticky_gp_polycount = bpy.props.IntProperty(
        name="Polycount Cache",
        default=0,
        description="Tracks the last known polycount of the mesh to detect topological changes"
    )

def unregister():
    bpy.utils.unregister_class(STICKYGP_OT_bind)
    bpy.utils.unregister_class(STICKYGP_OT_unbind)
    bpy.utils.unregister_class(STICKYGP_OT_fix_strokes)
    bpy.utils.unregister_class(STICKYGP_PT_panel)
    bpy.utils.unregister_class(STICKYGP_OT_add_layer_target)
    bpy.utils.unregister_class(STICKYGP_LayerTarget)
    del bpy.types.Object.sticky_gp_layer_targets
    del bpy.types.Object.sticky_gp_polycount

if __name__ == "__main__":
    register()
