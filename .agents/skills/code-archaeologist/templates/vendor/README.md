# Vendored third-party code

The explorer is a single self-contained file that must open from `file://` with the network
disabled (CLAUDE.md hard constraint 4). Anything it needs at runtime is vendored here and
inlined into `data/explorer.html` by `scripts/query/build_html.py`.

## force-graph.min.js

| | |
| --- | --- |
| Package | [`force-graph`](https://github.com/vasturiano/force-graph) |
| Version | **1.43.5** |
| Source | `npm pack force-graph@1.43.5` → `package/dist/force-graph.min.js` |
| Previous CDN URL | `https://cdn.jsdelivr.net/npm/force-graph@1.43.5/dist/force-graph.min.js` |
| Licence | MIT — © 2018 Vasco Asturiano |
| Size | ~159 KB |

The MIT licence text is preserved verbatim in the file's header comment, above the minified
bundle. Only that header was added; the bundle itself is byte-for-byte what npm ships.

### Updating it

```bash
npm pack force-graph@<version>
tar -xzf force-graph-<version>.tgz
# copy package/dist/force-graph.min.js here, re-apply the header comment,
# and update the version in this table
```

Take it from `npm pack` rather than a CDN so the version is pinned and the licence file comes
with it. After updating, rebuild and re-run the offline check:

```bash
python .agents/skills/code-archaeologist/scripts/archaeologist.py both --src ./sample_src
grep -c 'https\?://' .agents/skills/code-archaeologist/data/explorer.html   # must be 0
```
