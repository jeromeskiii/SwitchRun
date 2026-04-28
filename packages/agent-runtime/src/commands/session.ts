import { readFile, writeFile } from "node:fs/promises"
import type { AgentRuntime } from "../core/runtime.js"
import {
  appendSessionEvent,
  createSession,
  createToolRunEvent,
  deleteSession,
  exportSessionBundle,
  getSessionSnapshot,
  importSessionBundle,
  listSessions,
  pruneSessions,
  readSessionEvents,
  type SessionExportBundle,
  summarizeSession,
} from "../sessions/store.js"
import { isPathInsideRoot } from "../permissions/engine.js"
import { parseJsonInput } from "./run.js"

function confinedPath(rootDir: string, userPath: string): string | null {
  if (isPathInsideRoot(rootDir, userPath)) return userPath
  const safe = userPath.startsWith("/") ? userPath : `${rootDir}/${userPath}`
  if (isPathInsideRoot(rootDir, safe)) return safe
  return null
}

function parseLimit(raw: string | undefined): number | undefined {
  if (raw === undefined || raw === null) return undefined
  const parsed = Number.parseInt(raw, 10)
  if (!Number.isFinite(parsed) || parsed < 0) return undefined
  return parsed
}

function parseNonNegativeInt(raw: string | undefined): number | undefined {
  if (!raw) return undefined
  const parsed = Number.parseInt(raw, 10)
  if (!Number.isFinite(parsed) || parsed < 0) return undefined
  return parsed
}

function isSessionExportBundle(value: unknown): value is SessionExportBundle {
  if (!value || typeof value !== "object") return false
  const obj = value as Record<string, unknown>
  return (
    obj.version === 1 &&
    typeof obj.exportedAt === "string" &&
    typeof obj.snapshot === "object" &&
    Array.isArray(obj.events)
  )
}

export async function handleSessionCommand(
  runtime: AgentRuntime,
  rootDir: string,
  args: string[],
  printUsage: () => void,
): Promise<boolean> {
  const [action, ...sessionArgs] = args
  if (!action) {
    printUsage()
    process.exitCode = 1
    return true
  }

  if (action === "create") {
    const [sessionId] = sessionArgs
    const snapshot = await createSession(rootDir, sessionId)
    console.log(JSON.stringify(snapshot, null, 2))
    return true
  }

  if (action === "list") {
    const sessions = await listSessions(rootDir)
    console.log(JSON.stringify(sessions, null, 2))
    return true
  }

  if (action === "show") {
    const [sessionId, rawLimit] = sessionArgs
    if (!sessionId) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const snapshot = await getSessionSnapshot(rootDir, sessionId)
    if (!snapshot) {
      console.error(`unknown session: ${sessionId}`)
      process.exitCode = 1
      return true
    }
    const events = await readSessionEvents(rootDir, sessionId, parseLimit(rawLimit))
    console.log(
      JSON.stringify(
        {
          snapshot,
          events,
        },
        null,
        2,
      ),
    )
    return true
  }

  if (action === "resume") {
    const [sessionId] = sessionArgs
    if (!sessionId) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const snapshot = await getSessionSnapshot(rootDir, sessionId)
    if (!snapshot) {
      console.error(`unknown session: ${sessionId}`)
      process.exitCode = 1
      return true
    }
    const events = await readSessionEvents(rootDir, sessionId, 5)
    const summary = summarizeSession(snapshot, events)
    console.log(JSON.stringify({ summary, recentEvents: events }, null, 2))
    return true
  }

  if (action === "delete") {
    const [sessionId] = sessionArgs
    if (!sessionId) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const removed = await deleteSession(rootDir, sessionId)
    if (!removed) {
      console.error(`unknown session: ${sessionId}`)
      process.exitCode = 1
      return true
    }
    console.log(JSON.stringify({ deleted: sessionId }, null, 2))
    return true
  }

  if (action === "prune") {
    const [rawKeep] = sessionArgs
    const keep = parseNonNegativeInt(rawKeep)
    if (keep === undefined) {
      console.error("invalid keep-count, must be a non-negative integer")
      process.exitCode = 1
      return true
    }
    const result = await pruneSessions(rootDir, keep)
    console.log(JSON.stringify(result, null, 2))
    return true
  }

  if (action === "export") {
    const [sessionId, outputFile] = sessionArgs
    if (!sessionId) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const bundle = await exportSessionBundle(rootDir, sessionId)
    const payload = JSON.stringify(bundle, null, 2)
    if (outputFile) {
      const safePath = confinedPath(rootDir, outputFile)
      if (!safePath) {
        console.error(`output path '${outputFile}' is outside rootDir; refusing to write`)
        process.exitCode = 1
        return true
      }
      await writeFile(safePath, `${payload}\n`, "utf8")
      console.log(JSON.stringify({ sessionId, outputFile: safePath }, null, 2))
    } else {
      console.log(payload)
    }
    return true
  }

  if (action === "import") {
    const [inputFile, ...restArgs] = sessionArgs
    if (!inputFile) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const safePath = confinedPath(rootDir, inputFile)
    if (!safePath) {
      console.error(`input path '${inputFile}' is outside rootDir; refusing to read`)
      process.exitCode = 1
      return true
    }
    const force = restArgs.includes("--force")
    const positional = restArgs.filter(arg => arg !== "--force")
    const overrideSessionId = positional[0]
    const raw = await readFile(safePath, "utf8")
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      console.error("invalid JSON in import file")
      process.exitCode = 1
      return true
    }
    if (!isSessionExportBundle(parsed)) {
      console.error("invalid session export bundle format")
      process.exitCode = 1
      return true
    }
    const snapshot = await importSessionBundle(
      rootDir,
      parsed,
      overrideSessionId,
      { force },
    )
    console.log(JSON.stringify({ imported: snapshot, force }, null, 2))
    return true
  }

  if (action === "run") {
    const [sessionId, toolName, rawInput] = sessionArgs
    if (!sessionId || !toolName || !rawInput) {
      printUsage()
      process.exitCode = 1
      return true
    }
    const snapshot = await getSessionSnapshot(rootDir, sessionId)
    if (!snapshot) {
      console.error(`unknown session: ${sessionId}`)
      process.exitCode = 1
      return true
    }
    const input = parseJsonInput(rawInput)
    if (!input) {
      console.error("invalid JSON input")
      process.exitCode = 1
      return true
    }
    const result = await runtime.runTool(toolName, input)
    const event = createToolRunEvent(sessionId, toolName, input, result)
    const updatedSnapshot = await appendSessionEvent(rootDir, event)
    console.log(
      JSON.stringify(
        {
          result,
          snapshot: updatedSnapshot,
          event,
        },
        null,
        2,
      ),
    )
    process.exitCode = result.ok ? 0 : 1
    return true
  }

  printUsage()
  process.exitCode = 1
  return true
}

