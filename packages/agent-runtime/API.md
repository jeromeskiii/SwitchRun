# Agent Runtime API Documentation

**Agent Runtime v0.1.0** - Minimal, auditable local agent runtime

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Contracts](#contracts)
3. [AgentRuntime](#agentruntime)
4. [Tools](#tools)
5. [Permissions](#permissions)
6. [Session Store](#session-store)
7. [Commands](#commands)
8. [Telemetry](#telemetry)

---

## Core Concepts

### Architecture

The Agent Runtime follows a minimal, auditable design with these layers:

```
CLI Input → Command Router → Tool/Session/Engine Handler → Result (JSON)
```

Key principles:
- **Stateless processes**: Each invocation is independent
- **JSON I/O**: All tools return structured JSON
- **Permission-first**: All filesystem/shell operations are permission-gated
- **Append-only sessions**: Event logs are never modified, only appended

### Tool Contract

Every tool implements the `Tool` interface with:
- Metadata (name, description, version, schemas)
- Permission checking (`checkPermission`)
- Execution (`run`)

---

## Contracts

### JsonValue

```typescript
type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [k: string]: JsonValue }
```

### ToolInput

```typescript
type ToolInput = { [k: string]: JsonValue }
```

### ToolExecutionContext

```typescript
type ToolExecutionContext = {
  rootDir: string
  timeoutMs?: number  // Per-tool execution timeout
}
```

### ToolResult

```typescript
type ToolResult = {
  ok: boolean
  data?: JsonValue
  error?: string
}
```

### ToolPermissionDecision

```typescript
type ToolPermissionDecision = {
  allowed: boolean
  reason: string
}
```

### ToolJsonSchema

```typescript
type ToolJsonSchema = {
  type: "string" | "number" | "boolean" | "array" | "object"
  description: string
  required?: string[]
  items?: ToolJsonSchema
  properties?: Record<string, ToolJsonSchema>
}
```

### ToolListEntry

```typescript
type ToolListEntry = {
  name: string
  description: string
  contractVersion: number
  inputSchema: ToolJsonSchema
  outputSchema: ToolJsonSchema
  permissionSummary: string
  exampleInput?: ToolInput
}
```

### Tool Interface

```typescript
interface Tool {
  readonly name: string
  readonly description: string
  readonly contractVersion: number
  readonly inputSchema: ToolJsonSchema
  readonly outputSchema: ToolJsonSchema
  readonly permissionSummary: string
  readonly exampleInput?: ToolInput
  
  checkPermission(
    input: ToolInput,
    context: ToolExecutionContext,
  ): ToolPermissionDecision
  
  run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult>
}
```

---

## AgentRuntime

```typescript
import { AgentRuntime } from "./core/runtime.js"

const runtime = new AgentRuntime({ rootDir: "/path/to/project" })
```

### Constructor Options

```typescript
type RuntimeOptions = {
  rootDir: string           // Root directory for file operations
  defaultTimeoutMs?: number // Default timeout for tool execution
}
```

### Methods

#### `listTools(): ToolListEntry[]`

Returns metadata for all registered tools.

```typescript
const tools = runtime.listTools()
// [{ name: "read", description: "...", contractVersion: 1, ... }]
```

#### `runTool(toolName: string, input: ToolInput, options?: RunToolOptions): Promise<ToolResult>`

Execute a tool with the given input.

```typescript
const result = await runtime.runTool("read", { path: "README.md" })
// { ok: true, data: "# Project Name..." }
```

Options:
```typescript
type RunToolOptions = {
  timeoutMs?: number  // Override default timeout
}
```

---

## Tools

### ReadTool

Read a UTF-8 file from disk.

```typescript
const result = await runtime.runTool("read", { path: "src/index.ts" })
```

**Input Schema:**
```json
{
  "path": "string"  // Path relative to rootDir
}
```

**Output Schema:**
```json
{
  "type": "string"  // File content
}
```

**Permissions:** Denies absolute paths and parent-escape (`../`) paths outside rootDir.

---

### GlobTool

List files matching a glob pattern.

```typescript
const result = await runtime.runTool("glob", { pattern: "src/**/*.ts" })
```

**Input Schema:**
```json
{
  "pattern": "string"  // Glob pattern relative to rootDir
}
```

**Output Schema:**
```json
{
  "type": "array",
  "items": { "type": "string" }  // Array of file paths
}
```

**Permissions:** Denies absolute paths and patterns containing `..` segments.

---

### BashTool

Execute a constrained command.

```typescript
const result = await runtime.runTool("bash", {
  cmd: "git",
  args: ["status", "--short"]
})
```

**Input Schema:**
```json
{
  "cmd": "string",    // Executable name
  "args": ["string"]  // Optional arguments
}
```

**Output Schema:**
```json
{
  "stdout": "string",
  "stderr": "string"
}
```

**Permissions:** Only allows command prefixes defined in `BASH_ALLOW_PREFIXES`.

Default allowed prefixes:
- `git status`, `git diff`, `git log`
- `npm test`, `npm run typecheck`

---

### SwitchboardRouteTool

Route a task through Switchboard.

```typescript
const result = await runtime.runTool("switchboard.route", {
  input: "analyze this codebase"
})
```

**Input Schema:**
```json
{
  "input": "string"  // Task prompt
}
```

**Permissions:** Requires `ECOSYSTEM_ROOT` environment variable.

---

### MythosTool

Call the Mythos API bridge.

```typescript
const result = await runtime.runTool("mythos", {
  prompt: "implement a rate limiter"
})
```

**Input Schema:**
```json
{
  "prompt": "string"  // Task prompt
}
```

**Permissions:** Requires `ECOSYSTEM_ROOT` environment variable. Uses `MYTHOS_PORT` (default: 3847).

---

### PantheonRouteTool

Route a task to Pantheon through Switchboard.

```typescript
const result = await runtime.runTool("pantheon.route", {
  input: "route to pantheon"
})
```

**Input Schema:**
```json
{
  "input": "string"  // Task prompt
}
```

**Permissions:** Requires `ECOSYSTEM_ROOT` environment variable.

---

## Permissions

### BASH_ALLOW_PREFIXES

```typescript
export const BASH_ALLOW_PREFIXES: Array<[string, ...string[]]> = [
  ["git", "status"],
  ["git", "diff"],
  ["git", "log"],
  ["npm", "test"],
  ["npm", "run", "typecheck"],
]
```

### isPathInsideRoot(rootDir: string, filePath: string): boolean

Check if a path is contained within rootDir.

```typescript
import { isPathInsideRoot } from "./permissions/engine.js"

const allowed = isPathInsideRoot("/project", "src/index.ts")  // true
const denied = isPathInsideRoot("/project", "../etc/passwd")  // false
```

### isAllowedBashPrefix(cmd: string, args: string[]): boolean

Check if a command is in the allowlist.

```typescript
import { isAllowedBashPrefix } from "./permissions/engine.js"

const allowed = isAllowedBashPrefix("git", ["status"])  // true
const denied = isAllowedBashPrefix("rm", ["-rf", "/"])  // false
```

---

## Session Store

### SessionEvent

```typescript
type SessionEvent = {
  id: string
  sessionId: string
  timestamp: string
  type: "tool_run"
  payload: {
    toolName: string
    input: ToolInput
    result: ToolResult
    storageMeta?: {
      resultTruncated: boolean
      originalChars: number
      storedChars: number
    }
  }
}
```

### SessionSnapshot

```typescript
type SessionSnapshot = {
  sessionId: string
  createdAt: string
  updatedAt: string
  eventCount: number
  lastEventType: SessionEvent["type"] | null
}
```

### SessionExportBundle

```typescript
type SessionExportBundle = {
  version: 1
  exportedAt: string
  snapshot: SessionSnapshot
  events: SessionEvent[]
}
```

### Functions

#### `createSession(rootDir: string, sessionId?: string): Promise<SessionSnapshot>`

Create a new session. Auto-generates UUID if sessionId omitted.

```typescript
import { createSession } from "./sessions/store.js"

const snapshot = await createSession("/project", "my-session")
```

#### `appendSessionEvent(rootDir: string, event: SessionEvent): Promise<SessionSnapshot>`

Append an event to a session and update its snapshot.

```typescript
import { appendSessionEvent, createToolRunEvent } from "./sessions/store.js"

const event = createToolRunEvent(
  "my-session",
  "read",
  { path: "README.md" },
  { ok: true, data: "content" }
)
const updated = await appendSessionEvent("/project", event)
```

#### `listSessions(rootDir: string): Promise<SessionSnapshot[]>`

List all sessions sorted by `updatedAt` descending.

```typescript
const sessions = await listSessions("/project")
```

#### `getSessionSnapshot(rootDir: string, sessionId: string): Promise<SessionSnapshot | null>`

Get a single session's snapshot.

```typescript
const snapshot = await getSessionSnapshot("/project", "my-session")
```

#### `readSessionEvents(rootDir: string, sessionId: string, limit?: number): Promise<SessionEvent[]>`

Read events from a session. Limit caps from the tail.

```typescript
const events = await readSessionEvents("/project", "my-session", 10)
```

#### `deleteSession(rootDir: string, sessionId: string): Promise<boolean>`

Delete a session. Returns false if not found.

```typescript
const removed = await deleteSession("/project", "my-session")
```

#### `pruneSessions(rootDir: string, keep: number): Promise<{ kept: number; deleted: string[] }>`

Keep only the N most recent sessions.

```typescript
const result = await pruneSessions("/project", 10)
// { kept: 10, deleted: ["old-session-1", "old-session-2"] }
```

#### `exportSessionBundle(rootDir: string, sessionId: string): Promise<SessionExportBundle>`

Export a session for migration/backup.

```typescript
const bundle = await exportSessionBundle("/project", "my-session")
```

#### `importSessionBundle(rootDir: string, bundle: SessionExportBundle, sessionIdOverride?: string, options?: { force?: boolean }): Promise<SessionSnapshot>`

Import a session bundle.

```typescript
const snapshot = await importSessionBundle("/project", bundle, "new-name", { force: true })
```

#### `summarizeSession(snapshot: SessionSnapshot, events: SessionEvent[]): JsonValue`

Create a human-readable summary of a session.

```typescript
const summary = summarizeSession(snapshot, events)
```

---

## Commands

### Usage

All commands follow this pattern:

```bash
node dist/index.js [global-flags] <command> [subcommand] [args]
```

Global flags:
- `--root-dir <path>`: Set runtime root (default: cwd)

### Command Handlers

#### handleRunCommand

```typescript
import { handleRunCommand } from "./commands/run.js"

await handleRunCommand(runtime, ["read", '{"path":"file.ts"}'], printUsage)
```

#### handleSessionCommand

```typescript
import { handleSessionCommand } from "./commands/session.js"

await handleSessionCommand(runtime, rootDir, ["create", "my-session"], printUsage)
```

#### handleMetaCommand

```typescript
import { handleMetaCommand } from "./commands/meta.js"

await handleMetaCommand(runtime, rootDir, ["report"], printUsage)
```

#### handleMctsCommand

```typescript
import { handleMctsCommand } from "./commands/mcts.js"

await handleMctsCommand(["status"], printUsage)
```

#### handleAlphamuCommand

```typescript
import { handleAlphamuCommand } from "./commands/alphamu.js"

await handleAlphamuCommand(["selfplay", "--episodes", "10"], printUsage)
```

---

## Telemetry

The runtime exposes telemetry for monitoring.

### RuntimeTelemetry

```typescript
import { RuntimeTelemetry } from "./telemetry.js"

const telemetry = new RuntimeTelemetry()

// Record tool execution
telemetry.recordToolExecution("read", 150, true)

// Record session operation
telemetry.recordSessionOperation("create", 50)

// Get metrics
const metrics = telemetry.getMetrics()
```

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `agent_runtime_tool_executions_total` | Counter | Tool executions by name and status |
| `agent_runtime_session_operations_total` | Counter | Session operations by type |
| `agent_runtime_tool_latency_seconds` | Histogram | Tool execution latency |

---

## Error Handling

All errors are returned as `ToolResult` with `ok: false`:

```typescript
const result = await runtime.runTool("read", { path: "../secret.txt" })
// { ok: false, error: "permission denied: path is outside rootDir" }
```

Common error patterns:
- `unknown tool: <name>` — Tool not registered
- `permission denied: <reason>` — Permission check failed
- `input.<field> must be a <type>` — Input validation failed
- File system errors — Passed through from underlying operations

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADA_ENGINE_DIR` | No | `/Users/jm1/Projects/Foundry/ADA 03` | ADA engine path |
| `ALPHAMU_PATH` | No | `/Users/jm1/Projects/Foundry/alphamu-engine` | AlphaMu engine path |
| `ECOSYSTEM_ROOT` | Yes* | — | Ecosystem root for routing tools |
| `MYTHOS_PORT` | No | `3847` | Mythos service port |
| `SWITCHBOARD_OFFLINE` | No | — | Set to `1` for offline mode |

*Required for `switchboard.route`, `mythos`, and `pantheon.route` tools.

---

## Examples

### Basic Tool Execution

```typescript
import { AgentRuntime } from "./core/runtime.js"

const runtime = new AgentRuntime({ rootDir: "/project" })

// Read a file
const readResult = await runtime.runTool("read", { path: "package.json" })
if (readResult.ok) {
  const pkg = JSON.parse(readResult.data as string)
  console.log(pkg.name)
}

// List files
const globResult = await runtime.runTool("glob", { pattern: "src/**/*.ts" })
if (globResult.ok) {
  const files = globResult.data as string[]
  console.log(`Found ${files.length} TypeScript files`)
}
```

### Session Management

```typescript
import {
  createSession,
  createToolRunEvent,
  appendSessionEvent,
  listSessions,
} from "./sessions/store.js"

// Create session
const session = await createSession("/project", "dev-loop")

// Execute tool and log to session
const runtime = new AgentRuntime({ rootDir: "/project" })
const result = await runtime.runTool("read", { path: "README.md" })

const event = createToolRunEvent(
  session.sessionId,
  "read",
  { path: "README.md" },
  result
)
await appendSessionEvent("/project", event)

// List sessions
const sessions = await listSessions("/project")
console.log(`${sessions.length} sessions`)
```

### Custom Tool

```typescript
import type { Tool, ToolResult, ToolExecutionContext, ToolInput } from "./core/contracts.js"

const MyTool: Tool = {
  name: "mytool",
  description: "Does something useful",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Input for mytool",
    required: ["value"],
    properties: {
      value: { type: "string", description: "Input value" },
    },
  },
  outputSchema: {
    type: "string",
    description: "Output value",
  },
  permissionSummary: "No special permissions required",
  exampleInput: { value: "hello" },
  
  checkPermission(input: ToolInput) {
    if (typeof input.value !== "string") {
      return { allowed: false, reason: "value must be a string" }
    }
    return { allowed: true, reason: "valid input" }
  },
  
  async run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    return { ok: true, data: `Processed: ${input.value}` }
  },
}
```
