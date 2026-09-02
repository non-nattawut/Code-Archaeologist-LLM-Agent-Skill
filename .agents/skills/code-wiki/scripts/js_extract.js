#!/usr/bin/env node
/**
 * js_extract.js — JS/TS structure extractor for the code-wiki skill.
 *
 * Parses .js/.jsx/.ts/.tsx files with @babel/parser and prints a normalized JSON
 * array (one entry per file) to stdout, so the Python pipeline can merge frontend
 * entities into the same graph as the Python (backend) ones.
 *
 *   node js_extract.js <file> [<file> ...]
 *
 * Requires @babel/parser (the one dependency for frontend support). If it is not
 * installed the script exits non-zero with a clear message and the Python side
 * degrades gracefully (frontend files are skipped).
 */
"use strict";

const fs = require("fs");
const path = require("path");

let parser;
try {
  parser = require("@babel/parser");
} catch (_) {
  console.error("MISSING_DEP:@babel/parser (run `npm install` where the skill lives to enable frontend parsing)");
  process.exit(3);
}

function pluginsFor(file) {
  const ext = path.extname(file).toLowerCase();
  if (ext === ".tsx") return ["typescript", "jsx"];
  if (ext === ".ts") return ["typescript"];
  if (ext === ".jsx") return ["jsx"];
  return ["jsx"]; // .js — allow JSX, harmless if absent
}

function firstDocLine(node) {
  const c = node.leadingComments && node.leadingComments[node.leadingComments.length - 1];
  if (!c) return "";
  const line = c.value.split("\n").map((l) => l.replace(/^\s*\*?\s?/, "").trim()).find((l) => l);
  return line || "";
}

// Reconstruct a route-ish path from a string/template literal argument.
function urlOf(arg) {
  if (!arg) return "";
  if (arg.type === "StringLiteral") return arg.value;
  if (arg.type === "TemplateLiteral") {
    return arg.quasis
      .map((q, i) => q.value.cooked + (arg.expressions[i]
        ? ":" + (arg.expressions[i].name || "param") : ""))
      .join("");
  }
  return "";
}

function methodFromOptions(arg) {
  if (arg && arg.type === "ObjectExpression") {
    const p = arg.properties.find((p) => p.key && (p.key.name === "method" || p.key.value === "method"));
    if (p && p.value && p.value.type === "StringLiteral") return p.value.value.toUpperCase();
  }
  return "GET";
}

// Walk a subtree collecting called names and HTTP calls (fetch/axios).
function collectCalls(root) {
  const calls = new Set();
  const http = [];
  (function walk(node) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) return node.forEach(walk);
    if (node.type === "CallExpression") {
      const callee = node.callee;
      if (callee.type === "Identifier") {
        calls.add(callee.name);
        if (callee.name === "fetch") {
          http.push({ method: methodFromOptions(node.arguments[1]), url: urlOf(node.arguments[0]) });
        }
      } else if (callee.type === "MemberExpression" && callee.property) {
        const prop = callee.property.name;
        if (prop) calls.add(prop);
        const objName = callee.object && callee.object.name;
        if (objName === "axios" && ["get", "post", "put", "patch", "delete"].includes(prop)) {
          http.push({ method: prop.toUpperCase(), url: urlOf(node.arguments[0]) });
        }
      }
    }
    for (const k of Object.keys(node)) {
      if (k === "leadingComments" || k === "trailingComments" || k === "loc" || k === "type") continue;
      walk(node[k]);
    }
  })(root);
  return { calls: [...calls], http };
}

function unwrapExport(node) {
  if (node.type === "ExportNamedDeclaration" || node.type === "ExportDefaultDeclaration") {
    return node.declaration || null;
  }
  return node;
}

function extractFile(file) {
  const code = fs.readFileSync(file, "utf8");
  let ast;
  try {
    ast = parser.parse(code, { sourceType: "module", plugins: pluginsFor(file), attachComment: true });
  } catch (e) {
    process.stderr.write(`  ! skipped ${file}: ${e.message}\n`);
    return null;
  }

  const out = { file, classes: [], functions: [], imports: [] };

  for (const raw of ast.program.body) {
    const node = unwrapExport(raw) || raw;

    if (node.type === "ImportDeclaration") {
      out.imports.push({
        from: node.source.value,
        names: node.specifiers.map((s) => (s.imported && s.imported.name) || s.local.name),
      });
    } else if (node.type === "ClassDeclaration" && node.id) {
      const methods = node.body.body
        .filter((m) => m.type === "ClassMethod" && m.key)
        .map((m) => ({ name: m.key.name, doc: firstDocLine(m), line: m.loc.start.line, ...collectCalls(m.body) }));
      out.classes.push({
        name: node.id.name,
        bases: node.superClass && node.superClass.name ? [node.superClass.name] : [],
        doc: firstDocLine(raw),
        line: node.loc.start.line,
        methods,
      });
    } else if (node.type === "FunctionDeclaration" && node.id) {
      out.functions.push({ name: node.id.name, doc: firstDocLine(raw), line: node.loc.start.line, ...collectCalls(node.body) });
    } else if (node.type === "VariableDeclaration") {
      for (const d of node.declarations) {
        if (d.id && d.id.name && d.init &&
            (d.init.type === "ArrowFunctionExpression" || d.init.type === "FunctionExpression")) {
          out.functions.push({ name: d.id.name, doc: firstDocLine(raw), line: d.loc.start.line, ...collectCalls(d.init.body) });
        }
      }
    }
  }
  return out;
}

function main() {
  const files = process.argv.slice(2);
  const results = [];
  for (const f of files) {
    const r = extractFile(f);
    if (r) results.push(r);
  }
  process.stdout.write(JSON.stringify(results));
}

main();
