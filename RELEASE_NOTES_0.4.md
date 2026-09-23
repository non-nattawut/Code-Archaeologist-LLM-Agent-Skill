# Release Notes — Version 0.4.0

**Code Archaeologist LLM Agent Skill**  
*Deterministic, Zero-RAG Codebase Documentation Engine & Architecture Explorer*

---

## Highlights of 0.4.0

Version 0.4.0 represents a major evolutionary leap for the Code Archaeologist Explorer, introducing an untangled flowchart engine, intelligent component grouping with service containers, multi-node group manipulation, and an extensive suite of technical architecture guides.

---

## 1. Flowchart Untangling Engine & Visual Redesign

- **Sugiyama Two-Way Iterative Barycentric Sweeps**:
  - Replaced single-pass alphabetical ordering with 6 alternating forward and backward sweeps across columns.
  - Nodes in each column sort by the average vertical position ($Y$) of their connected callers, callees, and peers, aligning callers horizontally with callees and reducing diagonal crossings to near zero.
- **Smooth Cubic Bezier Edge Routing**:
  - Replaced rigid 90° orthogonal elbows with graceful cubic Bezier splines (`bezierCurveTo`).
  - **Same-column calls**: Clean lateral C-curve brackets in the inter-column gap that never detour under the whole diagram.
  - **Adjacent backward calls**: Direct smooth curves connecting implementation left edges to declaration right edges across the gap.
  - **Multi-column backward loops**: Arched bypass lanes with dedicated row clearance.
- **Two-Tone Card Typography & Styling**:
  - Two-tone label hierarchy: Class prefix in 10px muted slate (`#8b98ad`), method name in bold 11px bright text (`#e6e9ee`).
  - Card dimensions updated to `FC = { w: 192, h: 36, row: 54, col: 275 }` (18px vertical breathing room, 83px horizontal gap).
  - Subtle dark card tone (`#121721`) with 6px border radius.
- **Canvas Swimlane Guides & Column Headers**:
  - Rendered in `onRenderFramePre`: Subtle dashed vertical dividers between architectural tiers.
  - Tier headers positioned cleanly above columns.

---

## 2. Component Grouping & Service Containers

- **Smart Column Assignment (Eliminating Artificial Column Splits)**:
  - **Interface Contracts**: Inheritance links (`implements`, `extends`, `overrides`) no longer push implementations into artificial new columns. Interfaces and their implementations share the same tier stage, eliminating awkward backward loop jumps.
  - **Internal Helpers**: Calls within the same class (e.g. `ImageUploadServiceImpl.uploadImage` &rarr; `convertMultipartFileToFile`) remain inside the parent service container rather than stretching the chart horizontally into redundant columns.
  - **Frontend / UI Flow**: Client components and fetch helpers remain together in the `FRONTEND / UI TIER`.
  - **Cross-Service Calls**: Legitimate cross-service/cross-tier calls cleanly advance to subsequent columns.
- **Class & Service Containers (`drawFlowContainers`)**:
  - Encloses methods of the same class/component inside a unified card (`rgba(16, 22, 32, 0.55)`).
  - Container header displays the class/service name.
  - Pure interface contract groups are styled with a dashed gold border (`rgba(224, 163, 62, 0.5)`) and `⟨Interface⟩` badge.
  - Containers highlight reactively when any contained method is selected.
- **Distinct Domain-Specific Column Headers (`drawFlowLanes`)**:
  - Eliminates duplicate consecutive headers (`SERVICES / LOGIC` &times; 4).
  - Columns dynamically detect their dominant service/class and display domain-specific titles: `SERVICES (Auth)`, `SERVICES (Token)`, `SERVICES (Tenant)`, `SERVICES (ImageUpload)`.
  - UI columns display `FRONTEND / UI TIER`.
- **Contiguous Class Ordering**:
  - Sugiyama sweeps order nodes by class barycenters before individual method barycenters.
  - Methods of the same class stay strictly contiguous as a cohesive block, with 0.5-row vertical spacing automatically maintained between different class containers to prevent overlap.

---

## 3. Multi-Node Selection & Group Movement

- **Multi-Selection**:
  - `Shift`+Click or `Ctrl`/`Cmd`+Click to select or toggle multiple nodes into a group selection.
  - **Marquee Drag Selection**: Hold `Shift` and drag across the canvas background to draw a selection rectangle that selects all enclosed nodes.
- **Synchronized Group Drag**:
  - Dragging any selected node moves all selected nodes simultaneously with identical translation deltas, preserving their relative spatial layout.
- **Status Bar Integration**:
  - Displays `N nodes selected (drag to move group)` and highlights all selected cards.

---

## 4. Health Breakdown & Navigation

- **Clickable Health Deductions**:
  - Health degradation badges in the left rail are now interactive with smooth scrolling and highlight pulse animations linking directly to the specific smell group in the Patterns tab.
- **Health Calculation Breakdown**:
  - Added full health score formula and calculation breakdown to the legend.
- **Graded Check Prioritization (r84)**:
  - All graded analysis checks (cycles, layer violations, hubs, wrong-way dependencies, god objects) are displayed before non-graded checks across reports and the explorer UI.

---

## 5. View Unification & Explorer Optimizations

- **Canvas View Unification**:
  - Unified selection and freeze states across all canvas views (Flowchart, Graph, Tree, Cluster, Bundle).
  - Tab buttons reordered to clearly distinguish interactive canvas graph views from tabular/tree document views (Treemap, Matrix).
- **Code Archaeologist Explorer Optimization**:
  - Streamlined `.agents/skills/code-archaeologist-explorer/SKILL.md` to eliminate agent overthinking and minimize prompt/reasoning token usage.
  - Chained `archaeologist.py both && ... report` execution.

---

## 6. Comprehensive Technical Documentation

- **32-File Architecture Reading Checklist**:
  - English and Thai interactive architecture guides with complete algorithms, mathematical formulas, and input/output specifications.
  - Side-by-side interactive Data Flow vs Calling Flow visualization.
- **Technical Guides for Review Tools**:
  - Added dedicated guides in `docs/` for `analyze.py`, `scan_security.py`, `git_insights.py`, `metrics.py`, `debt.py`, `tests_map.py`, `duplicates.py`, `brief.py`, and query tools.
- **AGENTS.md Standard**:
  - Standardized agent instructions under `AGENTS.md` following the latest agent skill specifications.

---

## Verification & Test Results

- **Automated Regression Suite**: 84/84 regression cases hold (`python tools/check_regressions.py`).
- **Graph Integrity Checks**: 34/34 checks pass on Flow and Structure maps (`python tools/check_graph.py`).
- **Docs Mechanical Verification**: `check_docs: OK` (`python tools/check_docs.py`).
- **Language Fixture Coverage**: 21/21 languages OK (`python tools/check_langs.py`).
- **Self-Contained Standalone Artifact**: `data/explorer.html` regenerated and fully offline-capable with zero external runtime dependencies.
