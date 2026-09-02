#!/usr/bin/env python3
"""build_html.py — Generate a standalone, shareable HTML graph viewer.

Reads data/graph.json and writes a single self-contained HTML file with the
graph data embedded inline (no server required). Open it directly via file://,
commit it, or email it. `force-graph` is loaded from a CDN.

Re-run any time to regenerate/update the file after rebuilding the graph.

Zero external dependencies. Python 3.10+.

    python build_html.py                 # -> data/graph.html
    python build_html.py --out foo.html  # custom output path
    python build_html.py --title "My Service Map"
"""
from __future__ import annotations

import argparse
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "graph.html")

# The graph JSON is injected at the __GRAPH_DATA__ marker; the title at __TITLE__.
# Everything else is static and safe to customize by hand after generation.
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>__TITLE__</title>
<style>
  html, body { margin: 0; height: 100%; background: #0d1117; color: #c9d1d9;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  #bar { position: fixed; top: 0; left: 0; right: 0; z-index: 10; padding: 8px 12px;
    background: rgba(13,17,23,.85); border-bottom: 1px solid #21262d; display: flex;
    gap: 8px; align-items: center; flex-wrap: wrap; }
  #bar input { background: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 6px; padding: 6px 10px; width: 260px; outline: none; }
  #bar .hint { color: #8b949e; font-size: 12px; }
  #legend { display: flex; gap: 10px; font-size: 12px; margin-left: auto; }
  #legend span { display: inline-flex; align-items: center; gap: 4px; }
  #legend i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  #graph { position: fixed; inset: 0; }
</style>
<script src="https://cdn.jsdelivr.net/npm/force-graph@1.43.5/dist/force-graph.min.js"></script>
</head>
<body>
<div id="bar">
  <strong>__TITLE__</strong>
  <input id="q" placeholder="search node… (Enter to focus)" autocomplete="off" />
  <span class="hint" id="stats"></span>
  <span id="legend"></span>
</div>
<div id="graph"></div>
<script>
// ---- Embedded graph data (edit freely, or regenerate with build_html.py) ----
const GRAPH = __GRAPH_DATA__;

// ---- Customize colors per architectural layer here ----
const LAYER_COLORS = {
  controller: "#f778ba", service: "#58a6ff", repository: "#3fb950",
  model: "#d29922", config: "#a371f7", client: "#39c5cf", unknown: "#8b949e"
};
let HL = null;

document.getElementById("stats").textContent =
  GRAPH.nodes.length + " nodes · " + GRAPH.edges.length + " edges";

// Build legend from layers actually present.
const legend = document.getElementById("legend");
[...new Set(GRAPH.nodes.map(n => n.layer))].forEach(layer => {
  const s = document.createElement("span");
  s.innerHTML = '<i style="background:' + (LAYER_COLORS[layer] || LAYER_COLORS.unknown) + '"></i>' + layer;
  legend.appendChild(s);
});

const links = GRAPH.edges.map(e => ({ source: e.source, target: e.target, type: e.type }));
const Graph = ForceGraph()(document.getElementById("graph"))
  .backgroundColor("#0d1117")
  .graphData({ nodes: GRAPH.nodes.map(n => ({ ...n })), links })
  .nodeId("id")
  .nodeRelSize(5)
  .linkColor(() => "rgba(139,148,158,.35)")
  .linkDirectionalArrowLength(4)
  .linkDirectionalArrowRelPos(1)
  .nodeCanvasObject((node, ctx, scale) => {
    const r = 5;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = (HL && HL === node.id) ? "#ffffff"
      : (LAYER_COLORS[node.layer] || LAYER_COLORS.unknown);
    ctx.fill();
    const fontSize = Math.max(3, 12 / scale);
    ctx.font = fontSize + "px monospace";
    ctx.fillStyle = "#c9d1d9";
    ctx.fillText(node.id, node.x + r + 1, node.y + 3);
  })
  .onNodeClick(node => {
    Graph.centerAt(node.x, node.y, 500);
    Graph.zoom(4, 500);
    HL = node.id;
  });

function focus(term) {
  term = (term || "").trim().toLowerCase();
  if (!term) { HL = null; return; }
  const hit = Graph.graphData().nodes.find(n => n.id.toLowerCase().includes(term));
  if (hit) { HL = hit.id; Graph.centerAt(hit.x, hit.y, 500); Graph.zoom(4, 500); }
}
const q = document.getElementById("q");
q.addEventListener("keydown", e => { if (e.key === "Enter") focus(q.value); });
q.addEventListener("input", () => { if (!q.value) HL = null; });
</script>
</body>
</html>
"""


def build(graph_path: str, out_path: str, title: str) -> int:
    if os.path.isfile(graph_path):
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    else:
        print(f"warning: {graph_path} not found; embedding an empty graph.")
        graph = {"nodes": [], "edges": []}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    html = TEMPLATE
    html = html.replace("__TITLE__", title)
    # json.dumps is HTML-safe here (no </script> can appear in identifiers/layers).
    html = html.replace("__GRAPH_DATA__", json.dumps(graph, indent=2))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote standalone viewer: {out_path}")
    print(f"  {len(graph.get('nodes', []))} node(s), {len(graph.get('edges', []))} edge(s)")
    print("  Open it directly in a browser (file://) — no server needed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a standalone, shareable HTML graph viewer from graph.json.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output HTML path (default: data/graph.html)")
    parser.add_argument("--title", default="Code Archaeologist — Graph", help="Page title/heading")
    args = parser.parse_args(argv)
    return build(args.graph, args.out, args.title)


if __name__ == "__main__":
    raise SystemExit(main())
