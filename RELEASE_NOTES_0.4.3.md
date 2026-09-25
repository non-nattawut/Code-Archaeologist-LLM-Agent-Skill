# Release Notes — Version 0.4.3

**Code Archaeologist LLM Agent Skill**  
*Deterministic, Zero-RAG Codebase Documentation Engine & Architecture Explorer*

---

## Overview

Version 0.4.3 resolves a critical import binding bug in JavaScript / TypeScript extraction where default-exported classes (`export default class X` and `class X {}; export default X;`) were not recorded in the file's default export metadata. This caused cross-file call resolution to drop method invocations as "unresolved" whenever another file in the graph (such as a backend service) defined a method of the same name.

---

## Bug Fixes & Improvements

### 1. Default and Named Class Export Extraction (`js_ts_extract.py`)
- **Class Declaration Top-Level Extraction**: In `_extract_tree()`, the `class_declaration` and `abstract_class_declaration` branch now checks `exported` and `default`. When `exported` is true, the class name is added to `out["exports"]["names"]`; when `default` is true, it is set in `out["exports"]["default"]`, matching the pattern used by `function_declaration`.
- **Default Resolution in `_finish()`**: In `_finish()`, added traversal over `out["classes"]` to set `out["default"] = cls["name"]` whenever a class name matches `exports["default"]`. This ensures both direct default exports (`export default class HouseService`) and deferred default exports (`class HouseService {}; export default HouseService;`) accurately expose their default export name to consumers.
- **Import Binding & Shared Method Disambiguation (`build_flow.py`)**: `build_flow.py` relies on `defaults[src_rel]` when binding default imports (`import HouseService from "@/services/houseService"`). By properly populating `defaults`, calls through instances of default-imported classes (e.g. `houseService.save()`) correctly resolve to the frontend method node even when backend classes (e.g. Spring `HouseService.save`) share the same method name.

---

## Verification & Automated Testing

- **Real-World Monorepo Verification (`RoadBedProject`)**:
  - `extract_js_files` returns `default: "HouseService"` and `default: "UserService"`.
  - In `Create` (`src/main/road-bed-frontend/pages/create.js`), the call to `houseService.save(formData)` now successfully creates an edge to `...houseService.HouseService.save`, and `save` is removed from the unresolved call list.
  - Across the repository, 5 previously unresolved method calls resolved successfully (`Create -> HouseService.save`, `Payment -> HouseService.reserveHouse`, `HouseDetail -> UserService.addHouseToFavorites`, `HouseDetail -> UserService.removeHouseFromFavorites`, `Profile -> TenantService.updateProfilePicture`), with 0 dropped/regressed edges.
- **Regression Suite**:
  - Added `r86_default_exported_class` in `tools/check_regressions.py`.
  - `python tools/check_regressions.py`: **86/86 regression cases pass**.
  - `python tools/check_graph.py`: **34/34 flow checks, 34/34 structure checks pass**.
  - `python tools/check_langs.py`: **21/21 languages pass**.
  - `python tools/check_docs.py`: **OK**.
  - `python tools/check_py_oracle.py`: **OK**.
