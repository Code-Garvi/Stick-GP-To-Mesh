# Sticky GP Addon - Complete Documentation
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

## 2. How the Math Works (Python Binder)

When the user clicks the "Bind" button, the Python operator `bind_unbound_strokes` runs. Here is exactly what it does under the hood:

### A. The Evaluated Mesh
It asks Blender's `depsgraph` for the **Evaluated Mesh** of the target object. This means it looks at the mesh *after* all deformers (armatures, subsurf, etc.) have been applied.

### B. BMesh Triangulation
Because 3D models are often made of Quads (4-sided polygons), mathematical UV projection is dangerous. If a Quad bends, it's no longer flat. To fix this, the script creates a temporary `BMesh` and **triangulates** it. Triangles are always perfectly flat, which guarantees flawless mathematical projection later.

### C. The BVH Tree Raycast
The script builds a `BVHTree` (Bounding Volume Hierarchy), which is an extremely fast search algorithm.
It loops through every single point in the newly drawn Grease Pencil stroke, converts the point's position to the mesh's local space, and asks the BVH Tree: *"What is the absolute closest face on the mesh to this point?"*

The BVH Tree returns:
1. **Location:** The exact 3D coordinate on the face.
2. **Normal:** The direction the face is pointing.
3. **Distance:** How far the stroke point is from the surface.

### D. Barycentric Coordinates & UV Calculation
Knowing the 3D location on a triangle isn't enough; we need to know its **UV Coordinate** so Geometry Nodes can find it later.
The script uses a **Barycentric Transform**. It looks at the 3 corners of the triangle, calculates the weights (percentages) of how close the hit location is to each corner, and then mixes the UV coordinates of those corners using the exact same percentages. 

### E. Saving the Data (GPv3 Attributes)
Finally, it saves this data onto the Grease Pencil point itself:
- `bind_uv` (FLOAT2): The calculated UV coordinate.
- `bind_dist` (FLOAT): The distance from the surface.
- `is_bound` (BOOLEAN): A flag set to `True` so the script knows never to recalculate this point again.

*(Note for devs: In GPv3, these attributes must be written to `layer.frames[i].drawing.attributes`, NOT the root GP object).*

---

## 3. How the Math Works (Geometry Nodes)

Once the data is saved, the Geometry Nodes modifier (`Sticky_GP_Nodes`) takes over. It runs 60 times a second and does this:

1. **Object Info:** Grabs the target mesh geometry in `Relative` space.
2. **Sample UV Surface (Position):** Takes the `bind_uv` stored on the stroke point, looks at the target mesh's `UVMap`, and asks: *"Where is this UV coordinate in 3D space right now?"* It outputs the current 3D position.
3. **Sample UV Surface (Normal):** Does the exact same thing, but asks for the surface Normal (direction) at that UV coordinate.
4. **Offset:** Multiplies the Normal by the `bind_dist` to float the point perfectly above the mesh just like when it was drawn.
5. **Set Position:** Adds the offset to the surface position, and moves the Grease Pencil point there. (It only does this if `is_bound` is True).

---

## 4. Crucial API Quirks (For Future AI / Devs)

If you modify this addon in the future, you must be aware of these Blender 4.3+ API changes that this script successfully navigated:

- **Modifier Dictionary Assignment Fails:** You can no longer do `mod["Input_1"] = obj` to assign a target object to a Geometry Node modifier via Python. The script bypasses this by creating an internal `Object Info` node and setting `node.inputs['Object'].default_value = target_obj`.
- **Sample UV Surface strictness:** The `Sample UV Surface` node will collapse all strokes to `(0,0,0)` if you leave the `UV Map` input empty. You **must** create a `Named Attribute` node with the string name of the UV map (e.g. `"UVMap"`) and plug it into the `UV Map` socket of the Sample nodes.
- **Data Types:** You must explicitly set `node.data_type = 'FLOAT_VECTOR'` for the Sample nodes, and use two separate ones if you want to sample Position and Normal.

---

## 5. Future Development Ideas

If an AI agent or developer wishes to extend this addon, here are highly recommended features:

- **Auto-Bind Handler:** Hook into `bpy.app.handlers.depsgraph_update_post`. Check if the user is in Draw mode and just finished a stroke. If so, automatically run `bind_unbound_strokes` silently. This would eliminate the need for clicking the sidebar button entirely.
- **Layer-Specific Targets:** Add UI to allow the user to select different target meshes for different Grease Pencil layers (e.g., sticking a tattoo layer to the skin, and a zipper layer to the jacket). 
- **Distance Falloff:** Add a Geometry Nodes parameter to gracefully fade out the binding influence if a stroke is drawn too far away from the mesh.
