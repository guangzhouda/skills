# Diagram Templates

## Default Graphviz DOT template

Use this for most code-driven route maps.

```dot
digraph RouteMap {
  graph [
    rankdir=LR,
    newrank=true,
    compound=true,
    bgcolor="#FFFFFF",
    pad="0.24",
    nodesep="0.42",
    ranksep="0.82",
    splines=ortho,
    outputorder=nodesfirst
  ];

  node [
    shape=box,
    style="rounded,filled",
    fillcolor="#F8FAFC",
    color="#64748B",
    penwidth=1.4,
    fontname="Microsoft YaHei UI",
    fontsize=12,
    margin="0.14,0.10",
    width=2.40,
    height=0.82
  ];

  edge [
    color="#2563EB",
    penwidth=1.6,
    arrowhead=vee,
    fontname="Microsoft YaHei UI",
    fontsize=10,
    labelfloat=false
  ];

  subgraph cluster_entry {
    label="Entry";
    color="#CBD5E1";
    style="rounded";
    route [label="POST /orders"];
  }

  subgraph cluster_app {
    label="Application";
    color="#CBD5E1";
    style="rounded";
    service [label="CreateOrderService"];
  }

  subgraph cluster_persistence {
    label="Persistence";
    color="#CBD5E1";
    style="rounded";
    db [label="orders table", shape=cylinder, fillcolor="#FFFFFF"];
  }

  route -> service [label="validate + call"];
  service -> db [label="write"];
}
```

### Regular layout additions

Use these layout helpers when the first render looks skewed:

```dot
{ rank=same; route; service; db; }

route [group="g1"];
service [group="g2"];
db [group="g3"];

route -> service -> db [style=invis, weight=2];
```

- Use `rank=same` to align siblings in one row or column.
- Use `group` to stabilize column membership across ranks.
- Use a few invisible edges with moderate weight to keep the grid tidy.
- Keep node labels to 2 to 3 short lines. Split long API or symbol names across lines.
- Prefer overview diagrams with a small number of columns instead of many jagged intermediate nodes.

### Edge style conventions

- synchronous call: default solid edge
- async publish or consume: `style=dashed`
- indirect or inferred relation: `style=dotted`
- external service: use a distinct node fill or edge color, but keep the palette restrained

### Node conventions

- route, handler, controller: rounded rectangle
- service or use case: rounded rectangle
- database or cache: cylinder
- queue, topic, stream: box with explicit label such as `Kafka topic: orders`
- external API: box with a clearer boundary label such as `Stripe API`

## Strict black-and-white Graphviz template

Use this when the user asks for monochrome output or when the diagram will be printed.

```dot
digraph RouteMapBW {
  graph [
    rankdir=LR,
    newrank=true,
    bgcolor="white",
    pad="0.24",
    nodesep="0.42",
    ranksep="0.82",
    splines=ortho
  ];

  node [
    shape=box,
    style="rounded,filled",
    fillcolor="white",
    color="black",
    penwidth=1.5,
    fontname="Microsoft YaHei UI",
    fontsize=12,
    margin="0.12,0.08"
  ];

  edge [
    color="black",
    penwidth=1.2,
    arrowhead=vee,
    fontname="Microsoft YaHei UI",
    fontsize=10
  ];
}
```

## Mermaid fallback template

Use this only when the user wants markdown-native output.

```mermaid
---
config:
  theme: base
  themeVariables:
    primaryColor: "#F8FAFC"
    primaryBorderColor: "#64748B"
    primaryTextColor: "#0F172A"
    lineColor: "#2563EB"
    fontFamily: "Microsoft YaHei UI, Segoe UI, Arial, sans-serif"
  flowchart:
    curve: linear
---
flowchart LR
  A[Route] -->|validate + call| B[Service]
  B -->|write| C[(Database)]
  B -. publish .-> D[Topic]
```

## PlantUML fallback rule

When the user explicitly asks for PlantUML, switch to the shared header and black-and-white conventions in `references/plantuml-templates.md`.
