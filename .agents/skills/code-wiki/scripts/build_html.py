#!/usr/bin/env python3
"""build_html.py — Generate a standalone, shareable HTML graph viewer.

Reads a graph JSON (structure `graph.json` or flow `flow_graph.json`) and writes a
single self-contained HTML file with the graph data embedded inline (no server
required). Open it directly via file://, commit it, or email it.

The viewer is a full-screen dark canvas with:
  - neighbor highlighting on node click (the rest dims), or full transitive
    BLAST RADIUS highlighting when that toggle is on,
  - COLOR MODES: by layer, by folder, by churn, or by risk (churn x connectivity)
    when `--insights` data is embedded,
  - risk markers: nodes carrying security findings get a red ring, and the
    findings are listed in the panel when `--security` data is embedded,
  - a slide-in DETAIL PANEL showing what the selected method/class does — its
    description, signature, source file, churn/owner, blast-radius counts, and
    clickable callers/callees,
  - a search box (press "/") and a legend that follows the color mode.

`force-graph` is loaded from a CDN. Re-run any time to refresh the file.

    python build_html.py                                   # -> data/graph.html
    python build_html.py --graph data/flow_graph.json --out data/flow.html --title "Request Flow"
    python build_html.py --graph data/flow/flow_graph.json --out data/flow/flow.html \
        --insights data/report/insights.json --security data/report/security.json

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
    --muted: #8b98ad; --accent: #6ea8fe; --danger: #f85149;
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
  #controls { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--muted); }
  #mode { background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 5px 8px; font-size: 12px; outline: none; }
  #controls label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }

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
  .issue { border-left: 2px solid var(--danger); padding-left: 8px; margin: 6px 0; font-size: 12px; }
  .issue .sev { color: var(--danger); text-transform: uppercase; font-size: 10px; letter-spacing: .6px; }
  .issue code { color: var(--muted); word-break: break-all; }
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
  <div id="controls">
    <span>Color</span>
    <select id="mode"></select>
    <label title="Highlight every node reachable from / reaching the selection">
      <input type="checkbox" id="blast" /> Blast radius
    </label>
  </div>
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
const INSIGHTS = __INSIGHTS__;   // { nodes: { id: {commits, owner, risk, fan_in, fan_out} } }
const ISSUES = __SECURITY__;     // { id: [ {severity, rule, message, file, line, snippet} ] }

// Customize per-layer colors here.
const LAYER_COLORS = {
  controller: "#f778ba", endpoint: "#f778ba", service: "#6ea8fe", repository: "#3fb950",
  model: "#e3b341", client: "#39c5cf", config: "#a371f7", ui: "#f0883e",
  function: "#adbac7", unknown: "#8b98ad"
};
const FOLDER_COLORS = ["#6ea8fe", "#f778ba", "#3fb950", "#e3b341", "#a371f7", "#39c5cf",
                       "#f0883e", "#db6d28", "#8ddb8c", "#c297ff"];
const COOL = [45, 63, 94], HOT = [248, 81, 73];   // churn/risk heat ramp endpoints

const metricsOf = (id) => (INSIGHTS.nodes && INSIGHTS.nodes[id]) || {};
const HAS_INSIGHTS = !!(INSIGHTS.nodes && Object.keys(INSIGHTS.nodes).length);
const folderOf = (n) => {
  const src = String(n.source || "").split(":")[0];
  const i = src.lastIndexOf("/");
  return i < 0 ? "(root)" : src.slice(0, i);
};
const folders = [...new Set(GRAPH.nodes.map(folderOf))].sort();
const heat = (value, max) => {
  const t = max > 0 ? Math.min(1, value / max) : 0;
  const c = COOL.map((v, i) => Math.round(v + (HOT[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};
const maxOf = (field) => Math.max(0, ...GRAPH.nodes.map((n) => metricsOf(n.id)[field] || 0));
const MAX = { commits: maxOf("commits"), risk: maxOf("risk") };

let mode = "layer";
function colorFor(n) {
  if (mode === "folder") return FOLDER_COLORS[folders.indexOf(folderOf(n)) % FOLDER_COLORS.length];
  if (mode === "churn") return heat(metricsOf(n.id).commits || 0, MAX.commits);
  if (mode === "risk") return heat(metricsOf(n.id).risk || 0, MAX.risk);
  return LAYER_COLORS[n.layer] || LAYER_COLORS[n.kind] || LAYER_COLORS.unknown;
}
const worstIssue = (id) => {
  const list = ISSUES[id] || [];
  return list.some((f) => f.severity === "high") ? "high" : (list.length ? list[0].severity : null);
};

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

// ---- color modes + legend ----
const MODES = [["layer", "Layer"], ["folder", "Folder"]]
  .concat(HAS_INSIGHTS ? [["churn", "Churn"], ["risk", "Risk"]] : []);
const modeSelect = document.getElementById("mode");
MODES.forEach(([value, label]) => modeSelect.add(new Option(label, value)));

const legend = document.getElementById("legend");
function renderLegend() {
  const items = [];
  if (mode === "layer")
    [...new Set(nodes.map((n) => n.layer))].sort().forEach((layer) =>
      items.push([LAYER_COLORS[layer] || LAYER_COLORS.unknown, layer]));
  else if (mode === "folder")
    folders.forEach((f, i) => items.push([FOLDER_COLORS[i % FOLDER_COLORS.length], f]));
  else {
    const max = mode === "churn" ? MAX.commits : MAX.risk;
    const label = mode === "churn" ? "commits" : "risk";
    [0, 0.5, 1].forEach((t) =>
      items.push([heat(max * t, max), `${Math.round(max * t)} ${label}`]));
  }
  if (Object.keys(ISSUES).length) items.push(["transparent", "◯ security finding"]);
  legend.innerHTML = items.map(([color, label]) =>
    `<span><i style="background:${color}"></i>${label}</span>`).join("");
}
modeSelect.addEventListener("change", () => {
  mode = modeSelect.value;
  renderLegend();
  repaint();
});
renderLegend();

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
    } else if (worstIssue(node.id)) {
      ctx.lineWidth = 1.5 / scale;
      ctx.strokeStyle = worstIssue(node.id) === "high" ? "#f85149" : "#e3b341";
      ctx.stroke();
    }
    const fontSize = Math.max(3, 11 / scale);
    ctx.font = `${fontSize}px ui-sans-serif, system-ui`;
    ctx.fillStyle = dim ? "rgba(215,221,232,.35)" : "#d7dde8";
    ctx.fillText(node.id, node.x + r + 2, node.y + 3.5);
    ctx.globalAlpha = 1;
  })
  .onNodeClick((node) => selectNode(node.id, true))
  .onBackgroundClick(() => clearSelection());

// The canvas is redrawn by the force-graph render loop; nudging a prop makes a
// pure repaint (colors, highlight) show up immediately.
const repaint = () => Graph.nodeRelSize(Graph.nodeRelSize());

// ---- selection + highlighting ----
// Transitive reach in one direction (the blast radius, excluding the start node).
function reach(id, adj) {
  const seen = new Set(), queue = [id];
  while (queue.length) {
    (adj.get(queue.shift()) || []).forEach((next) => {
      if (!seen.has(next)) { seen.add(next); queue.push(next); }
    });
  }
  seen.delete(id);
  return seen;
}

function computeHighlight(id) {
  const blast = document.getElementById("blast").checked;
  const downstream = blast ? reach(id, outAdj) : new Set(outAdj.get(id) || []);
  const upstream = blast ? reach(id, inAdj) : new Set(inAdj.get(id) || []);
  highlightNodes = new Set([id, ...downstream, ...upstream]);
  highlightLinks = new Set();
  links.forEach((l) => {
    const s = l.source.id || l.source, t = l.target.id || l.target;
    if (s === id || t === id) highlightLinks.add(l);
    else if (blast && highlightNodes.has(s) && highlightNodes.has(t)) highlightLinks.add(l);
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

  const m = metricsOf(node.id);
  if (m.commits)
    parts.push(`<div class="section"><h3>Churn &amp; ownership</h3><p>${m.commits} commit(s) ·
      risk ${m.risk} · owner ${esc(m.owner || "unknown")}<br />
      <span class="src">last changed ${esc((m.last_commit || "").slice(0, 10))}</span></p></div>`);

  const issues = ISSUES[node.id] || [];
  if (issues.length)
    parts.push(`<div class="section"><h3>Risk findings</h3>` + issues.map((f) =>
      `<div class="issue"><span class="sev">${esc(f.severity)}</span> ${esc(f.message)}
       <br /><code>${esc(f.file)}:${f.line}</code></div>`).join("") + `</div>`);

  parts.push(`<div class="section"><h3>Blast radius</h3><p>${reach(node.id, inAdj).size} upstream ·
    ${reach(node.id, outAdj).size} downstream</p></div>`);

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
document.getElementById("blast").addEventListener("change", () => {
  if (selected) { computeHighlight(selected); repaint(); }
});
document.getElementById("closeDetail").addEventListener("click", clearSelection);
window.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  else if (e.key === "Escape") { clearSelection(); search.blur(); }
});
</script>
</body>
</html>
"""


def _load(path: str | None, default: dict) -> dict:
    """Optional side-data (insights / security). Missing or broken -> the default."""
    if not path or not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        print(f"warning: {path} is not valid JSON; skipping it.")
        return default


def issues_by_node(security: dict) -> dict[str, list[dict]]:
    """Group scan findings under the node that owns them (unattributed ones are dropped)."""
    grouped: dict[str, list[dict]] = {}
    for f in security.get("findings", []):
        if f.get("node"):
            grouped.setdefault(f["node"], []).append(
                {k: f[k] for k in ("severity", "rule", "message", "file", "line")})
    return grouped


def build(graph_path: str, out_path: str, title: str,
          insights_path: str | None = None, security_path: str | None = None) -> int:
    if os.path.isfile(graph_path):
        with open(graph_path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    else:
        print(f"warning: {graph_path} not found; embedding an empty graph.")
        graph = {"nodes": [], "edges": []}

    # Side data is keyed by node id, and the two maps use different ids (class vs
    # Class.method) — so keep only what belongs to THIS graph.
    ids = {n["id"] for n in graph.get("nodes", [])}
    insights = {k: v for k, v in _load(insights_path, {}).get("nodes", {}).items() if k in ids}
    issues = {k: v for k, v in issues_by_node(_load(security_path, {})).items() if k in ids}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    html = TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__GRAPH_DATA__", json.dumps(graph, indent=2))
    html = html.replace("__INSIGHTS__", json.dumps({"nodes": insights}))
    html = html.replace("__SECURITY__", json.dumps(issues))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote standalone viewer: {out_path}")
    print(f"  {len(graph.get('nodes', []))} node(s), {len(graph.get('edges', []))} edge(s)")
    if insights:
        print("  churn/risk color modes enabled")
    if issues:
        print(f"  {sum(len(v) for v in issues.values())} risk finding(s) marked on {len(issues)} node(s)")
    print("  Open it directly in a browser (file://) — no server needed.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a standalone, shareable HTML graph viewer.")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="Path to graph.json / flow_graph.json")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output HTML path (default: data/graph.html)")
    parser.add_argument("--title", default="Code Archaeologist — Graph", help="Page title/heading")
    parser.add_argument("--insights", default=None,
                        help="insights.json from git_insights.py; adds churn/risk color modes")
    parser.add_argument("--security", default=None,
                        help="security.json from scan_security.py; marks risky nodes")
    args = parser.parse_args(argv)
    return build(args.graph, args.out, args.title, args.insights, args.security)


if __name__ == "__main__":
    raise SystemExit(main())
