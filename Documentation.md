# Sticky GP V2.0 - Technical Documentation

## The Pure Barycentric Paradigm

In versions 1.0 -> 1.8, Sticky GP relied on generating a shattered, per-face UV map (Sticky_GP_UVMap) on the target meshes. While this worked, it caused floating point precision errors at polygon boundaries and prevented smooth normal interpolation, leading to "jagged" strokes when the GP line had a distance offset from the mesh.

### Version 2.0 deletes the UV dependency entirely.

Instead of translating 3D space into 2D UV space and back, the addon now operates strictly using **Vertex Indices** and **Barycentric Weights**.

### 1. Python Binding Data (The "Bake")
When the user clicks 'Bind Visible Strokes', the Python script raycasts against the target mesh to find the exact triangle the stroke point is hovering over. 
Instead of a UV coordinate, Python saves 4 attributes into the GP Point Cloud:
- ind_v1 (INT): The index of the triangle's 1st vertex.
- ind_v2 (INT): The index of the triangle's 2nd vertex.
- ind_v3 (INT): The index of the triangle's 3rd vertex.
- ind_bary (FLOAT_VECTOR): The 3 barycentric weights (u, v, w) that describe exactly where the point is located between those 3 vertices.
- ind_dist (FLOAT): The distance the point is hovering above the mesh.

### 2. Geometry Nodes Interpolation
The dynamically generated Geometry Nodes modifier no longer uses Sample UV Surface. 
Instead, it uses Sample Index (set to the POINT domain) to pull the exact Position and Normal data of ind_v1, ind_v2, and ind_v3 directly from the deforming mesh geometry.

It then does the math in real-time:
Final Position = (Pos1 * U) + (Pos2 * V) + (Pos3 * W)
Final Normal = Normalize( (Norm1 * U) + (Norm2 * V) + (Norm3 * W) )

Because it samples Normals from the POINT domain, it inherits Blender's native "Smooth Shading", perfectly smoothing out the stroke's offset across hard polygon edges.
