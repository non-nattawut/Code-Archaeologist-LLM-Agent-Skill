#!/usr/bin/env node
/**
 * js_extract.js — JS/TS structure extractor for the code-archaeologist skill.
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

// `decorators-legacy` is on everywhere: it is what Nest, Angular and TypeORM emit,
// and a file without decorators parses identically with it enabled.
function pluginsFor(file) {
  const ext = path.extname(file).toLowerCase();
  if (ext === ".tsx") return ["typescript", "jsx", "decorators-legacy"];
  if (ext === ".ts") return ["typescript", "decorators-legacy"];
  if (ext === ".jsx") return ["jsx", "decorators-legacy"];
  return ["jsx", "decorators-legacy"]; // .js — allow JSX, harmless if absent
}

// A comment documents a node only when it sits directly above it. Babel hands the
// first statement in a file every comment that precedes it, so without the
// adjacency test a file header becomes the summary of whichever symbol happens to
// be declared first -- which is how "Thin HTTP client for the orders backend."
// ended up describing one function inside that client.
function firstDocLine(node) {
  const cs = node.leadingComments;
  const c = cs && cs[cs.length - 1];
  if (!c || !c.loc || !node.loc || c.loc.end.line !== node.loc.start.line - 1) return "";
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

const HTTP_VERBS = ["get", "post", "put", "patch", "delete"];

// `const api = axios.create({...})` is how most apps actually call an API, and
// `api.get(...)` looked like any other method call. Collecting the instance names
// first is deterministic -- only identifiers assigned from axios.create() count,
// never an arbitrary object that happens to have a .get().
function axiosInstances(body) {
  const names = new Set(["axios"]);
  for (const raw of body) {
    const node = unwrapExport(raw) || raw;
    if (node.type !== "VariableDeclaration") continue;
    for (const d of node.declarations) {
      const init = d.init;
      if (!d.id || !d.id.name || !init || init.type !== "CallExpression") continue;
      const callee = init.callee;
      if (callee.type === "MemberExpression" && callee.object && callee.object.name === "axios"
          && callee.property && callee.property.name === "create") {
        names.add(d.id.name);
      }
    }
  }
  return names;
}

// Walk a subtree collecting called names and HTTP calls (fetch/axios).
function collectCalls(root, axiosNames) {
  const names = axiosNames || new Set(["axios"]);
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
        if (names.has(objName) && HTTP_VERBS.includes(prop)) {
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

// --- routes -------------------------------------------------------------------
// A decorator's name and its first string argument: @Get(":id") -> ["get", ":id"],
// @Controller("orders") -> ["controller", "orders"].
function decoratorInfo(dec) {
  const expr = dec.expression || dec;
  if (expr.type === "CallExpression") {
    const name = expr.callee.name || (expr.callee.property && expr.callee.property.name);
    return { name: (name || "").toLowerCase(), arg: urlOf(expr.arguments[0]) };
  }
  return { name: ((expr.name || "")).toLowerCase(), arg: "" };
}

function joinPath(prefix, suffix) {
  const parts = [prefix, suffix].filter((p) => p !== "" && p != null)
    .map((p) => String(p).replace(/^\/+|\/+$/g, "")).filter((p) => p !== "");
  return "/" + parts.join("/");
}

// Nest: @Controller('orders') on the class gives the prefix, @Get(':id') on the
// method gives verb and suffix.
function nestRoutes(classDecorators, methodDecorators) {
  let prefix = "";
  for (const d of classDecorators || []) {
    const info = decoratorInfo(d);
    if (info.name === "controller") prefix = info.arg;
  }
  const routes = [];
  for (const d of methodDecorators || []) {
    const info = decoratorInfo(d);
    if (HTTP_VERBS.includes(info.name)) {
      routes.push({ method: info.name.toUpperCase(), path: joinPath(prefix, info.arg) });
    }
  }
  return routes;
}

// Express: `router.post("/orders", createOrder)` or the same with an inline arrow.
// Only a top-level ExpressionStatement counts, so a `.get()` buried in application
// logic is never mistaken for a route registration.
function expressRoutes(body, axiosNames) {
  const routes = [];
  for (const raw of body) {
    if (raw.type !== "ExpressionStatement") continue;
    const call = raw.expression;
    if (!call || call.type !== "CallExpression") continue;
    const callee = call.callee;
    if (callee.type !== "MemberExpression" || !callee.property) continue;
    const verb = (callee.property.name || "").toLowerCase();
    if (!HTTP_VERBS.includes(verb)) continue;
    const routePath = urlOf(call.arguments[0]);
    if (!routePath.startsWith("/")) continue;   // a path, not a URL fetched from somewhere
    const handler = call.arguments[call.arguments.length - 1];
    if (!handler) continue;
    const entry = {
      method: verb.toUpperCase(), path: routePath,
      line: raw.loc.start.line, endLine: raw.loc.end.line, doc: firstDocLine(raw),
    };
    if (handler.type === "Identifier") {
      entry.handler = handler.name;             // attaches to that function's node
    } else if (handler.type === "ArrowFunctionExpression" || handler.type === "FunctionExpression") {
      Object.assign(entry, collectCalls(handler.body, axiosNames));
    } else {
      continue;
    }
    routes.push(entry);
  }
  return routes;
}

// A JSX tag starting with a capital letter names another component; lowercase tags
// are host elements (div, span) and say nothing about structure. `jsx` is what makes
// a function a React component; `components` are the components it renders.
function jsxName(n) {
  if (!n) return "";
  if (n.type === "JSXIdentifier") return n.name;
  if (n.type === "JSXMemberExpression") return jsxName(n.property);
  return "";
}

function collectJsx(root) {
  let jsx = false;
  const components = new Set();
  (function walk(node) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) return node.forEach(walk);
    if (node.type === "JSXElement" || node.type === "JSXFragment") {
      jsx = true;
      const name = node.openingElement && jsxName(node.openingElement.name);
      if (name && /^[A-Z]/.test(name)) components.add(name);
    }
    for (const k of Object.keys(node)) {
      if (k === "leadingComments" || k === "trailingComments" || k === "loc" || k === "type") continue;
      walk(node[k]);
    }
  })(root);
  return { jsx, components: [...components].sort() };
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

  const body = ast.program.body;
  const axiosNames = axiosInstances(body);
  const out = { file, classes: [], functions: [], imports: [], routes: expressRoutes(body, axiosNames) };

  for (const raw of body) {
    const node = unwrapExport(raw) || raw;

    if (node.type === "ImportDeclaration") {
      out.imports.push({
        from: node.source.value,
        names: node.specifiers.map((s) => (s.imported && s.imported.name) || s.local.name),
      });
    } else if (node.type === "ClassDeclaration" && node.id) {
      const classDecorators = node.decorators || raw.decorators || [];
      const methods = node.body.body
        .filter((m) => m.type === "ClassMethod" && m.key)
        .map((m) => ({ name: m.key.name, doc: firstDocLine(m), line: m.loc.start.line,
                       endLine: m.loc.end.line, routes: nestRoutes(classDecorators, m.decorators),
                       ...collectCalls(m.body, axiosNames) }));
      out.classes.push({
        name: node.id.name,
        bases: node.superClass && node.superClass.name ? [node.superClass.name] : [],
        decorators: classDecorators.map((d) => decoratorInfo(d).name).filter(Boolean),
        doc: firstDocLine(raw),
        line: node.loc.start.line,
        endLine: node.loc.end.line,
        methods,
      });
    } else if (node.type === "FunctionDeclaration" && node.id) {
      out.functions.push({ name: node.id.name, doc: firstDocLine(raw),
                           line: node.loc.start.line, endLine: node.loc.end.line,
                           ...collectCalls(node.body, axiosNames), ...collectJsx(node.body) });
    } else if (node.type === "VariableDeclaration") {
      for (const d of node.declarations) {
        if (d.id && d.id.name && d.init &&
            (d.init.type === "ArrowFunctionExpression" || d.init.type === "FunctionExpression")) {
          out.functions.push({ name: d.id.name, doc: firstDocLine(raw),
                               line: d.loc.start.line, endLine: d.loc.end.line,
                               ...collectCalls(d.init.body, axiosNames), ...collectJsx(d.init.body) });
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
