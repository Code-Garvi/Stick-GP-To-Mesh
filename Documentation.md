# Sticky GP - Master Developer Guide (v2.1)

This is the comprehensive technical manual for the Sticky GP addon. It details the complete architecture required to bind Grease Pencil v3 (GPv3) strokes to deforming 3D meshes seamlessly.

---

## 1. High-Level Architecture
Blender's GPv3 architecture relies heavily on Geometry Nodes, but it currently lacks a native "Surface Deform" or "Shrinkwrap" equivalent that respects individual drawing layers and exact stroke offsets. 

**Sticky GP solves this using a hybrid approach:**
- **Python (The Brain):** Performs one-time heavy mathematical calculations (Raycasting and Barycentric coordinate generation) when the user clicks 'Bind'. It writes this mathematical data directly into the stroke points as custom attributes.
- **Geometry Nodes (The Muscle):** A custom, dynamically compiled node tree that reads the baked Python data and physically moves the stroke points in real-time during animation playback.

---

## 2. Data Structures & UI
Because py.types.GreasePencilLayer in GPv3 does not natively support PointerProperty assignments, the addon stores targeting data on the Grease Pencil Object itself.

It uses a CollectionProperty named sticky_gp_layer_targets containing STICKYGP_LayerTarget items. 
Each item acts as a dictionary mapping a specific layer to its target:
- layer_name (String): The name of the GP layer.
- 	arget_mode (Enum): Either 'OBJECT' or 'COLLECTION'.
- 	arget_mesh (Pointer): Used if mode is 'OBJECT'.
- 	arget_collection (Pointer): Used if mode is 'COLLECTION'.

---

## 3. The Binding Engine (Python Raycasting)
When ind_unbound_strokes is called, Python executes the core binding logic:

### A. Mesh Evaluation & BVH Trees
Python scans the targets and generates a mathutils.bvhtree.BVHTree for every valid mesh. Crucially, it evaluates the mesh using valuated_get(depsgraph) to ensure modifiers (like Armatures) are accounted for, and converts it to a triangulated BMesh.

### B. Matrix Space Conversion
Stroke points exist in Grease Pencil Local Space. The Target Mesh exists in its own Local Space. Python calculates a transformation matrix (world_to_target @ gp_to_world) to accurately project the GP points into the Target's mathematical space before raycasting.

### C. Multi-Target Proximity Raycast
For every point on the stroke, Python loops through all assigned meshes (if a Collection is used, it loops through every mesh inside it). It calls vh.find_nearest() on all of them, compares the distance, and selects the absolute closest mesh surface.

### D. Pure Barycentric Baking
Once the exact face is found, Python calculates the barycentric coordinates. It saves **5 custom attributes** onto the GP drawing data:
1. ind_v1, ind_v2, ind_v3 (INT): The 3 physical Vertex Indices of the triangle.
2. ind_bary (FLOAT_VECTOR): The mathematical weights (U, V, W) representing where the point sits between those 3 vertices.
3. ind_dist (FLOAT): The physical offset distance the point is hovering above the mesh.
4. ind_target_idx (INT): A unique ID marking *which* mesh in the scene it bound to.
5. is_bound (BOOL): A flag to prevent re-binding the same point twice.

---

## 4. The Geometry Nodes Compiler
Python dynamically generates the Sticky_GP Geometry Nodes modifier. It compiles a "Router" based on the number of targets.

For every assigned target mesh in the scene, Python writes a block of nodes that does the following:
1. **Sample Index (Position):** It pulls the exact 3D coordinates of ind_v1, ind_v2, and ind_v3 from the target mesh.
2. **Barycentric Interpolation:** It uses Vector Math nodes to calculate: (Pos1 * U) + (Pos2 * V) + (Pos3 * W). This finds the exact deformed location on the skin.
3. **Smooth Normal Interpolation:** It does the exact same calculation for GeometryNodeInputNormal. Because it samples normals from the POINT domain, it inherits the mesh's smooth shading, perfectly preventing jagged "kinks" when a stroke crosses a polygon edge.
4. **Offset:** It pushes the point away from the surface by ind_dist along the interpolated Normal.
5. **The Switch:** A Set Position node applies this math *only* if the point's ind_target_idx matches this specific mesh's ID. 

---

## 5. The Maintenance Engine (Polycount Tracker)
The Barycentric system relies on **Vertex Indices**. If a user deforms the mesh (posing an arm), vertex indices remain identical. However, if a user *edits* the mesh topology (adding edge loops, deleting faces, subdividing), Blender scrambles the vertex indices, which immediately breaks the ind_v1 data.

To protect against this, the addon caches the sticky_gp_polycount for every target mesh.
During the N-Panel draw loop, it continuously checks the live polygon count of all assigned meshes. If it detects a mismatch (the user edited the topology), it surfaces a red **"Fix Strokes (Mesh Changed)"** button.

When clicked, this operator physically moves the timeline playhead through every keyframe, unbinds the broken strokes, rebuilds the BVH trees over the new topology, and re-bakes the new vertex indices and barycentric weights flawlessly.
