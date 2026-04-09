# Repository Tracing Playbook

## 1. Start from executable entrypoints

Prioritize code that admits real traffic or starts real jobs:

- HTTP route registrations
- controller and handler classes
- RPC and gRPC service registration
- message consumer registration
- cron or scheduler registration
- CLI entry commands
- webhook handlers
- background worker bootstraps

Read the route table, boot file, module wiring, or application startup first before diving into helper code.

## 2. Search heuristics by stack

### Node.js / TypeScript

Look for:

- `express.Router`, `app.get`, `app.post`, `router.use`
- NestJS `@Controller`, `@Get`, `@Post`, `@MessagePattern`
- Next.js route handlers under `app/api` or `pages/api`
- tRPC routers and procedures
- BullMQ workers, agenda jobs, Kafka consumers, RabbitMQ bindings

Then follow controller -> service -> repository or client.

### Python

Look for:

- FastAPI `@app.get`, `@router.post`, `APIRouter`
- Flask or Django route and view registration
- Celery tasks and beat schedules
- management commands and click/typer entrypoints
- Kafka consumers or queue subscribers

Then follow view or endpoint -> service -> model or repository -> side effect.

### Go

Look for:

- `http.HandleFunc`, chi, gin, echo, fiber route registration
- gRPC server registration
- consumer setup in `main.go` or worker packages
- cron schedulers

Then follow handler -> service -> store or client.

### Java / Kotlin

Look for:

- Spring `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`
- `@KafkaListener`, `@RabbitListener`, `@Scheduled`
- command runner or batch entry classes

Then follow controller or listener -> service -> repository -> external integration.

### C#

Look for:

- ASP.NET controllers, `MapGet`, `MapPost`, minimal APIs
- background services and hosted services
- message consumers and scheduled jobs

Then follow endpoint -> application service -> repository or gateway.

## 3. Keep only business-carrying edges

Keep edges that explain how information moves:

- request parsing and validation
- orchestration and use-case calls
- state reads and writes
- event publish and consume paths
- third-party API calls
- notifications and outbound integrations

Drop or collapse:

- logging
- tracing and metrics
- small pure helpers
- constants and config access
- container or dependency injection glue
- test-only code
- mocks and fixtures

## 4. Label edges consistently

Prefer these verbs:

- `validate`
- `call`
- `read`
- `write`
- `transform`
- `publish`
- `consume`
- `persist`
- `notify`
- `enqueue`

Add payload or message names when helpful, for example `publish OrderCreated` or `write order + payment rows`.

## 5. Separate confidence levels

Mark an edge as `confirmed` only when code shows a direct relationship such as:

- a function or method call
- an import and invocation
- route registration to a handler
- queue or topic binding
- scheduler registration
- explicit repository or client call

Mark an edge as `suspected` when the relationship is only implied by naming, config conventions, interface wiring, or incomplete visibility.

## 6. Prefer overview first

Create one overview diagram before drawing detail diagrams.

A good overview usually contains:

- 3 to 8 business flows
- 5 to 20 nodes
- only the highest-value datastores and integrations
- no internal helper noise

Create detail diagrams only for a bounded flow or subsystem such as authentication, order creation, billing, or media ingest.

## 7. Evidence file template

Use a compact markdown table like this:

| source | action | target | evidence | confidence |
| --- | --- | --- | --- | --- |
| `POST /orders` handler | `call` | `CreateOrderService` | `src/http/orders.ts:router.post -> createOrderHandler` | confirmed |
| `CreateOrderService` | `publish OrderCreated` | `orders` topic | `src/orders/service.ts:publishOrderCreated(...)` | confirmed |
| `OrderConsumer` | `write` | `billing` table | inferred from interface wiring in `src/billing/module.ts` | suspected |

Keep the evidence aligned to nodes and edge labels that actually appear in the diagram.
