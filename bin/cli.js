#!/usr/bin/env node
/**
 * code-archaeologist — installer CLI for the code-wiki agent skill.
 *
 * Copies the skill into a project's .agents/skills/code-wiki folder, verifies a
 * compatible Python is available, and can run an end-to-end self-test on the
 * bundled sample_src demo. Zero npm dependencies (Node built-ins only).
 *
 *   npx code-archaeologist-skill                 # install into the current project
 *   npx code-archaeologist-skill --target <dir>  # install into <dir>
 *   npx code-archaeologist-skill --self-test     # install + build the demo
 *   npx code-archaeologist-skill --help
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const PKG_ROOT = path.resolve(__dirname, "..");
const SKILL_SRC = path.join(PKG_ROOT, ".agents", "skills", "code-wiki");
const SAMPLE_SRC = path.join(PKG_ROOT, "sample_src");
const REL_SKILL = path.join(".agents", "skills", "code-wiki");

// ---- tiny arg parser ---------------------------------------------------------
function parseArgs(argv) {
  const opts = { target: process.cwd(), selfTest: false, force: false, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target" || a === "-t") opts.target = path.resolve(argv[++i]);
    else if (a === "--self-test") opts.selfTest = true;
    else if (a === "--force" || a === "-f") opts.force = true;
    else if (a === "--help" || a === "-h") opts.help = true;
    else {
      console.error(`Unknown option: ${a}`);
      opts.help = true;
    }
  }
  return opts;
}

const HELP = `code-archaeologist — install the code-wiki agent skill

Usage:
  npx code-archaeologist-skill [options]

Options:
  -t, --target <dir>   Project to install into (default: current directory)
      --self-test      After installing, build the bundled sample_src demo
  -f, --force          Overwrite an existing data/ workspace (default: keep it)
  -h, --help           Show this help

What it installs (into <target>/${REL_SKILL}):
  SKILL.md, scripts/, templates/, and a fresh data/ workspace.
`;

// ---- helpers -----------------------------------------------------------------
function findPython() {
  for (const exe of ["python3", "python", "py"]) {
    const r = spawnSync(exe, ["-c", "import sys;print('%d.%d'%sys.version_info[:2])"], {
      encoding: "utf8",
    });
    if (r.status === 0 && r.stdout) {
      const [maj, min] = r.stdout.trim().split(".").map(Number);
      if (maj > 3 || (maj === 3 && min >= 10)) return { exe, version: r.stdout.trim() };
    }
  }
  return null;
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  fs.cpSync(src, dest, { recursive: true });
}

function seedDataDir(dataDir, force) {
  const vault = path.join(dataDir, "vault");
  fs.mkdirSync(vault, { recursive: true });
  const graph = path.join(dataDir, "graph.json");
  const registry = path.join(dataDir, "registry.json");
  const keep = path.join(vault, ".gitkeep");
  if (force || !fs.existsSync(graph)) fs.writeFileSync(graph, '{\n  "nodes": [],\n  "edges": []\n}\n');
  if (force || !fs.existsSync(registry)) fs.writeFileSync(registry, "{}\n");
  if (!fs.existsSync(keep)) fs.writeFileSync(keep, "");
}

// ---- main --------------------------------------------------------------------
function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    process.stdout.write(HELP);
    return 0;
  }

  console.log("Code Archaeologist — skill installer\n");

  const py = findPython();
  if (!py) {
    console.error("ERROR: Python 3.10+ not found on PATH.");
    console.error("Install it from https://python.org and re-run.");
    return 1;
  }
  console.log(`OK   Python ${py.version} found (${py.exe})`);

  if (!fs.existsSync(SKILL_SRC)) {
    console.error(`ERROR: bundled skill not found at ${SKILL_SRC}`);
    return 1;
  }

  const dest = path.join(opts.target, REL_SKILL);
  console.log(`Installing skill into ${dest} ...`);
  fs.mkdirSync(dest, { recursive: true });
  copyDir(path.join(SKILL_SRC, "scripts"), path.join(dest, "scripts"));
  copyDir(path.join(SKILL_SRC, "templates"), path.join(dest, "templates"));
  fs.copyFileSync(path.join(SKILL_SRC, "SKILL.md"), path.join(dest, "SKILL.md"));
  seedDataDir(path.join(dest, "data"), opts.force);
  console.log("OK   Skill installed.\n");

  if (opts.selfTest) {
    console.log("Running self-test on bundled sample_src/ ...");
    const steps = [
      ["scripts/build_wiki.py", "--src", SAMPLE_SRC],
      ["scripts/build_graph.py"],
      ["scripts/build_html.py"],
    ];
    for (const [script, ...args] of steps) {
      const r = spawnSync(py.exe, [path.join(dest, script), ...args], { stdio: "inherit" });
      if (r.status !== 0) {
        console.error(`ERROR: self-test step failed: ${script}`);
        return r.status || 1;
      }
    }
    console.log(`\nOK   Self-test complete. Open ${path.join(dest, "data", "graph.html")}`);
    return 0;
  }

  console.log("Next steps (from your project root):");
  console.log(`  ${py.exe} ${REL_SKILL.split(path.sep).join("/")}/scripts/build_wiki.py --src ./src`);
  console.log(`  ${py.exe} ${REL_SKILL.split(path.sep).join("/")}/scripts/build_graph.py`);
  console.log(`  ${py.exe} ${REL_SKILL.split(path.sep).join("/")}/scripts/build_html.py`);
  console.log("\nTip: add --self-test to build the bundled demo now.");
  return 0;
}

process.exit(main());
