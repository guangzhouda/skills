#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: render_graphviz.sh <input.dot> [output.svg]" >&2
  exit 64
fi

input="$1"
if [[ ! -f "$input" ]]; then
  echo "Input DOT file not found: $input" >&2
  exit 66
fi

if [[ $# -eq 2 ]]; then
  output="$2"
else
  output="${input%.dot}.svg"
fi

if ! command -v dot >/dev/null 2>&1; then
  echo "Graphviz 'dot' is not installed. Keep the DOT file and run: dot -Tsvg '$input' -o '$output'" >&2
  exit 127
fi

if dot -Tsvg:cairo "$input" -o "$output" 2>/dev/null; then
  echo "Rendered $output with dot -Tsvg:cairo"
  exit 0
fi

dot -Tsvg "$input" -o "$output"
echo "Rendered $output with dot -Tsvg"
