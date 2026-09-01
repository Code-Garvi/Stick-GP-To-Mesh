# Sticky GP - Complete Changelog

## V2.2.1
- **[MODIFIED]** Replaced the bulky UI instructions block in the N-Panel with a clean, collapsible "Quick Guide" toggle, saving permanent vertical screen space.
- **[MODIFIED]** Expanded the quick guide to include instructions on the "Unbind" feature.
- **[FIX]** Resolved a strict UTF-8 Unicode decoding error that caused crashes when loading the addon if certain system encoding defaults (like `cp1252`) wrote invalid bullet point characters.

## V2.2 (Workflow & UX Update)
- **[NEW]** Global Offset Slider: Added a slider to the N-Panel (ranging from -1 to 1) that pushes all bound strokes outwards or inwards globally to prevent clipping with the target mesh. The Geometry Nodes math was dynamically updated to support this.
- **[NEW]** Real-Time Viewport Feedback: Connected a python `update_offset` callback hook that instantly passes the N-Panel UI slider values into the Geometry Nodes modifier for real-time visual tweaking.
- **[NEW]** Developer Auto-Reload Hook: Added a timed background hook (`auto_rebuild_gn_on_reload`) that executes 0.1 seconds after the addon registers (F8 reload). It safely nukes and completely rebuilds existing GN modifiers in your open scene so python edits are visible instantly.
- **[OPT]** Smart Node Optimization: The addon now generates a string hash of the targeted meshes required by the strokes. When binding or unbinding strokes, if the required meshes match the existing modifier's hash, it safely skips recompilation to save performance.
- **[FIX]** Polycount Tracker Crash: Fixed a `NameError` crash when clicking "Fix Strokes" on modified meshes. Updated the legacy function call to correctly handle multi-object collection lists instead of singular objects.

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
