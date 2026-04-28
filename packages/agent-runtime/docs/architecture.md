# Codex Runtime Architecture

This document is the architecture reference for `agent-runtime`.
It describes what exists today, why it is shaped this way, and where to extend it next.

## Goals

- Keep runtime behavior explicit and auditable.
- Keep permission checks deterministic and local.
- Keep session state portable and bounded.
- Keep tool integration simple enough to add safely.

## Current System Shape

```text
CLI (src/index.ts)
  -> AgentRuntime (src/core/runtime.ts)
    -> Tool Registry (src/tools/index.ts)
      -> Tool Permission Check
      -> Tool Execution
  -> Session Store (src/sessions/store.ts)
    -> JSONL event log
    -> Snapshot metadata
```

Runtime is intentionally thin:
- `AgentRuntime` handles dispatch + permission gating.
- Tools own their own input handling and execution behavior.
- `src/index.ts` owns startup orchestration and top-level command dispatch.
- `src/commands/*` owns user-facing command behavior.

Startup split:
- `src/entrypoints/startup/entrypoint.ts` initializes runtime entrypoint mode (`cli` vs `script`).
- `src/entrypoints/startup/settings-loader.ts` eagerly parses startup flags (`--root-dir`).
- `src/entrypoints/startup/pending-connections.ts` detects early session transfer intent.

## Core Modules

### `src/core/contracts.ts`
Defines stable interfaces:
- `Tool`, `ToolInput`, `ToolResult`, `ToolExecutionContext`
- JSON-safe value shapes for persisted output

This is the contract boundary. New capabilities should conform here first.

### `src/core/runtime.ts`
Single responsibility:
- resolve tool by name
- run `checkPermission()`
- run tool if allowed

No hidden side effects. Runtime does not persist state directly.

### `src/tools/*`
Current tools:
- `read` — UTF-8 file read, rootDir-confined
- `glob` — file listing via fast-glob, rootDir-confined
- `bash` — subprocess execution via execFile, prefix-allowlisted
- `switchboard.route` — delegates to Switchboard Python CLI (requires `ECOSYSTEM_ROOT`)
- `mythos` — HTTP client to the local Mythos service (requires `ECOSYSTEM_ROOT`, port via `MYTHOS_PORT`)
- `pantheon.route` — Switchboard with `--force-agent pantheon` (requires `ECOSYSTEM_ROOT`)

Shared helpers:
- `src/tools/parseJsonStream.ts` — parses concatenated JSON values from subprocess stdout
- `src/tools/ecosystemRoot.ts` — resolves and validates `ECOSYSTEM_ROOT` at invocation time

### `src/permissions/engine.ts`
Central policy helpers:
- `isPathInsideRoot()` for root confinement
- `isAllowedBashPrefix()` for command prefix allowlisting

Default shell capability is intentionally narrow.

### `src/sessions/store.ts`
Persistence model:
- `.agent-runtime/sessions/<id>.jsonl` for append-only events
- `.agent-runtime/snapshots/<id>.json` for session metadata

Features:
- create/list/show/resume/delete/prune
- export/import bundles
- `--force` overwrite during import
- result truncation to keep logs bounded

Storage safety:
- event payloads are JSON
- oversized tool results are clamped and annotated with `storageMeta`

## CLI Surface

Primary commands:
- `list-tools`
- `run <tool> '<json-input>'`
- `session create|list|show|resume|run|delete|prune|export|import`
- `meta report [target]`
- `mcts <subcommand>` — proxies to ADA 03 engine (requires `ADA_ENGINE_DIR`)
- `alphamu <subcommand>` — proxies to AlphaMu Python engine (requires `ALPHAMU_PATH`)
- global startup flag: `--root-dir <path>`

Entrypoint is `src/index.ts`, with command handlers in:
- `src/commands/run.ts`
- `src/commands/meta.ts`
- `src/commands/session.ts`
- `src/commands/usage.ts`

Behavior is designed to be scriptable and machine-readable via JSON output.

## Data Model

### Session Event
- type: `tool_run`
- fields: tool name, input, result, timestamp, id
- optional `storageMeta` when truncation occurs

### Session Snapshot
- `sessionId`
- `createdAt`, `updatedAt`
- `eventCount`
- `lastEventType`

Export format is versioned (`version: 1`) for forward compatibility.

## Design Decisions

1. JSONL + snapshot over DB
- easy local inspection
- low operational overhead
- enough structure for replay and export

2. Runtime-level permission gate
- consistent deny behavior across tools
- tools cannot bypass policy accidentally

3. Explicit CLI command model
- easy to test end-to-end
- easy to embed in external scripts

## Known Gaps

- No schema validator for CLI JSON input beyond runtime/tool checks.
- No multi-event types beyond `tool_run`.
- No partial session merge strategy on import.
- No integrity checksum for export bundles.
- `detectPendingSessionTransfer` sets `AGENT_RUNTIME_PENDING_TRANSFER` but nothing reads it yet (see TODO in `pending-connections.ts`).

## Extension Plan

### Near term
- Add `session verify` (bundle integrity + schema checks).
- Add structured error codes in `ToolResult`.
- Expose `--timeout` CLI flag to set `defaultTimeoutMs` on the runtime.

### Mid term
- Introduce `event.type` variants (`note`, `decision`, `system`).
- Add permission profiles (strict, dev, ci).
- Add optional compressed archives for large session exports.

### Long term
- Add deterministic replay runner from session log.
- Add policy audit log to explain allow/deny decisions.
- Add multi-runtime federation (shared import/export protocol).

## Contribution Rules

- Keep `runtime.ts` small; avoid business logic there.
- Add new tool behavior inside tool modules, not CLI branches.
- Any permission expansion must update `permissions/engine.ts` and docs.
- Any session format change must preserve or migrate existing exports.

## Quick File Map

- `src/index.ts`: startup orchestration and command dispatch
- `src/commands/`: command handlers (`run`, `meta`, `session`, `mcts`, `alphamu`, `usage`)
- `src/entrypoints/startup/`: startup entrypoint/settings/pending state helpers
- `src/core/contracts.ts`: shared interfaces
- `src/core/runtime.ts`: runtime dispatcher
- `src/tools/`: tool implementations + shared helpers (`parseJsonStream`, `ecosystemRoot`)
- `src/permissions/engine.ts`: policy helpers
- `src/sessions/store.ts`: session persistence
