bl_info = {
    "name": "Sticky Grease Pencil",
    "author": "Antigravity",
    "version": (2, 2),
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

def get_layer_targets(gp_obj, layer_name):
    targets = []
    for item in gp_obj.sticky_gp_layer_targets:
        if item.layer_name == layer_name:
            if item.target_mode == 'OBJECT' and item.target_mesh and item.target_mesh.type == 'MESH':
                targets.append(item.target_mesh)
            elif item.target_mode == 'COLLECTION' and item.target_collection:
                for obj in item.target_collection.objects:
                    if obj.type == 'MESH':
                        targets.append(obj)
            break
    return targets

def create_sticky_gn_modifier(gp_obj, target_dict, force_rebuild=False):
    mod_name = "Sticky_GP"
    group_name = f"Sticky_GP_Nodes_{gp_obj.name}"
    
    # Create a string hash of the current required targets
    target_hash = ",".join(sorted([obj.name for obj in target_dict.keys()]))
    
    # OPTIMIZATION: If we aren't forcing a rebuild (e.g. from addon reload), 
    # check if the existing nodes already support the exact same targets.
    if not force_rebuild:
        if mod_name in gp_obj.modifiers and group_name in bpy.data.node_groups:
            existing_group = bpy.data.node_groups[group_name]
            if existing_group.get("sticky_gp_targets") == target_hash:
                return # Skip rebuild, existing GN modifier is perfectly valid
    
    # If we reached here, a rebuild is required. Nuke the old ones.
    if group_name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[group_name])
        
    if mod_name in gp_obj.modifiers:
        gp_obj.modifiers.remove(gp_obj.modifiers[mod_name])
        
    mod = gp_obj.modifiers.new(name=mod_name, type='NODES')
    
    node_group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
    node_group["sticky_gp_targets"] = target_hash  # Save the hash for future checks
    node_group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    node_group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    
    nodes = node_group.nodes
    links = node_group.links
    
    group_in = nodes.new('NodeGroupInput')
    group_out = nodes.new('NodeGroupOutput')
    
    bind_v1 = nodes.new('GeometryNodeInputNamedAttribute')
    bind_v1.data_type = 'INT'
    bind_v1.inputs['Name'].default_value = 'bind_v1'
    
    bind_v2 = nodes.new('GeometryNodeInputNamedAttribute')
    bind_v2.data_type = 'INT'
    bind_v2.inputs['Name'].default_value = 'bind_v2'
    
    bind_v3 = nodes.new('GeometryNodeInputNamedAttribute')
    bind_v3.data_type = 'INT'
    bind_v3.inputs['Name'].default_value = 'bind_v3'
    
    bind_bary = nodes.new('GeometryNodeInputNamedAttribute')
    bind_bary.data_type = 'FLOAT_VECTOR'
    bind_bary.inputs['Name'].default_value = 'bind_bary'
    
    bind_dist = nodes.new('GeometryNodeInputNamedAttribute')
    bind_dist.data_type = 'FLOAT'
    bind_dist.inputs['Name'].default_value = 'bind_dist'
    
    is_bound = nodes.new('GeometryNodeInputNamedAttribute')
    is_bound.data_type = 'BOOLEAN'
    is_bound.inputs['Name'].default_value = 'is_bound'
    
    bind_target_idx = nodes.new('GeometryNodeInputNamedAttribute')
    bind_target_idx.data_type = 'INT'
    bind_target_idx.inputs['Name'].default_value = 'bind_target_idx'
    
    input_pos = nodes.new('GeometryNodeInputPosition')
    input_normal = nodes.new('GeometryNodeInputNormal')
    
    global_offset_node = nodes.new('ShaderNodeValue')
    global_offset_node.name = "GlobalOffsetValue"
    global_offset_node.outputs[0].default_value = gp_obj.sticky_gp_global_offset
    
    sep_bary = nodes.new('ShaderNodeSeparateXYZ')
    links.new(bind_bary.outputs['Attribute'], sep_bary.inputs['Vector'])
    
    last_geom_output = group_in.outputs['Geometry']
    
    for target_obj, idx in target_dict.items():
        obj_info = nodes.new('GeometryNodeObjectInfo')
        obj_info.transform_space = 'RELATIVE'
        obj_info.inputs['Object'].default_value = target_obj
        
        # Position samples
        sp1 = nodes.new('GeometryNodeSampleIndex')
        sp1.data_type = 'FLOAT_VECTOR'
        sp1.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sp1.inputs['Geometry'])
        links.new(input_pos.outputs['Position'], sp1.inputs['Value'])
        links.new(bind_v1.outputs['Attribute'], sp1.inputs['Index'])
        
        sp2 = nodes.new('GeometryNodeSampleIndex')
        sp2.data_type = 'FLOAT_VECTOR'
        sp2.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sp2.inputs['Geometry'])
        links.new(input_pos.outputs['Position'], sp2.inputs['Value'])
        links.new(bind_v2.outputs['Attribute'], sp2.inputs['Index'])
        
        sp3 = nodes.new('GeometryNodeSampleIndex')
        sp3.data_type = 'FLOAT_VECTOR'
        sp3.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sp3.inputs['Geometry'])
        links.new(input_pos.outputs['Position'], sp3.inputs['Value'])
        links.new(bind_v3.outputs['Attribute'], sp3.inputs['Index'])
        
        # Position math
        m_p1 = nodes.new('ShaderNodeVectorMath')
        m_p1.operation = 'SCALE'
        links.new(sp1.outputs['Value'], m_p1.inputs[0])
        links.new(sep_bary.outputs['X'], m_p1.inputs['Scale'])
        
        m_p2 = nodes.new('ShaderNodeVectorMath')
        m_p2.operation = 'SCALE'
        links.new(sp2.outputs['Value'], m_p2.inputs[0])
        links.new(sep_bary.outputs['Y'], m_p2.inputs['Scale'])
        
        m_p3 = nodes.new('ShaderNodeVectorMath')
        m_p3.operation = 'SCALE'
        links.new(sp3.outputs['Value'], m_p3.inputs[0])
        links.new(sep_bary.outputs['Z'], m_p3.inputs['Scale'])
        
        add_p12 = nodes.new('ShaderNodeVectorMath')
        add_p12.operation = 'ADD'
        links.new(m_p1.outputs['Vector'], add_p12.inputs[0])
        links.new(m_p2.outputs['Vector'], add_p12.inputs[1])
        
        add_p_all = nodes.new('ShaderNodeVectorMath')
        add_p_all.operation = 'ADD'
        links.new(add_p12.outputs['Vector'], add_p_all.inputs[0])
        links.new(m_p3.outputs['Vector'], add_p_all.inputs[1])
        
        # Normal samples
        sn1 = nodes.new('GeometryNodeSampleIndex')
        sn1.data_type = 'FLOAT_VECTOR'
        sn1.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sn1.inputs['Geometry'])
        links.new(input_normal.outputs['Normal'], sn1.inputs['Value'])
        links.new(bind_v1.outputs['Attribute'], sn1.inputs['Index'])
        
        sn2 = nodes.new('GeometryNodeSampleIndex')
        sn2.data_type = 'FLOAT_VECTOR'
        sn2.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sn2.inputs['Geometry'])
        links.new(input_normal.outputs['Normal'], sn2.inputs['Value'])
        links.new(bind_v2.outputs['Attribute'], sn2.inputs['Index'])
        
        sn3 = nodes.new('GeometryNodeSampleIndex')
        sn3.data_type = 'FLOAT_VECTOR'
        sn3.domain = 'POINT'
        links.new(obj_info.outputs['Geometry'], sn3.inputs['Geometry'])
        links.new(input_normal.outputs['Normal'], sn3.inputs['Value'])
        links.new(bind_v3.outputs['Attribute'], sn3.inputs['Index'])
        
        # Normal math
        m_n1 = nodes.new('ShaderNodeVectorMath')
        m_n1.operation = 'SCALE'
        links.new(sn1.outputs['Value'], m_n1.inputs[0])
        links.new(sep_bary.outputs['X'], m_n1.inputs['Scale'])
        
        m_n2 = nodes.new('ShaderNodeVectorMath')
        m_n2.operation = 'SCALE'
        links.new(sn2.outputs['Value'], m_n2.inputs[0])
        links.new(sep_bary.outputs['Y'], m_n2.inputs['Scale'])
        
        m_n3 = nodes.new('ShaderNodeVectorMath')
        m_n3.operation = 'SCALE'
        links.new(sn3.outputs['Value'], m_n3.inputs[0])
        links.new(sep_bary.outputs['Z'], m_n3.inputs['Scale'])
        
        add_n12 = nodes.new('ShaderNodeVectorMath')
        add_n12.operation = 'ADD'
        links.new(m_n1.outputs['Vector'], add_n12.inputs[0])
        links.new(m_n2.outputs['Vector'], add_n12.inputs[1])
        
        add_n_all = nodes.new('ShaderNodeVectorMath')
        add_n_all.operation = 'ADD'
        links.new(add_n12.outputs['Vector'], add_n_all.inputs[0])
        links.new(m_n3.outputs['Vector'], add_n_all.inputs[1])
        
        norm_n = nodes.new('ShaderNodeVectorMath')
        norm_n.operation = 'NORMALIZE'
        links.new(add_n_all.outputs['Vector'], norm_n.inputs[0])
        
        # Offset pos
        scale_dist = nodes.new('ShaderNodeVectorMath')
        scale_dist.operation = 'SCALE'
        links.new(norm_n.outputs['Vector'], scale_dist.inputs[0])
        
        add_dist = nodes.new('ShaderNodeMath')
        add_dist.operation = 'ADD'
        links.new(bind_dist.outputs['Attribute'], add_dist.inputs[0])
        links.new(global_offset_node.outputs[0], add_dist.inputs[1])
        links.new(add_dist.outputs[0], scale_dist.inputs['Scale'])
        
        final_pos = nodes.new('ShaderNodeVectorMath')
        final_pos.operation = 'ADD'
        links.new(add_p_all.outputs['Vector'], final_pos.inputs[0])
        links.new(scale_dist.outputs['Vector'], final_pos.inputs[1])
        
        # Routing
        cmp_target = nodes.new('FunctionNodeCompare')
        cmp_target.data_type = 'INT'
        cmp_target.operation = 'EQUAL'
        cmp_target.inputs[1].default_value = idx
        
        and_bound = nodes.new('FunctionNodeBooleanMath')
        and_bound.operation = 'AND'
        links.new(bind_target_idx.outputs['Attribute'], cmp_target.inputs[0])
        links.new(is_bound.outputs['Attribute'], and_bound.inputs[0])
        links.new(cmp_target.outputs['Result'], and_bound.inputs[1])
        
        set_pos = nodes.new('GeometryNodeSetPosition')
        links.new(last_geom_output, set_pos.inputs['Geometry'])
        links.new(and_bound.outputs['Boolean'], set_pos.inputs['Selection'])
        links.new(final_pos.outputs['Vector'], set_pos.inputs['Position'])
        
        last_geom_output = set_pos.outputs['Geometry']
        
    links.new(last_geom_output, group_out.inputs['Geometry'])
    mod.node_group = node_group

def bind_unbound_strokes(gp_obj, frame_num=None):
    gp_data = gp_obj.data
    
    target_dict = {}
    idx = 1
    for layer in gp_data.layers:
        targets = get_layer_targets(gp_obj, layer.name)
        for target in targets:
            if target not in target_dict:
                target_dict[target] = idx
                idx += 1
                
    if not target_dict:
        return 0, {}
        
    create_sticky_gn_modifier(gp_obj, target_dict)
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh_cache = {}
    
    for target_obj in target_dict.keys():
        mesh = get_evaluated_mesh(target_obj, depsgraph)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.faces.ensure_lookup_table()
        bvh = mathutils.bvhtree.BVHTree.FromBMesh(bm)
        
        gp_to_world = gp_obj.matrix_world
        world_to_target = target_obj.matrix_world.inverted()
        gp_to_target = world_to_target @ gp_to_world
        
        bvh_cache[target_obj] = (bvh, bm, gp_to_target)

    bound_count = 0
    current_scene_frame = bpy.context.scene.frame_current
    for layer in gp_data.layers:
        target_objs = get_layer_targets(gp_obj, layer.name)
        if not target_objs:
            continue
        
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
            
            if 'bind_v1' not in drawing.attributes:
                drawing.attributes.new(name='bind_v1', type='INT', domain='POINT')
            if 'bind_v2' not in drawing.attributes:
                drawing.attributes.new(name='bind_v2', type='INT', domain='POINT')
            if 'bind_v3' not in drawing.attributes:
                drawing.attributes.new(name='bind_v3', type='INT', domain='POINT')
            if 'bind_bary' not in drawing.attributes:
                drawing.attributes.new(name='bind_bary', type='FLOAT_VECTOR', domain='POINT')
            if 'bind_dist' not in drawing.attributes:
                drawing.attributes.new(name='bind_dist', type='FLOAT', domain='POINT')
            if 'is_bound' not in drawing.attributes:
                drawing.attributes.new(name='is_bound', type='BOOLEAN', domain='POINT')
            if 'bind_target_idx' not in drawing.attributes:
                drawing.attributes.new(name='bind_target_idx', type='INT', domain='POINT')
                
            attr_v1 = drawing.attributes['bind_v1'].data
            attr_v2 = drawing.attributes['bind_v2'].data
            attr_v3 = drawing.attributes['bind_v3'].data
            attr_bary = drawing.attributes['bind_bary'].data
            attr_dist = drawing.attributes['bind_dist'].data
            attr_bound = drawing.attributes['is_bound'].data
            attr_target_idx = drawing.attributes['bind_target_idx'].data
            
            if 'position' in drawing.attributes:
                points = drawing.attributes['position'].data
                for i in range(len(points)):
                    if not attr_bound[i].value:
                        pos_gp = points[i].vector
                        
                        best_dist = float('inf')
                        best_match = None
                        
                        for target_obj in target_objs:
                            bvh, bm, gp_to_target = bvh_cache[target_obj]
                            pos_target = gp_to_target @ pos_gp
                            location, normal, index, distance = bvh.find_nearest(pos_target)
                            
                            if location is not None and distance < best_dist:
                                best_dist = distance
                                best_match = (target_obj, location, index, distance, bm)
                                
                        if best_match is not None:
                            target_obj, location, index, distance, bm = best_match
                            target_idx = target_dict[target_obj]
                            
                            face = bm.faces[index]
                            v1, v2, v3 = (v.co for v in face.verts[:3])
                            bary = mathutils.geometry.barycentric_transform(location, v1, v2, v3, mathutils.Vector((1,0,0)), mathutils.Vector((0,1,0)), mathutils.Vector((0,0,1)))
                            
                            attr_v1[i].value = face.verts[0].index
                            attr_v2[i].value = face.verts[1].index
                            attr_v3[i].value = face.verts[2].index
                            attr_bary[i].vector = bary
                            attr_dist[i].value = distance
                            attr_bound[i].value = True
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
        return any(get_layer_targets(obj, layer.name) for layer in obj.data.layers)

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
        return any(get_layer_targets(obj, layer.name) for layer in obj.data.layers)

    def execute(self, context):
        gp_obj = context.active_object
        
        # Collect all targeted meshes
        target_meshes = set()
        for layer in gp_obj.data.layers:
            targets = get_layer_targets(gp_obj, layer.name)
            for target in targets:
                target_meshes.add(target)
                
        
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
                row.label(text=layer.name)
                row.prop(item, "target_mode", text="")
                if item.target_mode == 'OBJECT':
                    row.prop(item, "target_mesh", text="")
                else:
                    row.prop(item, "target_collection", text="")
            else:
                row.label(text=layer.name)
                op = row.operator("object.add_sticky_gp_layer_target", text="Assign Mesh")
                op.layer_name = layer.name
            
        layout.separator()
        
        row = layout.row()
        row.prop(obj, "sticky_gp_global_offset")
        
        layout.separator()
        
        row = layout.row()
        row.operator("object.bind_sticky_gp")
        
        row = layout.row()
        row.operator("object.unbind_sticky_gp")

        # Global polycount check
        needs_fix = False
        for layer in obj.data.layers:
            targets = get_layer_targets(obj, layer.name)
            for target in targets:
                if len(target.data.polygons) != target.sticky_gp_polycount:
                    needs_fix = True
                    break
            if needs_fix:
                break
                    
        if needs_fix:
            row = layout.row()
            row.alert = True
            row.operator("object.fix_sticky_gp_strokes", icon='ERROR')
            
        layout.separator()
        row = layout.row()
        icon = 'TRIA_DOWN' if context.scene.stickygp_show_guide else 'TRIA_RIGHT'
        row.prop(context.scene, "stickygp_show_guide", icon=icon, emboss=False)
        if context.scene.stickygp_show_guide:
            help_box = layout.box()
            col = help_box.column(align=True)
            col.label(text="- Setup: Assign a Target Mesh or Collection.")
            col.label(text="- Draw: Draw strokes anywhere near the target.")
            col.label(text="- Bind / Unbind: Attach strokes, or detach them.")
            col.label(text="- Tweak: Use 'Global Offset' to fix clipping.")
            col.label(text="- Fix: Click red warning to re-bake if mesh changes.")


class STICKYGP_LayerTarget(bpy.types.PropertyGroup):
    layer_name: bpy.props.StringProperty()
    target_mode: bpy.props.EnumProperty(
        items=[('OBJECT', "Object", ""), ('COLLECTION', "Collection", "")],
        name="Target Mode",
        default='OBJECT'
    )
    target_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH',
        description="Select the mesh to stick this layer's strokes to"
    )
    target_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        description="Select the collection of meshes to stick this layer's strokes to"
    )


def auto_rebuild_gn_on_reload():
    # Only run once on reload
    for obj in bpy.data.objects:
        if obj.type in {'GREASEPENCIL', 'GREASEPENCIL_V3'} or obj.type.startswith('GREASEPENCIL'):
            if "Sticky_GP" in obj.modifiers:
                target_dict = {}
                idx = 1
                if hasattr(obj.data, 'layers'):
                    for layer in obj.data.layers:
                        targets = get_layer_targets(obj, layer.name)
                        for target in targets:
                            if target not in target_dict:
                                target_dict[target] = idx
                                idx += 1
                if target_dict:
                    create_sticky_gn_modifier(obj, target_dict, force_rebuild=True)
    return None

def update_offset(self, context):
    mod_name = "Sticky_GP"
    if mod_name in self.modifiers:
        group_name = f"Sticky_GP_Nodes_{self.name}"
        if group_name in bpy.data.node_groups:
            node_group = bpy.data.node_groups[group_name]
            if "GlobalOffsetValue" in node_group.nodes:
                node_group.nodes["GlobalOffsetValue"].outputs[0].default_value = self.sticky_gp_global_offset

def register():
    bpy.utils.register_class(STICKYGP_LayerTarget)
    if bpy.app.background is False:
        bpy.app.timers.register(auto_rebuild_gn_on_reload, first_interval=0.1)
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
    bpy.types.Object.sticky_gp_global_offset = bpy.props.FloatProperty(
        name="Global Offset",
        default=0.0,
        min=-1.0,
        max=1.0,
        description="Offsets all bound strokes outwards or inwards from the mesh surface",
        update=update_offset
    )
    bpy.types.Scene.stickygp_show_guide = bpy.props.BoolProperty(
        name="Quick Guide",
        default=False
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
    
    if hasattr(bpy.types.Scene, "stickygp_show_guide"):
        del bpy.types.Scene.stickygp_show_guide

if __name__ == "__main__":
    register()

