bl_info = {
    "name": "Sticky Grease Pencil",
    "author": "Antigravity",
    "version": (3, 0, 0),
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

def ensure_rest_position(obj):
    if obj.type != 'MESH': return
    if 'rest_position' not in obj.data.attributes:
        attr = obj.data.attributes.new(name='rest_position', type='FLOAT_VECTOR', domain='POINT')
        import numpy as np
        coords = np.empty((len(obj.data.vertices), 3), dtype=np.float32)
        obj.data.vertices.foreach_get("co", coords.ravel())
        attr.data.foreach_set("vector", coords.ravel())
        obj.data.update_tag()

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
    
    bind_rest_pos = nodes.new('GeometryNodeInputNamedAttribute')
    bind_rest_pos.data_type = 'FLOAT_VECTOR'
    bind_rest_pos.inputs['Name'].default_value = 'bind_rest_pos'
    
    bind_dist = nodes.new('GeometryNodeInputNamedAttribute')
    bind_dist.data_type = 'FLOAT'
    bind_dist.inputs['Name'].default_value = 'bind_dist'
    
    is_bound = nodes.new('GeometryNodeInputNamedAttribute')
    is_bound.data_type = 'BOOLEAN'
    is_bound.inputs['Name'].default_value = 'is_bound'
    
    bind_target_idx = nodes.new('GeometryNodeInputNamedAttribute')
    bind_target_idx.data_type = 'INT'
    bind_target_idx.inputs['Name'].default_value = 'bind_target_idx'
    
    global_offset_node = nodes.new('ShaderNodeValue')
    global_offset_node.name = "GlobalOffsetValue"
    global_offset_node.outputs[0].default_value = gp_obj.sticky_gp_global_offset
    
    last_geom_output = group_in.outputs['Geometry']
    
    for target_obj, idx in target_dict.items():
        # Deformed Target Mesh
        obj_info = nodes.new('GeometryNodeObjectInfo')
        obj_info.transform_space = 'RELATIVE'
        obj_info.inputs['Object'].default_value = target_obj
        
        target_geom = obj_info.outputs['Geometry']
        
        # Store deformed Position
        store_pos = nodes.new('GeometryNodeStoreNamedAttribute')
        store_pos.data_type = 'FLOAT_VECTOR'
        store_pos.domain = 'POINT'
        store_pos.inputs['Name'].default_value = '_deformed_pos'
        store_pos.inputs['Value'].default_value = (0,0,0) # We will link Position to this
        pos_input = nodes.new('GeometryNodeInputPosition')
        links.new(target_geom, store_pos.inputs['Geometry'])
        links.new(pos_input.outputs['Position'], store_pos.inputs['Value'])
        
        # Store deformed Normal
        store_norm = nodes.new('GeometryNodeStoreNamedAttribute')
        store_norm.data_type = 'FLOAT_VECTOR'
        store_norm.domain = 'POINT'
        store_norm.inputs['Name'].default_value = '_deformed_normal'
        store_norm.inputs['Value'].default_value = (0,0,0)
        norm_input = nodes.new('GeometryNodeInputNormal')
        links.new(store_pos.outputs['Geometry'], store_norm.inputs['Geometry'])
        links.new(norm_input.outputs['Normal'], store_norm.inputs['Value'])
        
        # Snap target mesh back to rest_position
        rest_attr = nodes.new('GeometryNodeInputNamedAttribute')
        rest_attr.data_type = 'FLOAT_VECTOR'
        rest_attr.inputs['Name'].default_value = 'rest_position'
        
        set_rest = nodes.new('GeometryNodeSetPosition')
        links.new(store_norm.outputs['Geometry'], set_rest.inputs['Geometry'])
        links.new(rest_attr.outputs['Attribute'], set_rest.inputs['Position'])
        
        set_rest_offset = nodes.new('GeometryNodeSetPosition')
        links.new(set_rest.outputs['Geometry'], set_rest_offset.inputs['Geometry'])
        
        rest_normal_node = nodes.new('GeometryNodeInputNormal')
        
        push_math = nodes.new('ShaderNodeVectorMath')
        push_math.operation = 'SCALE'
        links.new(rest_normal_node.outputs['Normal'], push_math.inputs[0])
        push_math.inputs['Scale'].default_value = 0.0001
        
        links.new(push_math.outputs['Vector'], set_rest_offset.inputs['Offset'])
        
        rest_target_geom = set_rest_offset.outputs['Geometry']
        
        # Sample Nearest Surface on Rest Mesh
        sample_pos = nodes.new('GeometryNodeSampleNearestSurface')
        sample_pos.data_type = 'FLOAT_VECTOR'
        links.new(rest_target_geom, sample_pos.inputs['Mesh'])
        
        deformed_pos_attr = nodes.new('GeometryNodeInputNamedAttribute')
        deformed_pos_attr.data_type = 'FLOAT_VECTOR'
        deformed_pos_attr.inputs['Name'].default_value = '_deformed_pos'
        
        links.new(deformed_pos_attr.outputs['Attribute'], sample_pos.inputs['Value'])
        links.new(bind_rest_pos.outputs['Attribute'], sample_pos.inputs['Sample Position'])
        
        sampled_deformed_pos = sample_pos.outputs['Value']
        
        sample_norm = nodes.new('GeometryNodeSampleNearestSurface')
        sample_norm.data_type = 'FLOAT_VECTOR'
        links.new(rest_target_geom, sample_norm.inputs['Mesh'])
        
        deformed_norm_attr = nodes.new('GeometryNodeInputNamedAttribute')
        deformed_norm_attr.data_type = 'FLOAT_VECTOR'
        deformed_norm_attr.inputs['Name'].default_value = '_deformed_normal'
        
        links.new(deformed_norm_attr.outputs['Attribute'], sample_norm.inputs['Value'])
        links.new(bind_rest_pos.outputs['Attribute'], sample_norm.inputs['Sample Position'])
        
        sampled_deformed_norm = sample_norm.outputs['Value']
        
        # Normalize the sampled normal
        norm_n = nodes.new('ShaderNodeVectorMath')
        norm_n.operation = 'NORMALIZE'
        links.new(sampled_deformed_norm, norm_n.inputs[0])
        
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
        links.new(sampled_deformed_pos, final_pos.inputs[0])
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
                ensure_rest_position(target)
                target_dict[target] = idx
                idx += 1
                
    if not target_dict:
        return 0, {}
        
    create_sticky_gn_modifier(gp_obj, target_dict)
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh_cache = {}
    
    for target_obj in target_dict.keys():
        mesh = get_evaluated_mesh(target_obj, depsgraph)
        
        if 'rest_position' in mesh.attributes:
            rest_pos_attr = mesh.attributes['rest_position'].data
        else:
            # Fallback if somehow update_tag didn't push it to the evaluated mesh yet
            ensure_rest_position(target_obj)
            depsgraph.update()
            mesh = get_evaluated_mesh(target_obj, depsgraph)
            rest_pos_attr = mesh.attributes['rest_position'].data
            
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.faces.ensure_lookup_table()
        bvh = mathutils.bvhtree.BVHTree.FromBMesh(bm)
        
        gp_to_world = gp_obj.matrix_world
        world_to_target = target_obj.matrix_world.inverted()
        gp_to_target = world_to_target @ gp_to_world
        target_to_gp = gp_to_target.inverted()
        
        bvh_cache[target_obj] = (bvh, bm, gp_to_target, target_to_gp, rest_pos_attr)

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
            
            if 'bind_rest_pos' not in drawing.attributes:
                drawing.attributes.new(name='bind_rest_pos', type='FLOAT_VECTOR', domain='POINT')
            if 'bind_dist' not in drawing.attributes:
                drawing.attributes.new(name='bind_dist', type='FLOAT', domain='POINT')
            if 'is_bound' not in drawing.attributes:
                drawing.attributes.new(name='is_bound', type='BOOLEAN', domain='POINT')
            if 'bind_target_idx' not in drawing.attributes:
                drawing.attributes.new(name='bind_target_idx', type='INT', domain='POINT')
                
            attr_rest_pos = drawing.attributes['bind_rest_pos'].data
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
                            bvh, bm, gp_to_target, target_to_gp, rest_pos_attr = bvh_cache[target_obj]
                            pos_target = gp_to_target @ pos_gp
                            location, normal, index, local_dist = bvh.find_nearest(pos_target)
                            
                            if location is not None:
                                # Convert surface location back to GP's space to measure true scale-agnostic distance
                                location_gp = target_to_gp @ location
                                true_distance = (pos_gp - location_gp).length
                                
                                if true_distance < best_dist:
                                    best_dist = true_distance
                                    best_match = (target_obj, location, index, true_distance, bm)
                                
                        if best_match is not None:
                            target_obj, location, index, distance, bm = best_match
                            target_idx = target_dict[target_obj]
                            
                            face = bm.faces[index]
                            v1_eval, v2_eval, v3_eval = (v.co for v in face.verts[:3])
                            
                            bvh, bm_ref, gp_to_target, target_to_gp, rest_pos_attr = bvh_cache[target_obj]
                            
                            r1 = rest_pos_attr[face.verts[0].index].vector
                            r2 = rest_pos_attr[face.verts[1].index].vector
                            r3 = rest_pos_attr[face.verts[2].index].vector
                            
                            bary_rest = mathutils.geometry.barycentric_transform(location, v1_eval, v2_eval, v3_eval, r1, r2, r3)
                            
                            rest_normal = mathutils.geometry.normal([r1, r2, r3])
                            if rest_normal.length_squared == 0:
                                rest_normal = mathutils.Vector((0, 0, 1))
                                
                            bind_rest_pos = bary_rest + (rest_normal * 0.0001)
                            
                            attr_rest_pos[i].vector = bind_rest_pos
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
                            
    # Force depsgraph update for backward compatibility (Blender 4.3 - 4.5)
    if unbound_count > 0:
        if hasattr(gp_obj.data, "update_tag"):
            gp_obj.data.update_tag()
        if hasattr(gp_obj, "update_tag"):
            gp_obj.update_tag()
            
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

class STICKYGP_UL_bound_objects(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        is_active = (context.active_object == item)
        icon = 'GREASEPENCIL' if not is_active else 'RESTRICT_SELECT_OFF'
        layout.prop(item, "name", text="", icon=icon, emboss=False)

    def filter_items(self, context, data, propname):
        objects = getattr(data, propname)
        flt_flags = []
        flt_neworder = []
        
        for obj in objects:
            if obj.type in {'GREASEPENCIL', 'GREASEPENCIL_V3'} and "Sticky_GP" in obj.modifiers:
                flt_flags.append(self.bitflag_filter_item)
            else:
                flt_flags.append(0)
                
        return flt_flags, flt_neworder

class STICKYGP_PT_panel(bpy.types.Panel):
    """Creates a Panel in the scene context of the properties editor"""
    bl_label = "Sticky GP"
    bl_idname = "STICKYGP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Sticky GP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        active_obj = context.active_object
        
        # Determine if we are in valid context
        is_valid_context = active_obj and active_obj.type in {'MESH', 'GREASEPENCIL', 'GREASEPENCIL_V3'}
        
        if not is_valid_context:
            layout.label(text="Select a Mesh or GP object", icon='INFO')
            return

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
            help_box.label(text="1. Select Mesh")
            help_box.label(text="2. Add Sticky GP Layer Target")
            help_box.label(text="3. Assign target object")
            help_box.label(text="4. Draw strokes on the surface!")

class STICKYGP_PT_bound_objects(bpy.types.Panel):
    bl_label = "Bound GP Objects"
    bl_idname = "STICKYGP_PT_bound_objects"
    bl_parent_id = "STICKYGP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    
    @classmethod
    def poll(cls, context):
        bound_gp_objects = [
            obj for obj in context.scene.objects
            if obj.type in {'GREASEPENCIL', 'GREASEPENCIL_V3'} and "Sticky_GP" in obj.modifiers
        ]
        return len(bound_gp_objects) > 0

    def draw(self, context):
        layout = self.layout
        layout.template_list(
            "STICKYGP_UL_bound_objects",
            "",
            context.scene,
            "objects",
            context.scene,
            "stickygp_bound_objects_index",
            rows=3
        )

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

def on_bound_objects_index_update(self, context):
    idx = self.stickygp_bound_objects_index
    if 0 <= idx < len(self.objects):
        obj = self.objects[idx]
        if obj.type in {'GREASEPENCIL', 'GREASEPENCIL_V3'} and "Sticky_GP" in obj.modifiers:
            if context.view_layer.objects.active != obj:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj

@bpy.app.handlers.persistent
def sync_bound_objects_index(scene, depsgraph):
    active_obj = bpy.context.active_object
    if active_obj and active_obj.type in {'GREASEPENCIL', 'GREASEPENCIL_V3'} and "Sticky_GP" in active_obj.modifiers:
        idx = scene.objects.find(active_obj.name)
        if idx != -1 and scene.stickygp_bound_objects_index != idx:
            scene.stickygp_bound_objects_index = idx

def register():
    bpy.utils.register_class(STICKYGP_LayerTarget)
    if bpy.app.background is False:
        bpy.app.timers.register(auto_rebuild_gn_on_reload, first_interval=0.1)
    
    if sync_bound_objects_index not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(sync_bound_objects_index)
        
    bpy.utils.register_class(STICKYGP_UL_bound_objects)
    bpy.utils.register_class(STICKYGP_OT_add_layer_target)
    bpy.utils.register_class(STICKYGP_OT_bind)
    bpy.utils.register_class(STICKYGP_OT_unbind)
    bpy.utils.register_class(STICKYGP_OT_fix_strokes)
    bpy.utils.register_class(STICKYGP_PT_panel)
    bpy.utils.register_class(STICKYGP_PT_bound_objects)
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
    bpy.types.Scene.stickygp_bound_objects_index = bpy.props.IntProperty(
        name="Bound Objects List Index",
        update=on_bound_objects_index_update,
        options={'SKIP_SAVE'}
    )

def unregister():
    if sync_bound_objects_index in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sync_bound_objects_index)
        
    bpy.utils.unregister_class(STICKYGP_OT_bind)
    bpy.utils.unregister_class(STICKYGP_OT_unbind)
    bpy.utils.unregister_class(STICKYGP_OT_fix_strokes)
    bpy.utils.unregister_class(STICKYGP_PT_bound_objects)
    bpy.utils.unregister_class(STICKYGP_PT_panel)
    bpy.utils.unregister_class(STICKYGP_UL_bound_objects)
    bpy.utils.unregister_class(STICKYGP_OT_add_layer_target)
    bpy.utils.unregister_class(STICKYGP_LayerTarget)
    del bpy.types.Object.sticky_gp_layer_targets
    del bpy.types.Object.sticky_gp_polycount
    
    if hasattr(bpy.types.Scene, "stickygp_bound_objects_index"):
        del bpy.types.Scene.stickygp_bound_objects_index
    
    if hasattr(bpy.types.Scene, "stickygp_show_guide"):
        del bpy.types.Scene.stickygp_show_guide

if __name__ == "__main__":
    register()




