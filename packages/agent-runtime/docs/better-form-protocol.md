# Better-Form Protocol

This protocol defines how we change `agent-runtime` safely and consistently.

## Principles

- Preserve behavior unless the task explicitly changes behavior.
- Prefer small, composable modules over growth in `src/index.ts`.
- Keep tool execution deterministic and permission-gated.
- Keep session persistence portable and bounded.

## Change Flow

1. Explore current shape (`src/index.ts`, `src/core/*`, `src/sessions/*`, `src/entrypoints/startup/*`).
2. Define the smallest acceptable change set.
3. Implement in dependency order.
4. Verify with:
   - `npm run typecheck`
   - `npm run build`
5. Update docs when CLI behavior, persistence format, or permission behavior changes.

## Boundaries

- `src/core/runtime.ts`: dispatch + permission gate only.
- `src/tools/*`: tool-specific parsing/execution.
- `src/permissions/engine.ts`: policy logic only.
- `src/sessions/store.ts`: persistence model only.
- `src/entrypoints/startup/*`: startup concerns only.
- `src/index.ts`: command routing and orchestration.

## Definition of Done

- Typecheck/build pass.
- No partial command wiring.
- Usage text matches real command behavior.
- Architecture docs reflect new behavior.

