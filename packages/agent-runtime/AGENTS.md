# AGENTS.md

Operating rules for AI agents and automated tools working on this repository.

## Repository Contract

This is a **minimal local agent runtime** — a thin CLI that wires tool execution, session
persistence, and external engine bridges together. Keep it thin. Resist adding abstraction
layers unless they eliminate duplication across three or more call sites.

## Definition of Done

A change is complete when all three pass locally:

```bash
npm run typecheck
npm run build
npm test
```

CI enforces this automatically on every push and pull request.

## Code Rules

- **No `any` types.** Use `unknown` + narrowing or add a typed interface.
- **No `@ts-ignore` or `@ts-expect-error`.** Fix the underlying type, not the error.
- **ESM-only.** All imports must include the `.js` extension (NodeNext resolution).
- **`const` over `let`** unless mutation is necessary.
- **No hardcoded user paths.** Use environment variables with a clear startup error when
  unset (see `src/commands/mcts.ts` for the pattern).

## Tool & Permission Rules

- All tools must honour `context.rootDir` — never read/write outside it.
- All tools must call `checkPermission` before performing any filesystem or shell action.
- `ToolExecutionContext.timeoutMs` must be wired through to any subprocess call.
- JSONL-backed stores must use per-line `try/catch` so one corrupt record never aborts a
  full read.

## Session Store

- Session files live in `.agent-runtime/sessions/<id>.jsonl` and `.agent-runtime/snapshots/<id>.json`.
- Never commit `.agent-runtime/` to the repo — it is gitignored.
- The `MAX_STORED_RESULT_CHARS = 8_000` limit in `store.ts` is intentional. Do not raise it
  without measuring p99 session file size first.

## Adding a New Tool

1. Create `src/tools/<toolName>Tool.ts` implementing `Tool`.
2. Register it in `src/tools/index.ts` by adding an entry to the `TOOLS` record.
3. Add a permission entry in `src/permissions/engine.ts` if the tool uses the bash allowlist or path confinement.
4. Write at least one integration test in `src/tests/`.

## Adding a New Command

1. Create `src/commands/<name>.ts` exporting `handle<Name>Command`.
2. Wire it into `src/index.ts` with an `if (command === "<name>")` branch.
3. Add usage text to `src/commands/usage.ts`.

## External Engine Bridges (`mcts`, `alphamu`, `switchboard.route`, `mythos`, `pantheon.route`)

The `mcts` and `alphamu` commands shell out to separate processes and bypass `AgentRuntime` entirely.
They require environment variables (`ADA_ENGINE_DIR`, `ALPHAMU_PATH`) to be set.

The `switchboard.route`, `mythos`, and `pantheon.route` tools require `ECOSYSTEM_ROOT` to be set.
`mythos` additionally respects `MYTHOS_PORT` (default: `3847`) to locate the Mythos HTTP service.

Do not add fallback paths — fail fast with a descriptive error.

## What This Repo Is Not

- Not a framework. Do not expose a plugin API.
- Not an HTTP server. The `run` command is the API surface.
- Not a persistent daemon. Each invocation is stateless at the process level; state lives in
  session files.

## Speculative / Incomplete Features

- `detectPendingSessionTransfer` in `src/entrypoints/startup/pending-connections.ts`:
  sets `AGENT_RUNTIME_PENDING_TRANSFER` but nothing reads it yet. See the TODO comment in
  that file before extending this pattern.
