# Agent Runtime

```
    ___       __                        __   _                     __
   /   | ____/ /   _____  _______  ____/ /  (_)___  ____  ___     / /_
  / /| |/ __  / | / / _ \/ ___/ / / / __/  / / __ \/ __ \/ _ \   / __/
 / ___ / /_/ /| |/ /  __/ /  / /_/ / /_   / / /_/ / / / /  __/  / /_
/_/  |_\__,_/ |___/\___/_/   \__,_/\__/  /_/ .___/_/ /_/\___/   \__/
                                          /_/
```

[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Node](https://img.shields.io/badge/Node-20+-green.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-21+-green.svg)](src/tests)

A minimal, auditable local agent runtime with tool execution, session persistence, and MCTS/ADA engine integration.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                         AGENT RUNTIME ARCHITECTURE                              │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────────────┐  │
│  │   Input     │───▶│   Parser    │───▶│        Command Router               │  │
│  │   (CLI)     │    │  (args)     │    │                                     │  │
│  └─────────────┘    └─────────────┘    └──────────┬──────────────────────────┘  │
│                                                    │                            │
│                       ┌────────────────────────────┼────────────────────────┐   │
│                       │                            │                        │   │
│           ┌───────────▼──────────┐    ┌────────────▼─────────┐   ┌──────────▼─┐│
│           │   Tool Execution     │    │   Session Manager    │   │   Engine   ││
│           │                      │    │                      │   │   Bridges  ││
│           │  • read              │    │  • create/list       │   │            ││
│           │  • glob              │    │  • show/resume       │   │  • MCTS    ││
│           │  • bash (allowlist)  │    │  • export/import     │   │  • AlphaMu ││
│           │  • switchboard.route │    │  • run with logging  │   │            ││
│           │  • mythos            │    │                      │   │            ││
│           │  • pantheon.route    │    │                      │   │            ││
│           └──────────────────────┘    └──────────────────────┘   └────────────┘│
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Architecture reference: [`docs/architecture.md`](docs/architecture.md)

## Quick Start

```bash
npm install
npm run build

# List available tools
node dist/index.js list-tools

# Execute a tool
node dist/index.js run read '{"path":"README.md"}'
node dist/index.js run glob '{"pattern":"src/**/*.ts"}'

# Check version
node dist/index.js version

# Get runtime health/status
node dist/index.js status
```

---

## Core Commands

### `list-tools`
Print all registered tools as JSON, including contract metadata:
- `name`
- `description`
- `contractVersion`
- `inputSchema`
- `outputSchema`
- `permissionSummary`
- `exampleInput`

```bash
node dist/index.js list-tools
```

---

### `run <tool> '<json-input>'`
Execute a registered tool by name with a JSON input object. Prints the `ToolResult` as JSON and exits non-zero on failure.

```bash
node dist/index.js run read '{"path":"src/index.ts"}'
node dist/index.js run glob '{"pattern":"src/**/*.ts"}'
node dist/index.js run bash '{"cmd":"git","args":["status","--short"]}'
```

**Available tools:**

| Tool | Input | Description |
|------|-------|-------------|
| `read` | `{ "path": "<file>" }` | Read a UTF-8 file. Path must be inside `rootDir`. |
| `glob` | `{ "pattern": "<glob>" }` | List files matching a glob under `rootDir`. |
| `bash` | `{ "cmd": "<cmd>", "args": [...] }` | Run a command from the prefix allowlist (see [Permissions](#permissions)). |
| `switchboard.route` | `{ "input": "<prompt>" }` | Route a task through Switchboard. |
| `mythos` | `{ "prompt": "<prompt>" }` | Call the Mythos API bridge. |
| `pantheon.route` | `{ "input": "<prompt>" }` | Route a task to Pantheon through Switchboard. |

---

### `meta report [target]`
Emit a JSON diagnostic snapshot: runtime name/version, loaded tools, session counts, and startup prefetch state. `target` defaults to `"agent-runtime"`.

```bash
node dist/index.js meta report
node dist/index.js meta report my-project
```

---

### `version`
Print version information for the agent runtime.

```bash
node dist/index.js version
```

---

### `status`
Print runtime health status including tool registry state, session storage, and telemetry metrics.

```bash
node dist/index.js status
```

---

## Session Commands

Sessions are append-only JSONL event logs stored under `.agent-runtime/sessions/`. Each session has a snapshot (`createdAt`, `updatedAt`, `eventCount`) for fast listing without replaying the full log.

### `session create [session-id]`
Create a new session. If `session-id` is omitted, one is auto-generated.

```bash
node dist/index.js session create
node dist/index.js session create dev-loop
```

### `session list`
List all sessions with snapshot metadata.

```bash
node dist/index.js session list
```

### `session show <session-id> [limit]`
Print the session snapshot and its full event log. `limit` caps the number of events returned.

```bash
node dist/index.js session show dev-loop
node dist/index.js session show dev-loop 20
```

### `session resume <session-id>`
Print a summary and the last 5 events — designed for resuming a previous work context quickly.

```bash
node dist/index.js session resume dev-loop
```

### `session run <session-id> <tool> '<json-input>'`
Execute a tool within a session. The result is appended to the session log and the updated snapshot is returned.

```bash
node dist/index.js session run dev-loop read '{"path":"README.md"}'
node dist/index.js session run dev-loop glob '{"pattern":"src/**/*.ts"}'
```

### `session delete <session-id>`
Permanently delete a session and its event log. Exits non-zero if the session does not exist.

```bash
node dist/index.js session delete dev-loop
```

### `session prune <keep-count>`
Delete all sessions except the most recent `<keep-count>`. Pass `0` to delete all.

```bash
node dist/index.js session prune 10
node dist/index.js session prune 0
```

### `session export <session-id> [output-file]`
Export a session to a versioned JSON bundle (`version: 1`). Prints to stdout if `output-file` is omitted.

```bash
node dist/index.js session export dev-loop
node dist/index.js session export dev-loop ./dev-loop.session.json
```

### `session import <input-file> [session-id] [--force]`
Import a session bundle. Optionally provide a new `session-id` to rename it on import. Use `--force` to overwrite an existing session with the same ID.

```bash
node dist/index.js session import ./dev-loop.session.json
node dist/index.js session import ./dev-loop.session.json dev-loop-copy
node dist/index.js session import ./dev-loop.session.json dev-loop --force
```

---

## MCTS / ADA engine commands

All `mcts` subcommands are forwarded to the ADA 03 engine via `npx tsx src/index.ts`. The engine directory defaults to `/Users/jm1/Projects/Foundry/ADA 03` and can be overridden with the `ADA_ENGINE_DIR` environment variable.

```bash
ADA_ENGINE_DIR="/path/to/ADA 03" node dist/index.js mcts status
```

### `mcts memory recall`
Load the engine's startup recall context — the memory entries surfaced at session init.

```bash
node dist/index.js mcts memory recall
```

### `mcts memory append`
Append a new entry to the engine memory store.

```bash
node dist/index.js mcts memory append --tags "auth,jwt" --body "JWT refresh token impl notes"
```

### `mcts memory search`
Search memory entries by semantic query or tag filter.

```bash
node dist/index.js mcts memory search --query "auth JWT" --limit 5
node dist/index.js mcts memory search --tags "coder,typescript"
```

### `mcts trimmer analyze "<prompt>" [--json]`
Classify a prompt into a task tier: `fast`, `smart`, or `deep`. Use `--json` for structured output suitable for piping.

```bash
node dist/index.js mcts trimmer analyze "fix a typo in README"
node dist/index.js mcts trimmer analyze "implement distributed rate limiting" --json
```

### `mcts select [options]`
Run MCTS model selection with learned PUCT priors and transposition table. Returns the selected model, UCB-like score, per-dimension value estimates, and a ranked alternatives list.

```bash
node dist/index.js mcts select --prompt "build a REST API" --framework coder --language typescript
node dist/index.js mcts select --action forge --framework react
```

| Flag | Description |
|------|-------------|
| `--prompt "<text>"` | Task description used for semantic fingerprinting |
| `--framework <fw>` | Target framework (e.g. `coder`, `react`, `nextjs`) |
| `--language <lang>` | Target language (e.g. `typescript`, `python`) |

### `mcts agents select [options]`
Run ensemble agent negotiation using a `weighted_vote` strategy across registered agents (speed-specialist, quality-maximizer, cost-optimizer). Returns the winning model, per-agent votes, and worker contracts.

```bash
node dist/index.js mcts agents select --prompt "refactor auth module" --language typescript
```

### `mcts compare <modelA> <modelB> [options]`
Head-to-head comparison of two models on a task. Returns relative quality, cost, and latency estimates.

```bash
node dist/index.js mcts compare claude-sonnet-4-6 gemini-2.5-pro --prompt "implement JWT refresh" --framework coder
```

### `mcts score [options]`
Record a quality score for a model/action pair. Scores accumulate and shift future `select` decisions after the next `train` run.

```bash
node dist/index.js mcts score --model claude-sonnet-4-6 --score 0.9 --outcome success
node dist/index.js mcts score --model gemini-2.5-pro --score 0.7 --outcome success \
  --framework coder --language typescript --session-id run1
```

| Flag | Description |
|------|-------------|
| `--model <model>` | Model ID or `auto` |
| `--score <0.0–1.0>` | Quality score |
| `--outcome <success\|failure>` | Outcome label |
| `--framework <fw>` | Optional framework context |
| `--language <lang>` | Optional language context |
| `--session-id <id>` | Optional session correlation ID |

### `mcts train`
Retrain MCTS routing priors from all recorded score events on disk. Synthetic/test entries are filtered before training. Run this after accumulating new scores to update selection weights.

```bash
node dist/index.js mcts train
```

### `mcts run --prompt "<text>" [options]`
Execute the full ADA pipeline: select a model, run the task, record a score.

```bash
node dist/index.js mcts run --prompt "implement a rate limiter" --framework coder --language typescript
```

### `mcts status [--neural]`
Print engine health: loaded adapters, prior scores per model/action pair, transposition table stats, and active configuration. Add `--neural` for model weight diagnostics.

```bash
node dist/index.js mcts status
node dist/index.js mcts status --neural
```

---

## AlphaMu commands

All `alphamu` subcommands are forwarded to the AlphaMu Python engine via `python -m engine`. The engine directory defaults to `/Users/jm1/Projects/Foundry/alphamu-engine` and can be overridden with the `ALPHAMU_PATH` environment variable. All commands return JSON to stdout; progress is logged to stderr.

```bash
ALPHAMU_PATH="/path/to/alphamu-engine" node dist/index.js alphamu selfplay
```

### `alphamu selfplay [options]`
Run self-play episodes using MCTS + a policy/value network.

```bash
node dist/index.js alphamu selfplay --episodes 20 --simulations 100
node dist/index.js alphamu selfplay --backend mu_zero --game stub --episodes 50
```

| Flag | Default | Description |
|------|---------|-------------|
| `--backend` | `alpha_zero` | `alpha_zero` or `mu_zero` |
| `--game` | `tictactoe` | `tictactoe` (9 actions) or `stub` (4 actions) |
| `--episodes` | `10` | Number of self-play games |
| `--simulations` | `50` | MCTS simulations per move |

### `alphamu train [options]`
Train the policy+value network. Loads `model.json` if present; saves on completion.

```bash
node dist/index.js alphamu train --steps 200 --batch-size 64
node dist/index.js alphamu train --backend mu_zero --steps 500
```

| Flag | Default | Description |
|------|---------|-------------|
| `--backend` | `alpha_zero` | Network backend |
| `--game` | `tictactoe` | Game environment |
| `--steps` | `100` | Training steps |
| `--batch-size` | `32` | Batch size per step |

### `alphamu eval [options]`
Evaluate a trained network in greedy play (temperature = 0). Returns win/loss/draw counts and win rate.

```bash
node dist/index.js alphamu eval --episodes 100
node dist/index.js alphamu eval --backend mu_zero --checkpoint ./model_mz.json --episodes 50
```

### `alphamu arena [options]`
Head-to-head match between AlphaZero and MuZero backends. Loads `model_az.json` and `model_mz.json` from the engine directory if available.

```bash
node dist/index.js alphamu arena --games 50
node dist/index.js alphamu arena --backend-a alpha_zero --backend-b mu_zero --games 100
```

---

## Global flag

`--root-dir <path>` sets the runtime root for file operations and session storage. Defaults to `process.cwd()`. Can be passed before any command.

```bash
node dist/index.js --root-dir /tmp/sandbox run read '{"path":"notes.txt"}'
node dist/index.js --root-dir /tmp/sandbox session create test-session
```

---

## Permissions

**`bash`** is guarded by a prefix allowlist in `src/permissions/engine.ts`. Only the following command prefixes are permitted by default:

| Command | Allowed forms |
|---------|--------------|
| `git` | `git status`, `git diff`, `git log` |
| `npm` | `npm test`, `npm run typecheck` |

Any other command or prefix is denied at the permission layer before execution. To expand the allowlist, update `BASH_ALLOW_PREFIXES` in `src/permissions/engine.ts`.

**`read`** and **`glob`** are restricted to paths resolved inside `rootDir`. Paths that escape via `../` are denied.

---

## Development

```bash
npm run typecheck   # type-check without building
npm run build       # compile to dist/
npm test            # run all tests
```

Build artifacts go to `dist/` and are gitignored. Session data is stored under `.agent-runtime/` and is also gitignored.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADA_ENGINE_DIR` | `/Users/jm1/Projects/Foundry/ADA 03` | Path to ADA engine |
| `ALPHAMU_PATH` | `/Users/jm1/Projects/Foundry/alphamu-engine` | Path to AlphaMu engine |
| `ECOSYSTEM_ROOT` | — | Path to ecosystem root |
| `MYTHOS_PORT` | `3847` | Mythos HTTP service port |
| `SWITCHBOARD_OFFLINE` | — | Set to `1` to force offline mode |

---

## Telemetry

The runtime includes a built-in telemetry system for monitoring tool executions and session operations. Metrics are collected in-memory and can be exported in Prometheus format.

### Recording Metrics

```typescript
import { getTelemetry } from "./telemetry.js"

const telemetry = getTelemetry()

// Record a tool execution
telemetry.recordToolExecution("read", 150, true)  // name, latencyMs, success

// Record a session operation
telemetry.recordSessionOperation("create", 50)  // operation, latencyMs
```

### Exporting Metrics

```typescript
// Get structured metrics
const metrics = telemetry.getMetrics()

// Export as Prometheus format
const prometheus = telemetry.formatPrometheus()
// # HELP agent_runtime_tool_executions_total Total tool executions
// # TYPE agent_runtime_tool_executions_total counter
// agent_runtime_tool_executions_total{tool="read",status="success"} 5
```

### Available Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_runtime_tool_executions_total` | Counter | `tool`, `status` | Total tool executions by name and success/failure |
| `agent_runtime_session_operations_total` | Counter | `operation` | Total session operations by type |
| `agent_runtime_tool_latency_seconds` | Histogram | — | Tool execution latency buckets |

---

## API Documentation

See [`API.md`](API.md) for detailed API documentation of the core interfaces, tools, and session management.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for detailed architecture documentation.

---

## License

MIT License - Copyright 2026 Human Systems
