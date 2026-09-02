#!/usr/bin/env bash
# Install / verify the Code Archaeologist (code-wiki) agent skill.
#
# The skill has zero external dependencies (Python 3.10+ standard library only),
# so "install" means:
#   1. Verify a compatible Python is available.
#   2. Optionally copy the skill into another project's .agents/skills/ folder.
#   3. Optionally run a self-test that builds the bundled sample_src demo.
#
# Usage:
#   ./install.sh                     # verify Python only
#   ./install.sh --self-test         # build the bundled sample_src demo
#   ./install.sh --target <path>     # install skill into another project
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$REPO_ROOT/.agents/skills/code-wiki"

TARGET=""
SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

echo "Code Archaeologist -- skill installer"

# --- Find a Python 3.10+ interpreter ---
PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "ERROR: Python 3.10+ not found on PATH. Install it from https://python.org and retry." >&2
  exit 1
fi
echo "OK   Python $("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])') found ($PY)"

# --- Optional: install into a target project ---
if [ -n "$TARGET" ]; then
  DEST="$TARGET/.agents/skills/code-wiki"
  echo "Installing skill into $DEST ..."
  mkdir -p "$DEST/data/vault"
  cp -R "$SKILL_SRC/scripts" "$DEST/"
  cp -R "$SKILL_SRC/templates" "$DEST/"
  cp "$SKILL_SRC/SKILL.md" "$DEST/"
  # Fresh, empty data workspace (do not carry the demo vault over).
  printf '{ "nodes": [], "edges": [] }\n' > "$DEST/data/graph.json"
  printf '{}\n' > "$DEST/data/registry.json"
  : > "$DEST/data/vault/.gitkeep"
  echo "OK   Skill installed."
  echo
  echo "Next steps (from $TARGET):"
  echo "  $PY .agents/skills/code-wiki/scripts/build_wiki.py --src ./src"
  echo "  $PY .agents/skills/code-wiki/scripts/build_graph.py"
  echo "  $PY .agents/skills/code-wiki/scripts/build_html.py"
fi

# --- Optional: self-test on bundled sample ---
if [ "$SELF_TEST" -eq 1 ]; then
  echo
  echo "Running self-test on bundled sample_src/ ..."
  cd "$REPO_ROOT"
  "$PY" .agents/skills/code-wiki/scripts/build_wiki.py --src ./sample_src
  "$PY" .agents/skills/code-wiki/scripts/build_graph.py
  "$PY" .agents/skills/code-wiki/scripts/build_html.py
  echo "OK   Self-test complete. Open .agents/skills/code-wiki/data/graph.html"
fi

if [ -z "$TARGET" ] && [ "$SELF_TEST" -eq 0 ]; then
  echo
  echo "Skill is ready to use in place. Try:  ./install.sh --self-test"
  echo "Or install into another project:      ./install.sh --target <path>"
fi
