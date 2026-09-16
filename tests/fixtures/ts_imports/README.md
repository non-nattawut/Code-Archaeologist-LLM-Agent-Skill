# ts_imports — a minimal Next.js app, for import resolution

Built from a real Spring + Next.js repository whose frontend files were reported dead
although they were in use. It is pinned by `tools/check_regressions.py` r42, not by
`check_langs.py`: the shapes here are about imports and framework conventions, not
about whether a grammar loads.

| Shape | File | Expected |
| --- | --- | --- |
| named import through a tsconfig `@/` alias, called in JSX | `components/OrderSummary.tsx` -> `utils/fileSizeFormat.ts` | edge (both maps) |
| namespace import, `errors.toMessage()` | `OrderSummary.tsx` -> `lib/apiError.ts` | flow edge, and a structure edge to `ApiErrorModule` |
| `new ApiError(...)` | `OrderSummary.tsx` -> `lib/apiError.ts` | structure edge to `ApiError` |
| a name two files define, imported through the alias | `OrderSummary.tsx` -> `lib/labels.ts`, never `legacy/labels.ts` | flow edge to the imported file's `label`, structure edge to that file's `LabelsModule` -- never `legacy/` |
| anonymous `export default function () {}` | `components/Dashboard.tsx` | a node named `Dashboard`, with its calls |
| an App Router page's default export | `app/dashboard/page.tsx` | `entry: next:page`, never dead |
| a function *passed* rather than called (`action={saveAction}`, `onClick={handleSave}`) | `lib/actions.ts` | **still dead** -- a reference is not a call edge; recorded in `docs/ROADMAP_PLAN.md` |
| `<Dashboard />` in the page | `app/dashboard/page.tsx` -> `components/Dashboard.tsx` | a `renders` edge (r49) |
| `import * as api` through a barrel `export * from "./project"` | `components/ProjectActions.tsx` -> `services/api/project.ts` | edge to `approveSetdatProject` (r47) |
| an imported instance `export const projectApi = new ProjectApi()` | `ProjectActions.tsx` -> `lib/projectApi.ts` | edge to `ProjectApi.approve` |
| an object of functions: inline member, shorthand member, `refresh() {}` | `ProjectActions.tsx` -> `lib/objectApi.ts` | edges to `objectApi.reject` and `archive`; `helper` inside `refresh()` is **not** module-load code |
| a hook's untyped return value, `hooked.listProjects()` | `ProjectActions.tsx` | **no edge** -- nothing states what `hooked` is |
