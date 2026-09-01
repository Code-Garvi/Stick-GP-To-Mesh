# Sticky GP - Complete Changelog

## V2.1
- **[NEW]** Multi-Object Collection Binding: Assign entire Collections to a layer. The addon automatically evaluates every mesh and binds strokes across overlapping geometry seamlessly.
- **[NEW]** N-Panel UI Mode Toggle: Layers feature a dropdown to switch between 'Object' mode and 'Collection' mode, dynamically changing the picker slot.
- **[MODIFIED]** Raycast Binding Engine: The core python loop supports multi-target evaluation per point, comparing distances against all meshes and assigning the point to the absolute closest surface.
- **[MODIFIED]** Polycount Tracker: Iterates over all meshes inside targeted collections, triggering auto-fix prompts if any mesh in the collection has its topology edited.

## V2.0_nouv (Pure Barycentric Update)
- **[NEW]** Pure Barycentric Paradigm: Replaced the UV-based system entirely with a Vertex Index + Barycentric weight system.
- **[REMOVED]** Removed dependency on `Sticky_GP_UVMap`.
- **[MODIFIED]** Geometry Nodes Interpolation: Replaced "Sample UV Surface" with "Sample Index" in the POINT domain.
- **[FIX]** Smooth Normal Interpolation now inherits Blender's native smooth shading, perfectly smoothing out the stroke's offset across hard polygon edges.

## V1.8
- **[MODIFIED]** Overhauled internal tracking and maintenance routines.
- **[NEW]** Introduced initial documentation (Documentation.md) and changelog tracking.

## V1.7
- **[FIX]** Minor bugfixes and optimizations for the UV map generation pipeline.

## V1.6
- **[NEW]** Added Changelog support natively to the development folder.
- **[MODIFIED]** Refined the UV mapping process for slightly better precision.

## V1.5
- **[REMOVED]** Removed extraneous test blend files (Auto_Bind_Test.blend).
- **[MODIFIED]** Cleanup of the core codebase to streamline the geometry nodes compilation.

## V1.2
- **[NEW]** Created `Auto_Bind_Test.blend` to validate the binding procedures.
- **[MODIFIED]** Improved the Polycount Tracker's ability to prompt users when mesh topology is modified.

## V1.1
- **[INITIAL]** Initial release of Sticky GP Addon. 
- **[INITIAL]** Python Binding Engine (UV Map based) and dynamically compiled Geometry Nodes modifier.
- **[INITIAL]** `Sticky_GP_Documentation.md` created to track development.
