# Sticky GP - Technical Blueprint

This blueprint documents the complete architecture of the Sticky GP addon for Blender (Grease Pencil v3). It is designed to allow any future developer or AI agent to understand the project architecture and logic without reading code files.

## 1. System Overview

**Sticky GP** binds Grease Pencil v3 (GPv3) strokes to deforming 3D meshes (such as animated characters).
Since GPv3 lacks a native "Surface Deform" modifier that respects individual layers, Sticky GP uses a hybrid Python + Geometry Nodes architecture:
- **Python (The Brain):** Calculates Barycentric coordinates and vertex indices via raycasting when the user clicks 'Bind'.
- **Geometry Nodes (The Muscle):** Dynamically compiled node trees that read these coordinates and shift the stroke points in real-time, matching the mesh's deformation.

## 2. Core Components

### 2.1 Data Structures & UI
Targeting data is stored on the Grease Pencil Object using a CollectionProperty named `sticky_gp_layer_targets` containing `STICKYGP_LayerTarget` items.
Each item maps a layer to a target using:
- `layer_name` (String): The GP layer name.
- `target_mode` (Enum): 'OBJECT' or 'COLLECTION' (introduced in V2.1).
- `target_mesh` (Pointer): The mesh object if 'OBJECT' mode.
- `target_collection` (Pointer): The collection if 'COLLECTION' mode.

**Global Offset Property:**
The GP Object also holds a float property `sticky_gp_global_offset`. A Python `update` callback instantly pushes changes from this slider directly into the Geometry Nodes setup, providing real-time visual feedback in the viewport.

### 2.2 Python Raycasting Engine (The Bake)
When `bind_unbound_strokes` is executed, Python bakes mathematically precise targeting data into the GP stroke points.
1. **Mesh Evaluation & BVH:** Generates a triangulated BMesh and `mathutils.bvhtree.BVHTree` for every target. Evaluates modifiers (e.g., Armatures) using `obj.evaluated_get(depsgraph)`.
2. **Matrix Conversion:** Calculates `world_to_target @ gp_to_world` to ensure precise math between local/world spaces.
3. **Proximity Raycast:** Loops through all assigned meshes (or all meshes in a collection). Compares distances using `bvh.find_nearest()` and selects the closest face.
4. **Barycentric Bake:** Saves 5 custom attributes onto the GP drawing data:
    - `bind_v1`, `bind_v2`, `bind_v3` (INT): Indices of the 3 vertices of the triangle.
    - `bind_bary` (FLOAT_VECTOR): The barycentric weights (U, V, W).
    - `bind_dist` (FLOAT): The physical offset distance.
    - `bind_target_idx` (INT): ID of the target mesh.
    - `is_bound` (BOOL): Flag to prevent double-binding.

### 2.3 Geometry Nodes Compiler & Optimizations
A Python script dynamically generates the `Sticky_GP` modifier node tree. For every assigned mesh, it writes a node block that:
1. **Sample Index (Position):** Extracts 3D coordinates for `bind_v1`, `bind_v2`, `bind_v3`.
2. **Barycentric Interpolation:** Calculates `(Pos1 * U) + (Pos2 * V) + (Pos3 * W)` to locate the deformed surface point.
3. **Smooth Normal Interpolation:** Does the same for `GeometryNodeInputNormal` from the POINT domain, inheriting smooth shading to prevent kinks at polygon edges.
4. **Offset & Global Push:** Adds the baked `bind_dist` and the user-adjustable `GlobalOffsetValue` (Math ADD node), then pushes the point away along the calculated normal.
5. **Target Switch:** Applies a Set Position node filtering by `bind_target_idx`.

**Smart GN Optimization (Target Hashing):**
Re-compiling the GN modifier can be slow. When the script builds the modifier, it joins all required mesh names into a string hash and saves it (e.g., `node_group["sticky_gp_targets"] = "MeshA,MeshB"`). On future stroke binds, the addon checks if the new stroke's required targets match the existing hash. If they do, it securely aborts the rebuild process and perfectly re-uses the existing node group.

### 2.4 Polycount Maintenance Tracker & Dev Reloads
Barycentric logic relies on constant vertex indices. If the user edits the mesh topology (e.g., extruding, subdividing), the indices shift, destroying the bind data.
- The addon caches the `sticky_gp_polycount` for every target mesh.
- The N-Panel continuously compares live polycounts to the cache.
- If a mismatch occurs, it surfaces a **"Fix Strokes (Mesh Changed)"** button.
- Clicking the fix button iterates through the timeline, unbinds the broken strokes, rebuilds the BVH trees over the new topology, and perfectly re-bakes the barycentric coordinates.

**Developer Hot-Reload Hook:**
To solve testing workflow issues, a background timer hook (`auto_rebuild_gn_on_reload`) automatically triggers 0.1 seconds after the addon's `register()` function is called (e.g., hitting F8). It bypasses all GN hashing optimizations, scans the active scene for bound GP objects, and rigorously nukes and rebuilds their GN modifiers so that Python code edits visually update in the viewport instantly.

## 3. Major Iterations & Paradigm Shifts

- **V1.0 - V1.8 (UV Map Paradigm):** Relied on generating a per-face UV map (`Sticky_GP_UVMap`). Caused floating point errors and prevented smooth normal interpolation.
- **V2.0 (Pure Barycentric Paradigm):** Deleted the UV dependency. Moved entirely to vertex indices (`bind_v1`, `v2`, `v3`) and barycentric weights, solving shading and precision issues.
- **V2.1 (Collection Binding):** Introduced the ability to assign an entire collection to a layer, enabling strokes to automatically bind across multiple overlapping meshes seamlessly.
- **V2.2 (Workflow & Offset Update):** Introduced the Global Offset slider driven via python updates, automated target hashing to skip redundant modifier recompilation, and an automated background hook for instant developer hot-reloading.
