# Release Notes — Version 0.4.2

**Code Archaeologist LLM Agent Skill**  
*Deterministic, Zero-RAG Codebase Documentation Engine & Architecture Explorer*

---

## Overview

Version 0.4.2 is a major functionality and stability release introducing **automated cross-stack frontend-to-backend HTTP bridge resolution** — eliminating isolated/standalone controllers and connecting frontend API service calls directly to backend route handlers across mixed codebases (e.g. Next.js/React + Spring Boot/FastAPI/Express). It also incorporates canvas interaction fixes across Graph, Tree, and Bundle views with dynamic D3 physics unpinning.

---

## Key Features & Improvements

### 1. Cross-Stack Frontend-to-Backend HTTP Edge Extraction & Controller Linking
- **Member Expression Receiver Extraction**: In `js_ts_extract.py`, `_callee_parts` previously discarded member expression callees (`this.axiosInstance.post(...)`, `api.client.get(...)`). It now extracts property names (`axiosInstance`, `client`) so instance-based HTTP client calls are accurately recognized.
- **Universal HTTP Client Detection**: Added recognition for any client variable containing `"axios"` (e.g. `axiosInstance`, `customAxios`), standard HTTP client identifiers (`"api"`, `"client"`, `"http"`, `"httpclient"`, `"request"`, `"fetcher"`, `"ky"`, `"superagent"`, `"instance"`), and client/service suffixes. Direct calls (`axios(url)`, `axios({ url, method })`, `axios.request(...)`) and Nuxt `$fetch` / `window.fetch` are now fully extracted.
- **Class Fields & Binary Concatenation**: Class-level string fields (`apiUrl = "tenants/"`, `apiUrl = "http://localhost:8080/auth/"`, `static BASE = "..."`) and constructor assignments (`this.apiUrl = "..."`) are now resolved. Added support for binary concatenation chains (`this.apiUrl + "updateProfilePic/" + userId`) and dynamic parameter synthesis (`:userId`, `:email`, `:param`). Fixed tree-sitter JavaScript `field_definition` which uses `property:` rather than `name:`.
- **URL Scheme & Host Normalization**: In `build_flow.py`, `_norm_path` now strips URL scheme and host prefixes (`^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//[^/]*`), seamlessly matching full frontend URLs (`http://localhost:8080/auth/register`) against backend route definitions (`/auth/register`).
- **Multi-Language Backend Route Extraction**: Extended Spring controller route detection in `langs_extract.py` from `java` only to `SPRING_ROUTE_LANGS = {"java", "groovy", "kotlin", "scala"}`. Added JAX-RS / Jakarta REST HTTP verb annotations (`@GET`, `@POST`, `@PUT`, `@DELETE`, `@PATCH`, `@Path`), eliminating standalone controller isolation across mixed stacks.

### 2. Canvas Physics & Node Interaction Restoration
- **Critical Render Loop Crash Fix**: Restored `const issue = worstIssue(node.id);` inside `drawNode` in `templates/viewer.html`. Previously, switching from Flowchart to Graph, Tree, Cluster, or Bundle views threw an unhandled `ReferenceError`, halting D3 physics ticks and freezing canvas pointer hit-testing.
- **Dynamic Drag Handling & Physics Unpinning**: Dragging nodes in Graph and Tree views now unpins them upon drag release (`fx = undefined`, `fy = undefined`) and reheats the simulation via `Graph.d3ReheatSimulation()`, allowing nodes to float and respond to physics naturally. In Flowchart, Bundle, and Cluster views, manual placements remain pinned.
- **Strict Coordinate Unpinning**: Replaced `n.fx = null; n.fy = null;` with `undefined` across `setView()`, `layoutBundle()`, `layoutCluster()`, and `layoutFlowchart()` to align with force-graph's strict `void 0 === r.fx` check.
- **Generous Pointer & Selection Hit Area**: Expanded circular hit radius from 5px to the node's full visual radius with padding (`r + 4`) and added the node's label bounding box to the hit area for effortless node selection.
- **Background Marquee Detection**: Fixed the canvas `pointerdown` listener to check `!hovered` instead of `!Graph.hoverObj`.

---

## Verification & Automated Testing

- **Real-World Monorepo Verification (`RoadBedProject`)**:
  - Cross-stack HTTP edges jumped from 6 to 24, directly connecting all frontend services (`AuthService`, `TenantService`, `HouseService`, `UserService`) and Next.js page requests (`[category].js`, `[city].js`, `[houseId].js`, `[userId].js`, `[...nextauth].js`) to backend Spring controllers (`AuthController`, `TenantController`, `HouseController`, `UserController`).
- **Headless Browser CDP Verification**:
  - Automated tests via Microsoft Edge DevTools Protocol across Flowchart, Graph, Tree, and Bundle views confirmed 0 runtime exceptions.
  - Verified active velocities (`vx`, `vy`) on force simulation reheat and clean unpinning on drag release.
- **Regression Suite**:
  - `python tools/check_regressions.py`: **85/85 regression cases pass** (including new `r85_cross_stack_http_calls`).
  - `python tools/check_graph.py`: **34/34 checks pass**.
  - `python tools/check_docs.py`: **OK**.
