---
name: debug-log-investigation
description: Use when diagnosing a code, runtime, UI, injection, async, or integration problem by tracing the real execution path with targeted debug logs, writing logs to fixed files, narrowing the failure step by step, and archiving the confirmed root cause into a fixed problem document.
---

# Debug Log Investigation

## Overview

Use this skill when a problem cannot be solved confidently from static reading alone and must be narrowed through runtime evidence.

The workflow is: define the problem, identify the shortest execution path, add targeted logs, reproduce once, narrow the failing segment, add finer logs only around that segment, confirm the root cause, verify the fix, and archive the issue in a fixed document for later review.

## When To Use

Use this skill for:

- runtime behavior that does not match the apparent code path
- UI problems where updates appear to run but the result is wrong
- async, callback, event, state, or cross-thread issues
- integration failures with external apps, windows, devices, SDKs, or services
- problems that require confirming which branch, state, handle, or return value is actually seen at runtime

Do not use this skill for:

- pure refactors with no bug
- straightforward syntax or compile errors that already point to a single line
- tasks where static code reading is already sufficient

## Workflow

1. Define the exact symptom, expected behavior, trigger steps, and impact.
2. Map the shortest execution path related to the symptom.
3. Read [references/debug-workflow.md](references/debug-workflow.md) and add first-pass skeleton logs only at path boundaries.
4. Write logs to fixed files using the rules in [references/logging-guidelines.md](references/logging-guidelines.md).
5. Reproduce once and determine where the path breaks or diverges.
6. Add second-pass detail logs only around the suspicious segment.
7. Continue narrowing until the root cause is proven by logs rather than guessed.
8. Fix the issue, rebuild, verify the actual loaded artifact, and reproduce again.
9. Remove or downgrade temporary logs that are no longer needed.
10. Archive the issue in a fixed document using [references/problem-log-template.md](references/problem-log-template.md).

## Fixed Archive Rule

After locating or fixing a problem, always update a fixed issue document in the current project.

Default path:

- `docs/problem-investigation-log.md`

If the project already has a dedicated issue log, append to that file instead of creating a second registry.

## References

- Full workflow: [references/debug-workflow.md](references/debug-workflow.md)
- Logging rules: [references/logging-guidelines.md](references/logging-guidelines.md)
- Archive template: [references/problem-log-template.md](references/problem-log-template.md)
