#!/usr/bin/env python3
"""build_html.py — Generate a standalone, shareable HTML graph viewer.

Reads a graph JSON (structure `graph.json` or flow `flow_graph.json`) and writes a
single self-contained HTML file with the graph data embedded inline (no server
required). Open it directly via file://, commit it, or email it.

The viewer is a full-screen dark canvas with:
  - neighbor highlighting on node click (the rest dims),
  - a slide-in DETAIL PANEL showing what the selected method/class does — its
    description, signature, source file, and clickable callers/callees,
  - a search box (press "/") and a layer legend.

`force-graph` is loaded from a CDN. Re-run any time to refresh the file.

    python build_html.py                                   # -> data/graph.html
    python build_html.py --graph data/flow_graph.json --out data/flow.html --title "Request Flow"

Zero external Python dependencies. Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, "data")
DEFAULT_GRAPH = os.path.join(DATA_DIR, "structure", "graph.json")
DEFAULT_OUT = os.path.join(DATA_DIR, "structure", "graph.html")

# The graph JSON is injected at __GRAPH_DATA__; the title at __TITLE__.
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0b0e14; --panel: #11161f; --border: #222b39; --text: #d7dde8;
    --muted: #8b98ad; --accent: #6ea8fe;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  #graph { position: fixed; inset: 0; }

  /* Top-left heads-up display */
  #hud { position: fixed; top: 16px; left: 16px; z-index: 20; display: flex;
    flex-direction: column; gap: 8px; max-width: 320px; }
  #hud .title { font-weight: 700; font-size: 15px; letter-spacing: .2px; }
  #hud .sub { color: var(--muted); font-size: 12px; }
  #search { background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 11px; width: 260px; outline: none; font-size: 13px; }
  #search:focus { border-color: var(--accent); }

  /* Legend bottom-left */
  #legend { position: fixed; left: 16px; bottom: 16px; z-index: 20; background: rgba(17,22,31,.8);
    border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; display: flex;
    flex-wrap: wrap; gap: 6px 12px; max-width: 320px; font-size: 12px; color: var(--muted); }
  #legend span { display: inline-flex; align-items: center; gap: 5px; }
  #legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

  /* Right detail panel */
  #detail { position: fixed; top: 0; right: 0; height: 100%; width: 360px; z-index: 30;
    background: var(--panel); border-left: 1px solid var(--border); padding: 20px;
    overflow-y: auto; transform: translateX(100%); transition: transform .22s ease;
    box-shadow: -12px 0 40px rgba(0,0,0,.35); }
  #detail.open { transform: translateX(0); }
  #detail .close { position: absolute; top: 12px; right: 14px; cursor: pointer;
    color: var(--muted); font-size: 20px; line-height: 1; border: none; background: none; }
  #detail .close:hover { color: var(--text); }
  #detail h2 { margin: 4px 0 10px; font-size: 16px; word-break: break-word; padding-right: 24px; }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border);
    color: var(--text); display: inline-flex; align-items: center; gap: 5px; text-transform: capitalize; }
  .badge i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .section { margin: 14px 0; }
  .section h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .8px; color: var(--muted);
    margin: 0 0 6px; }
  .section p { margin: 0; font-size: 13px; line-height: 1.5; }
  code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; }
  .src { color: var(--muted); font-size: 12px; word-break: break-all; }
  .neighbors { list-style: none; margin: 0; padding: 0; }
  .neighbors li { margin: 3px 0; }
  .link { color: var(--accent); cursor: pointer; font-size: 13px; }
  .link:hover { text-decoration: underline; }
  .empty { color: var(--muted); font-size: 12px; font-style: italic; }
  .hint { position: fixed; bottom: 16px; right: 16px; z-index: 20; color: var(--muted);
    font-size: 12px; background: rgba(17,22,31,.8); border: 1px solid var(--border);
    border-radius: 8px; padding: 6px 10px; }
</style>
<script src="https://cdn.jsdelivr.net/npm/force-graph@1.43.5/dist/force-graph.min.js"></script>
</head>
<body>
<div id="hud">
  <div class="title">__TITLE__</div>
  <div class="sub" id="stats"></div>
  <input id="search" placeholder="Search node…  (press /)" autocomplete="off" />
</div>
<div id="legend"></div>
<div class="hint" id="hint">Click a node for details</div>
<div id="detail">
  <button class="close" id="closeDetail" title="Close (Esc)">×</button>
  <div id="detailBody"></div>
</div>
<div id="graph"></div>

<script>
const GRAPH = __GRAPH_DATA__;

// Customize per-layer colors here.
const LAYER_COLORS = {
  controller: "#f778ba", endpoint: "#f778ba", service: "#6ea8fe", repository: "#3fb950",
  model: "#e3b341", client: "#39c5cf", config: "#a371f7", function: "#adbac7", unknown: "#8b98ad"
};
const colorFor = (n) => LAYER_COLORS[n.layer] || LAYER_COLORS[n.kind] || LAYER_COLORS.unknown;

const nodes = GRAPH.nodes.map((n) => ({ ...n }));
const byId = new Map(nodes.map((n) => [n.id, n]));
const links = GRAPH.edges.map((e) => ({ source: e.source, target: e.target, type: e.type }));
const isFlow = GRAPH.edges.some((e) => e.type === "calls");
const OUT_LABEL = isFlow ? "Calls" : "References";
const IN_LABEL = isFlow ? "Called by" : "Referenced by";

// Adjacency (by id).
const outAdj = new Map(), inAdj = new Map();
nodes.forEach((n) => { outAdj.set(n.id, []); inAdj.set(n.id, []); });
GRAPH.edges.forEach((e) => { outAdj.get(e.source)?.push(e.target); inAdj.get(e.target)?.push(e.source); });

let selected = null;         // selected node id
let highlightNodes = new Set();
let highlightLinks = new Set();

document.getElementById("stats").textContent = `${nodes.length} nodes · ${links.length} edges`;

// Legend from layers present.
const legend = document.getElementById("legend");
[...new Set(nodes.map((n) => n.layer))].forEach((layer) => {
  const s = document.createElement("span");
  s.innerHTML = `<i style="background:${LAYER_COLORS[layer] || LAYER_COLORS.unknown}"></i>${layer}`;
  legend.appendChild(s);
});

const Graph = ForceGraph()(document.getElementById("graph"))
  .backgroundColor("#0b0e14")
  .graphData({ nodes, links })
  .nodeId("id")
  .nodeRelSize(5)
  .nodeVal((n) => 1 + (outAdj.get(n.id).length + inAdj.get(n.id).length) * 0.6)
  .linkColor((l) => highlightLinks.has(l) ? "rgba(110,168,254,.9)"
    : (l.type === "http" ? "rgba(226,116,161,.55)" : "rgba(139,152,173,.18)"))
  .linkWidth((l) => highlightLinks.has(l) ? 2 : 1)
  .linkLineDash((l) => l.type === "http" ? [4, 3] : null)
  .linkDirectionalArrowLength(4)
  .linkDirectionalArrowRelPos(1)
  .linkDirectionalParticles((l) => highlightLinks.has(l) ? 3 : 0)
  .linkDirectionalParticleWidth(2)
  .nodeCanvasObject((node, ctx, scale) => {
    const deg = outAdj.get(node.id).length + inAdj.get(node.id).length;
    const r = 4 + Math.min(deg, 8) * 0.7;
    const dim = selected && !highlightNodes.has(node.id);
    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = colorFor(node);
    ctx.fill();
    if (node.id === selected) {
      ctx.lineWidth = 2 / scale; ctx.strokeStyle = "#ffffff"; ctx.stroke();
    }
    const fontSize = Math.max(3, 11 / scale);
    ctx.font = `${fontSize}px ui-sans-serif, system-ui`;
    ctx.fillStyle = dim ? "rgba(215,221,232,.35)" : "#d7dde8";
    ctx.fillText(node.id, node.x + r + 2, node.y + 3.5);
    ctx.globalAlpha = 1;
  })
  .onNodeClick((node) => selectNode(node.id, true))
  .onBackgroundClick(() => clearSelection());

// ---- selection + highlighting ----
function computeHighlight(id) {
  highlightNodes = new Set([id]);
  highlightLinks = new Set();
  (outAdj.get(id) || []).forEach((t) => highlightNodes.add(t));
  (inAdj.get(id) || []).forEach((s) => highlightNodes.add(s));
  links.forEach((l) => {
    const s = l.source.id || l.source, t = l.target.id || l.target;
    if (s === id || t === id) highlightLinks.add(l);
  });
}

function selectNode(id, recenter) {
  const node = byId.get(id);
  if (!node) return;
  selected = id;
  computeHighlight(id);
  openDetail(node);
  if (recenter && node.x != null) { Graph.centerAt(node.x, node.y, 500); Graph.zoom(3.2, 500); }
}

function clearSelection() {
  selected = null; highlightNodes.clear(); highlightLinks.clear();
  document.getElementById("detail").classList.remove("open");
}

// ---- detail panel ----
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
// Render a description that may contain [[wikilinks]] as clickable links.
function renderDoc(text) {
  const t = esc(text || "");
  return t.replace(/\[\[(.*?)\]\]/g, (_, id) =>
    byId.has(id) ? `<span class="link" data-goto="${esc(id)}">${esc(id)}</span>` : esc(id));
}
function neighborList(ids) {
  if (!ids || !ids.length) return '<span class="empty">None</span>';
  return '<ul class="neighbors">' + ids.map((id) =>
    `<li><span class="link" data-goto="${esc(id)}">${esc(id)}</span></li>`).join("") + "</ul>";
}

function openDetail(node) {
  const dot = colorFor(node);
  const parts = [];
  parts.push(`<h2 class="mono">${esc(node.id)}</h2>`);
  parts.push('<div class="badges">');
  if (node.kind) parts.push(`<span class="badge"><i style="background:${dot}"></i>${esc(node.kind)}</span>`);
  if (node.layer) parts.push(`<span class="badge">${esc(node.layer)}</span>`);
  if (node.cls) parts.push(`<span class="badge">${esc(node.cls)}</span>`);
  parts.push("</div>");

  parts.push(`<div class="section"><h3>What it does</h3><p>${renderDoc(node.doc)}</p></div>`);
  if (node.signature)
    parts.push(`<div class="section"><h3>Signature</h3><p><code>${esc(node.signature)}</code></p></div>`);
  if (node.source)
    parts.push(`<div class="section"><h3>Source</h3><p class="src mono">${esc(node.source)}</p></div>`);

  parts.push(`<div class="section"><h3>${OUT_LABEL}</h3>${neighborList(outAdj.get(node.id))}</div>`);
  parts.push(`<div class="section"><h3>${IN_LABEL}</h3>${neighborList(inAdj.get(node.id))}</div>`);

  const body = document.getElementById("detailBody");
  body.innerHTML = parts.join("");
  body.querySelectorAll("[data-goto]").forEach((el) =>
    el.addEventListener("click", () => selectNode(el.getAttribute("data-goto"), true)));
  document.getElementById("detail").classList.add("open");
}

// ---- search + keyboard ----
const search = document.getElementById("search");
function runSearch(term) {
  term = (term || "").trim().toLowerCase();
  if (!term) return;
  const hit = nodes.find((n) => n.id.toLowerCase().includes(term));
  if (hit) selectNode(hit.id, true);
}
search.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(search.value); });
document.getElementById("closeDetail").addEventListener("click", clearSelection);
window.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  else if (e.key === "Escape") { clearSelection(); search.blur(); }
});
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
    html = html.replace("__GRAPH_DATA__", json.dumps(graph, indent=2))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote standalone viewer: {out_path}")
    print(f"  {len(graph.get('nodes', []))} node(s), {len(graph.get('edges', []))} edge(s)")
    print("  Open it directly in a browser (file://) — no server needed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a standalone, shareable HTML graph viewer.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json / flow_graph.json")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output HTML path (default: data/graph.html)")
    parser.add_argument("--title", default="Code Archaeologist — Graph", help="Page title/heading")
    args = parser.parse_args(argv)
    return build(args.graph, args.out, args.title)


if __name__ == "__main__":
    raise SystemExit(main())
