#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def render(dot_exe: str, input_path: Path, output_path: Path) -> int:
    commands = [
        [dot_exe, "-Tsvg:cairo", str(input_path), "-o", str(output_path)],
        [dot_exe, "-Tsvg", str(input_path), "-o", str(output_path)],
    ]

    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode == 0:
            print(f"Rendered {output_path} with {' '.join(command[1:3])}")
            return 0

    sys.stderr.write(
        "Graphviz 'dot' was found, but SVG rendering failed.\n"
    )
    return commands[-1] and completed.returncode or 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Graphviz DOT file to SVG."
    )
    parser.add_argument("input_dot", help="Path to the input .dot file")
    parser.add_argument(
        "output_svg",
        nargs="?",
        help="Optional output .svg path. Defaults to replacing .dot with .svg",
    )
    args = parser.parse_args()

    input_path = Path(args.input_dot).expanduser().resolve()
    if not input_path.is_file():
        sys.stderr.write(f"Input DOT file not found: {input_path}\n")
        return 66

    if args.output_svg:
        output_path = Path(args.output_svg).expanduser().resolve()
    else:
        output_path = input_path.with_suffix(".svg")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dot_exe = shutil.which("dot")
    if not dot_exe:
        sys.stderr.write(
            "Graphviz 'dot' is not installed. "
            f"Keep the DOT file and run later: dot -Tsvg \"{input_path}\" -o \"{output_path}\"\n"
        )
        return 127

    return render(dot_exe, input_path, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
