# Main Entrypoint Refactor Plan (`src/index.ts`)

## Current State

- `src/index.ts` owns startup loading, CLI routing, meta reporting, and session command handling.
- Startup concerns have been extracted to `src/entrypoints/startup/`.

## Phases

### Phase 1: Startup Extraction

- [x] `pending-connections.ts`
- [x] `entrypoint.ts`
- [x] `settings-loader.ts`
- [x] `prefetch.ts`

### Phase 2: Command Router Split

Goal: reduce `src/index.ts` responsibility by moving command handling into modules.

Proposed files:

- `src/commands/meta.ts` ✅
- `src/commands/session.ts` ✅
- `src/commands/run.ts` ✅
- `src/commands/usage.ts` ✅

Status:
- [x] `meta`, `session`, and `run` extracted from `src/index.ts`
- [x] `usage` extracted from `src/index.ts`

### Phase 3: Validation and Error Model

Goal: standardize command failures.

- Add structured error payload shape.
- Normalize unknown-command and invalid-arg responses.
- Ensure non-zero exit codes are consistent across commands.

### Phase 4: Session Verification Command

Goal: add `session verify`.

- Validate import bundle shape/version.
- Validate snapshot/event consistency.
- Return machine-readable validation result.

## Verification Gate

After each phase:

- `npm run typecheck`
- `npm run build`
- spot-check command behavior with `node dist/index.js ...`

## Success Metrics

- Smaller `src/index.ts` with clearer orchestration-only role.
- Command modules become independently testable.
- No behavior regressions in existing CLI commands.
- Docs remain aligned with runtime behavior.
