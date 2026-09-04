#!/usr/bin/env node
/**
 * code-archaeologist — installer CLI for the code-wiki agent skill.
 *
 * Installs the skill into the harness folder of your choice
 * (.agents, .claude, .cursor, .windsurf, .zed, or a custom path), verifies a
 * compatible Python is available, and can run an end-to-end self-test on the
 * bundled sample_src demo. Zero npm dependencies (Node built-ins only).
 *
 *   npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill                      # interactive: pick a harness
 *   npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --harness claude     # install into .claude/skills/code-wiki
 *   npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --dir .foo/skills/cw # install into a custom path
 *   npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --self-test
 *   npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill --help
 */
"use strict";

const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { spawnSync } = require("child_process");

const PKG_ROOT = path.resolve(__dirname, "..");
const SKILL_SRC = path.join(PKG_ROOT, ".agents", "skills", "code-wiki");
const SAMPLE_SRC = path.join(PKG_ROOT, "sample_src");

// Known agent harnesses -> where the skill folder lives, relative to a project.
// Add your own with --dir <path>.
const HARNESSES = {
  agents:   { label: "Agents (.agents)", dir: ".agents/skills/code-wiki" },
  claude:   { label: "Claude Code",      dir: ".claude/skills/code-wiki" },
  cursor:   { label: "Cursor",           dir: ".cursor/skills/code-wiki" },
  windsurf: { label: "Windsurf",         dir: ".windsurf/skills/code-wiki" },
  zed:      { label: "Zed",              dir: ".zed/skills/code-wiki" },
};
const DEFAULT_HARNESS = "agents";

// ---- tiny arg parser ---------------------------------------------------------
function parseArgs(argv) {
  const opts = {
    target: process.cwd(),
    harness: null,
    dir: null,
    selfTest: false,
    force: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target" || a === "-t") opts.target = path.resolve(argv[++i]);
    else if (a === "--harness") opts.harness = String(argv[++i] || "").toLowerCase();
    else if (a === "--dir" || a === "-d") opts.dir = argv[++i];
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
  npx github:non-nattawut/Code-Archaeologist-LLM-Agent-Skill [options]

Options:
  --harness <name>     Target harness: ${Object.keys(HARNESSES).join(", ")}
  -d, --dir <path>     Custom install path (relative to --target or absolute);
                       overrides --harness
  -t, --target <dir>   Project root to install into (default: current directory)
      --self-test      After installing, build the bundled sample_src demo
  -f, --force          Overwrite an existing data/ workspace (default: keep it)
  -h, --help           Show this help

If neither --harness nor --dir is given and you're in a terminal, you'll be
prompted to choose a harness. Non-interactively it defaults to "${DEFAULT_HARNESS}".

Harness folders:
${Object.entries(HARNESSES).map(([k, v]) => `  ${k.padEnd(9)} -> ${v.dir}`).join("\n")}
`;

// ---- helpers -----------------------------------------------------------------
function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(question, (a) => { rl.close(); resolve(a); }));
}

async function chooseInstallDir(opts) {
  // Explicit custom path wins.
  if (opts.dir) return opts.dir;

  // Explicit harness name.
  if (opts.harness) {
    if (!HARNESSES[opts.harness]) {
      console.error(`ERROR: unknown harness "${opts.harness}". Valid: ${Object.keys(HARNESSES).join(", ")} (or use --dir).`);
      process.exit(2);
    }
    return HARNESSES[opts.harness].dir;
  }

  // Non-interactive: fall back to the default harness.
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.log(`No --harness/--dir given; defaulting to "${DEFAULT_HARNESS}" (${HARNESSES[DEFAULT_HARNESS].dir}).`);
    return HARNESSES[DEFAULT_HARNESS].dir;
  }

  // Interactive menu.
  const keys = Object.keys(HARNESSES);
  console.log("Where should the skill be installed?\n");
  keys.forEach((k, i) => {
    console.log(`  ${i + 1}) ${HARNESSES[k].label.padEnd(18)} ${HARNESSES[k].dir}`);
  });
  console.log(`  ${keys.length + 1}) Custom path…`);
  const raw = (await ask(`\nChoose [1-${keys.length + 1}] (default 1 - ${DEFAULT_HARNESS}): `)).trim();

  if (!raw) return HARNESSES[DEFAULT_HARNESS].dir;
  if (HARNESSES[raw.toLowerCase()]) return HARNESSES[raw.toLowerCase()].dir; // typed a name
  const n = parseInt(raw, 10);
  if (n >= 1 && n <= keys.length) return HARNESSES[keys[n - 1]].dir;
  if (n === keys.length + 1) {
    const p = (await ask("Enter path relative to project root (e.g. .myagent/skills/code-wiki): ")).trim();
    return p || HARNESSES[DEFAULT_HARNESS].dir;
  }
  console.log(`Unrecognized choice; defaulting to "${DEFAULT_HARNESS}".`);
  return HARNESSES[DEFAULT_HARNESS].dir;
}

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
  // data/ groups output by map: structure/ (class graph), flow/ (call graph),
  // cache/ (internal AI-summary + freshness state). Scripts create flow/ and
  // cache/ on demand; seed the structure skeleton so the viewer/tracer defaults
  // resolve before the first build.
  const vault = path.join(dataDir, "structure", "vault");
  fs.mkdirSync(vault, { recursive: true });
  const graph = path.join(dataDir, "structure", "graph.json");
  const registry = path.join(dataDir, "structure", "registry.json");
  const keep = path.join(vault, ".gitkeep");
  if (force || !fs.existsSync(graph)) fs.writeFileSync(graph, '{\n  "nodes": [],\n  "edges": []\n}\n');
  if (force || !fs.existsSync(registry)) fs.writeFileSync(registry, "{}\n");
  if (!fs.existsSync(keep)) fs.writeFileSync(keep, "");
}

// ---- main --------------------------------------------------------------------
async function main() {
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

  const subdir = await chooseInstallDir(opts);
  const relPosix = subdir.split(path.sep).join("/");
  const dest = path.isAbsolute(subdir) ? subdir : path.join(opts.target, subdir);

  console.log(`\nInstalling skill into ${dest} ...`);
  fs.mkdirSync(dest, { recursive: true });
  copyDir(path.join(SKILL_SRC, "scripts"), path.join(dest, "scripts"));
  copyDir(path.join(SKILL_SRC, "templates"), path.join(dest, "templates"));
  fs.copyFileSync(path.join(SKILL_SRC, "SKILL.md"), path.join(dest, "SKILL.md"));
  fs.copyFileSync(path.join(SKILL_SRC, "package.json"), path.join(dest, "package.json"));
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
    console.log(`\nOK   Self-test complete. Open ${path.join(dest, "data", "structure", "graph.html")}`);
    return 0;
  }

  console.log("Next steps (from your project root):");
  console.log(`  ${py.exe} ${relPosix}/scripts/build_wiki.py --src ./src`);
  console.log(`  ${py.exe} ${relPosix}/scripts/build_graph.py`);
  console.log(`  ${py.exe} ${relPosix}/scripts/build_html.py`);
  console.log("\nBackend (Python) needs no dependencies. To also parse frontend (JS/TS), run:");
  console.log(`  cd ${relPosix} && npm install`);
  console.log("Tip: add --self-test to build the bundled demo now.");
  return 0;
}

main().then((code) => process.exit(code)).catch((err) => {
  console.error(err);
  process.exit(1);
});
