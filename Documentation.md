# Sticky GP V8 - Technical Documentation

## Core Architecture
Sticky GP V8 introduces **Per-Layer Multi-Mesh Targeting**. Previously, the entire Grease Pencil object was stuck to a single mesh. In V8, each individual Grease Pencil Layer can be assigned to completely different mesh objects in the scene.

### 1. Data Storage (The Property Issue)
In Blender 4.3+ (GPv3 architecture), GreasePencilLayer objects do not natively support arbitrary custom ID properties like PointerProperty. 
To solve this, the target meshes are stored on the Grease Pencil Object itself using a CollectionProperty of type STICKYGP_LayerTarget. 
This collection acts as a dictionary mapping layer_name -> 	arget_mesh.

### 2. The Geometry Nodes Router (GN Compilation)
Geometry Nodes for GPv3 merges all layers into a single Point Cloud and currently lacks a native 'layer name' attribute.
Because strokes from different layers need to snap to different meshes, the Python script acts as a compiler:
1. Python scans all layers and gathers all unique target meshes.
2. It assigns an integer index (1, 2, 3...) to each unique mesh.
3. It dynamically generates a complex Geometry Nodes modifier (create_sticky_gn_modifier).
4. This node tree contains an Object Info node and Raycast/Sample logic for **every single target mesh**.
5. The nodes use a custom point attribute ind_target_idx to switch which mesh the point should snap to using consecutive Set Position nodes gated by a Selection boolean (ind_target_idx == assigned_idx).

### 3. Raycast Binding
When the user clicks "Bind Visible Strokes":
- The script checks the scene's current frame and limits the bind logic to only the drawings that are currently visible at the playhead.
- It iterates through each layer, grabbing its specific target mesh.
- It calculates the barycentric coordinates (UV + Distance) against that specific mesh using a BVHTree.
- Crucially, it bakes the layer's assigned ind_target_idx integer into the GP points so Geometry Nodes knows where to route them.

### 4. Smart Polycount Tracking & Global Fixing
The addon stores sticky_gp_polycount on every assigned target mesh.
The N-Panel actively monitors all assigned meshes. If *any* mesh's polygon count changes (e.g. topology edits, subdivisions), a global Fix Strokes (Mesh Changed) button appears.
Clicking this alters the scene frame iteratively to visit every single keyframe across the timeline, unbinds the points, recalculates the barycentric coordinates against the new topology, and rebinds them perfectly in place.
