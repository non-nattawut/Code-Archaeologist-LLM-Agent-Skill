# Template field taxonomy

Reference for every `{{placeholder}}` written into a generated page, so values stay
**consistent** across the Python and JS/TS extractors and both maps. The code source of
truth is `scripts/taxonomy.py` (do not hand-edit generated pages to values outside these
sets — change the taxonomy instead).

## Structure pages (`data/vault/<Entity>.md`, from `wiki_page_template.md`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `{{name}}` | any entity id | Class name, or `<Module>Module` for a file's module-level functions. |
| `{{kind}}` | `class`, `module` | What the entity is. |
| `{{layer}}` | `controller`, `service`, `repository`, `model`, `client`, `config`, `ui`, `function`, `module`, `unknown` | Architectural role (inferred from name/decorators). |
| `{{source}}` | `<area>/<path>` | Source file, prefixed with its root area (e.g. `backend/order_service.py`). |
| `{{summary}}` | free text | Docstring / description. |
| `{{bases}}`, `{{decorators}}`, `{{methods}}`, `{{references}}` | lists | `[[wikilinks]]` where the target is a known entity, else inline code. |

## Flow pages (`data/flow/<Class.method>.md`, from `build_flow.py`)

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `entity` | `Class.method` or `function` | The method/function node id. |
| `kind` | `method`, `function`, `endpoint`, `component` | `endpoint` = a route handler (flow root). |
| `layer` | same set as above | Role of the owning class/file. |
| `lang` | `py`, `js` | Source language (Python backend vs JS/TS frontend). |
| `desc_source` | `docstring`, `ai`, `auto` | Where "What it does" came from (see hybrid descriptions). |
| `source` | `<area>/<path>:<line>` | Location. |

`kind` and `layer` come from `taxonomy.py` (`KINDS`, `LAYERS`, `LAYER_RULES`). Add a new value
there once, and every extractor and template stays consistent.
