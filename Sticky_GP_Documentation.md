# Sticky GP Addon - Complete Documentation (V2 Multi-Character)
*A comprehensive guide for users, developers, and AI Agents to understand, maintain, and extend the Sticky GP Addon.*

---

## 1. Introduction

**Sticky GP** is a Blender Addon (designed for Blender 4.3+ and the Grease Pencil v3 architecture) that perfectly sticks Grease Pencil strokes to a deforming 3D mesh.

Whether a character is bending their arm with an Armature, squashing their head with a Lattice, or speaking via Shape Keys, strokes bound by this addon will stretch, squash, and move exactly with the surface of the mesh.

### Why a Hybrid Approach?
Doing everything in **Python** (calculating vertex weights per-frame) is incredibly slow and drops playback framerates. Doing everything in **Geometry Nodes** (using `Sample Nearest` or Raycasts per-frame) causes strokes to "slip" or slide across the surface when the mesh heavily deforms because it recalculates the nearest point every frame.

**The Hybrid Solution:**
1. **Python (One-Time Execution):** When you click "Bind New Strokes", Python does the heavy lifting. It calculates exactly where the stroke is sitting on the mesh *at that exact moment* and bakes those surface coordinates directly into the stroke points as custom data.
2. **Geometry Nodes (Real-Time Execution):** A lightweight modifier simply reads those baked coordinates and instantly snaps the stroke points to the mesh surface. This evaluates perfectly in real-time without slipping.

---

## 2. Multi-Character Support (V2 Architecture)

In Version 2, the architecture was drastically refactored to seamlessly support multiple Grease Pencil objects targeting multiple unique meshes simultaneously (e.g., Character A binds to Mesh A, Character B binds to Mesh B).

### A. Object-Level Properties
Instead of storing the target mesh on the global `bpy.context.scene` (which limits you to one target file-wide), the addon stores the target directly on the Grease Pencil object itself (`bpy.types.Object.sticky_gp_target`). When you click a character's GP object, the UI reads the property assigned to that specific object.

### B. Dynamic Geometry Nodes Sandboxing
Blender 4.3 restricts Python from seamlessly injecting targets into Geometry Node modifier input sockets. Because of this, the `Object Info` node must be hardcoded inside the Node Group. 
To prevent Character A's mesh from overriding Character B's mesh, the addon dynamically generates a **unique Node Group for every single GP Object**. (e.g., `Sticky_GP_Nodes_GPencil.001`). This perfectly sandboxes the characters from one another.

---

## 3. Dedicated Custom UV Generation (The Perfect Grid)

Because the addon relies on UV mapping to track strokes on the surface, using the character's existing UV map (or relying on Blender's built-in unwrappers like Smart UV Project) proved highly problematic. Existing UV maps contain topological seams, and Catmull-Clark subdivision heavily distorts UV coordinates along these seams. If a user drew a stroke across a UV seam on a subdivided mesh, the `Sample UV Surface` node would fail mathematically, causing those stroke points to violently snap to the `(0,0,0)` origin.

To fix this, Sticky GP now features a mathematically flawless **Custom UV Generator** built directly into the addon.

### A. The "Perfect Grid" Algorithm
If the target mesh does not have a `Sticky_GP_UVMap`, the addon generates one using Python before binding.
Instead of unwrapping continuous islands (which create boundary seams that distort under subdivision), the algorithm mathematically isolates *every single polygon* in the mesh and assigns it to a tiny, non-overlapping square on a massive UV grid.

To guarantee zero geometric distortion, the algorithm projects the exact 3D aspect ratio and shape of each polygon perfectly onto the 2D plane inside its assigned grid square. Because every polygon is 100% isolated, the boundaries never stretch or shear in ways that break the sampling.

---

## 4. How the Math Works (Python Binder)

When the user clicks the "Bind" button, the Python operator `bind_unbound_strokes` runs. Here is exactly what it does under the hood:

### A. The Evaluated Mesh
It asks Blender's `depsgraph` for the **Evaluated Mesh** of the target object. This means it looks at the mesh *after* all deformers (armatures, subsurf, etc.) have been applied.

### B. BMesh Triangulation & The Orig_Idx Layer
Because `Sample UV Surface` evaluates UV coordinates on a triangulated mesh, we must mirror that logic in Python. The script creates a temporary `BMesh` and triangulates it.
However, because we need a robust fallback in Geometry Nodes (see Section 5), we **must** preserve the exact index of the original evaluated polygon. Before triangulating, the script creates a custom `orig_idx` integer layer on the BMesh faces and saves `face.index`. When the BMesh is triangulated, those custom layers are preserved, meaning the new triangles perfectly map back to their parent polygons.

### C. The BVH Tree Raycast
The script builds a `BVHTree` (Bounding Volume Hierarchy).
It loops through every single point in the newly drawn Grease Pencil stroke, converts the point's position to the mesh's local space, and asks the BVH Tree: *"What is the absolute closest face on the mesh to this point?"*

The BVH Tree returns the Location, Normal, and Distance.

### D. Barycentric Coordinates & UV Calculation
The script uses a **Barycentric Transform**. It looks at the 3 corners of the BMesh triangle, calculates the weights (percentages) of how close the hit location is to each corner, and then mixes the UV coordinates of those corners using the exact same percentages. 

### E. Saving the Data (GPv3 Attributes)
Finally, it saves this data onto the Grease Pencil point itself:
- `bind_uv` (FLOAT2): The calculated UV coordinate.
- `bind_dist` (FLOAT): The distance from the surface.
- `bind_face_idx` (INT): The original polygon index (from `orig_idx`).
- `is_bound` (BOOLEAN): A flag set to `True` so the script knows never to recalculate this point.

## 5. How the Math Works (Geometry Nodes)

Once the data is saved, the Geometry Nodes modifier takes over. It runs 60 times a second and does this:

1. **Object Info:** Grabs the target mesh geometry in `Relative` space.
2. **Sample UV Surface:** Takes the `bind_uv` stored on the stroke point, looks at the target mesh's `Sticky_GP_UVMap`, and asks: *"Where is this UV coordinate in 3D space right now?"* It samples both the Position and the Normal.

### The Bulletproof Fallback System
Due to extreme floating-point precision limitations in 32-bit vs 64-bit mathematics, if a stroke point is drawn *exactly* on the mathematical edge of a quad, Python's 64-bit barycentric calculation might produce a UV coordinate that Blender's 32-bit Geometry Nodes engine evaluates as being `0.000001` units *outside* the triangle boundary.
When this happens, `Sample UV Surface` catastrophically fails and returns a `(0,0,0)` vector, shooting the stroke point to the world origin.

To make the addon 100% mathematically bulletproof, the node tree includes a robust fallback:
1. It measures the `Length` of the `Sample UV Surface` position output.
2. If the length is less than `0.001` (meaning it failed), it switches to a `Sample Index` node.
3. The `Sample Index` node reads the `bind_face_idx` attribute we saved in Python, and instantly grabs the Position and Normal of that exact polygon's center.
4. Because polygons on character meshes are tiny, snapping a single failed stroke point to the exact center of the polygon is visually imperceptible, and because it targets the polygon's index, it perfectly deforms with the mesh without sliding!

Finally, the offset is applied along the sampled normal, and `Set Position` moves the points to their final tracking coordinates.

---

## 6. Crucial API Quirks (For Future AI / Devs)

If you modify this addon in the future, you must be aware of these Blender 4.3+ API changes that this script successfully navigated:

- **Modifier Dictionary Assignment Fails:** You can no longer do `mod["Input_1"] = obj` to assign a target object to a Geometry Node modifier via Python. The script bypasses this by creating an internal `Object Info` node inside a unique node group (as explained in Section 2B).
- **Sample UV Surface strictness:** The `Sample UV Surface` node will collapse all strokes to `(0,0,0)` if you leave the `UV Map` input empty. You **must** create a `Named Attribute` node with the string name of the UV map (e.g. `"UVMap"`) and plug it into the `UV Map` socket of the Sample nodes.
- **Data Types:** You must explicitly set `node.data_type = 'FLOAT_VECTOR'` for the Sample nodes, and use two separate ones if you want to sample Position and Normal.

---

## 6. Future Development Ideas

If an AI agent or developer wishes to extend this addon, here are highly recommended features:

- **Auto-Bind Handler:** Hook into `bpy.app.handlers.depsgraph_update_post`. Check if the user is in Draw mode and just finished a stroke. If so, automatically run `bind_unbound_strokes` silently. This would eliminate the need for clicking the sidebar button entirely.
- **Distance Falloff:** Add a Geometry Nodes parameter to gracefully fade out the binding influence if a stroke is drawn too far away from the mesh.
