---
name: code-route-mapper
description: inspect a local repository and turn real request flow, data flow, event flow, or routing behavior into clear code-driven diagrams. use when codex needs to read source code, trace handlers through services, jobs, queues, databases, or external apis, and produce graphviz dot, svg, mermaid, or plantuml route maps, architecture diagrams, 请求流, 数据走向, 事件流, 调用链, or reusable diagramming prompts. prefer this skill for evidence-backed diagrams from an actual codebase, not for purely conceptual uml with no repository inspection.
---

# Code Route Mapper

## Overview

Trace actual code paths in a repository and produce route diagrams that make request, data, or event movement easy to follow. Default to Graphviz DOT as the editable source of truth and render SVG when Graphviz is available.

## Choose the output format

- Default to Graphviz DOT plus SVG for repository-driven route maps, dataflow diagrams, request flow diagrams, and event flow diagrams.
- Use Mermaid only when the user wants Markdown-native diagrams or lightweight docs output.
- Use PlantUML only when the user explicitly asks for PlantUML or the repository already standardizes on it. When doing that, read [references/plantuml-templates.md](references/plantuml-templates.md) and keep the diagram black and white.
- Produce the diagram source first, then render the visual output from that source. Do not start from raw SVG unless the user explicitly asks for hand-written SVG.

## Trace before drawing

1. Identify entrypoints first. Look for HTTP routes, controllers, RPC endpoints, message consumers, schedulers, CLI commands, webhooks, and background jobs. Use the language-specific cues in [references/tracing-playbook.md](references/tracing-playbook.md).
2. Follow business-carrying edges only. Keep edges that move request data, domain data, state transitions, or external side effects. Collapse trivial helpers, logging, metrics, constants, dependency injection wiring, and boilerplate.
3. Normalize the flow into layers. Prefer `Entry`, `Validation`, `Application`, `Domain`, `Persistence`, and `External`, renaming only when the codebase uses a clearer house style.
4. Mark each edge as `confirmed` or `suspected`. Treat an edge as confirmed only when there is direct code evidence such as imports, calls, registrations, route tables, queue bindings, or config wiring.
5. Create an overview before a detail view. Start with the few highest-value business flows. Add a detailed diagram only when the user asks or when the codebase is large enough to require drill-down.

## Draw for readability

- Use left-to-right layout for route maps unless the user explicitly asks for top-to-bottom.
- Keep the main business direction readable within 10 seconds.
- Prefer rounded rectangles for code modules, cylinders for databases, and a distinct visual for queues, topics, and third-party services.
- Default to a grid-first layout. Regularity is more important than packing every node tightly.
- Distinguish edge types clearly:
  - solid = synchronous call or direct request path
  - dashed = async publish, consume, enqueue, or callback path
  - dotted = indirect dependency, config wiring, or inferred relationship
- Label edges with the action, not just the destination: `validate`, `call`, `read`, `write`, `publish`, `consume`, `transform`, `persist`, `notify`.
- Include payload or event names when that materially improves clarity.
- Reduce crossing lines aggressively. Favor orthogonal routing over decorative curves.
- Keep node labels short and evenly shaped. Prefer 2 to 3 short lines per node rather than one very long line.
- When multiple nodes belong to the same layer, force alignment with `rank=same` and use invisible edges if Graphviz needs help stabilizing the layout.
- Keep the number of columns small. For overview diagrams, prefer 4 to 7 major columns.
- Avoid mixing giant cluster boxes with tiny single nodes in the same layer unless that difference is semantically important.

## Default visual standard

- Use a clean engineering style: white background, modest rounded corners, consistent spacing, and restrained colors.
- Prefer the Graphviz styling in [references/diagram-templates.md](references/diagram-templates.md).
- For Graphviz output on Windows, default to `Microsoft YaHei UI` for mixed Chinese and English labels. It is usually more stable and visually cleaner than `Inter` in local Graphviz rendering.
- If the user explicitly asks for `Source Han Sans SC` and the environment has it installed, prefer it over `Microsoft YaHei UI`.
- Use `Segoe UI` only for English-only diagrams when the labels are short and there is no Chinese content.
- When the user asks for monochrome output, switch to the strict black-and-white template in [references/diagram-templates.md](references/diagram-templates.md).

## Regular layout checklist

Before rendering a Graphviz diagram, check these points:

1. The main route advances in one consistent direction.
2. Sibling nodes in the same conceptual layer are aligned with `rank=same`.
3. Long labels have been split so node sizes are not wildly uneven.
4. Edges mostly travel horizontally or vertically, not diagonally across the page.
5. If the layout is still skewed, add a small number of invisible edges to stabilize columns or rows.
6. Re-render after layout adjustments instead of hand-editing SVG.

## Output contract

Unless the user explicitly asks for inline-only output, write files under `docs/architecture/`:

- `*-overview.dot`
- `*-overview.svg`
- `*-detail.dot` if detail is warranted
- `*-detail.svg` if rendered
- `*-evidence.md`

In the response:

1. Summarize the main flows in plain language.
2. State which diagram format was chosen and why.
3. List the most important confirmed edges.
4. Call out suspected edges or blind spots.
5. Point to the generated files.

## Evidence standard

For every important edge, record:

- source node
- target node
- action label
- file path
- symbol or registration point
- confidence: `confirmed` or `suspected`

Keep the evidence file concise and directly mappable to the diagram.

## Rendering workflow

- Write DOT first using the template in [references/diagram-templates.md](references/diagram-templates.md).
- On Windows or mixed-path environments, render SVG with [scripts/render_graphviz.py](scripts/render_graphviz.py).
- On POSIX shells, you may also use [scripts/render_graphviz.sh](scripts/render_graphviz.sh).
- If Graphviz is unavailable, still write the DOT file and include the exact render command the user can run later.
- Do not rewrite the diagram into raw SVG by hand unless the user explicitly requests manual SVG authoring.

## Boundaries

- Do not refactor business code unless the user explicitly asks.
- Do not draw a giant call graph. Compress the system into business-relevant route segments.
- Do not claim certainty where the code only hints at behavior. Use `suspected`.
- Do not choose PlantUML or Mermaid by default when Graphviz DOT would make the route clearer.

## Reference files

Read these files when needed:

- [references/tracing-playbook.md](references/tracing-playbook.md) for repository search heuristics and evidence rules
- [references/diagram-templates.md](references/diagram-templates.md) for Graphviz, Mermaid, and black-and-white style templates
- [references/plantuml-templates.md](references/plantuml-templates.md) only when the user explicitly asks for PlantUML-compatible output
