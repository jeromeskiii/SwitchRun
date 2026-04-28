import { randomUUID } from "node:crypto"
import { appendFile, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises"
import path from "node:path"
import type { JsonValue, ToolInput, ToolResult } from "../core/contracts.js"

const MAX_STORED_RESULT_CHARS = 8_000

export type SessionEvent = {
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

export type SessionSnapshot = {
  sessionId: string
  createdAt: string
  updatedAt: string
  eventCount: number
  lastEventType: SessionEvent["type"] | null
}

export type SessionExportBundle = {
  version: 1
  exportedAt: string
  snapshot: SessionSnapshot
  events: SessionEvent[]
}

type SessionPaths = {
  sessionsDir: string
  snapshotsDir: string
}

function getSessionPaths(rootDir: string): SessionPaths {
  const baseDir = path.join(rootDir, ".agent-runtime")
  return {
    sessionsDir: path.join(baseDir, "sessions"),
    snapshotsDir: path.join(baseDir, "snapshots"),
  }
}

function sessionLogPath(paths: SessionPaths, sessionId: string): string {
  return path.join(paths.sessionsDir, `${sessionId}.jsonl`)
}

function snapshotPath(paths: SessionPaths, sessionId: string): string {
  return path.join(paths.snapshotsDir, `${sessionId}.json`)
}

async function ensureDirs(paths: SessionPaths): Promise<void> {
  await mkdir(paths.sessionsDir, { recursive: true })
  await mkdir(paths.snapshotsDir, { recursive: true })
}

async function readSnapshot(paths: SessionPaths, sessionId: string): Promise<SessionSnapshot | null> {
  try {
    const raw = await readFile(snapshotPath(paths, sessionId), "utf8")
    return JSON.parse(raw) as SessionSnapshot
  } catch {
    return null
  }
}

async function writeSnapshot(paths: SessionPaths, snapshot: SessionSnapshot): Promise<void> {
  await writeFile(
    snapshotPath(paths, snapshot.sessionId),
    JSON.stringify(snapshot, null, 2),
    "utf8",
  )
}

export function createToolRunEvent(
  sessionId: string,
  toolName: string,
  input: ToolInput,
  result: ToolResult,
): SessionEvent {
  const boundedResult = clampResultForStorage(result)
  return {
    id: randomUUID(),
    sessionId,
    timestamp: new Date().toISOString(),
    type: "tool_run",
    payload: {
      toolName,
      input,
      result: boundedResult.result,
      ...(boundedResult.meta ? { storageMeta: boundedResult.meta } : {}),
    },
  }
}

function clampResultForStorage(result: ToolResult): {
  result: ToolResult
  meta?: {
    resultTruncated: boolean
    originalChars: number
    storedChars: number
  }
} {
  const raw = JSON.stringify(result)
  if (raw.length <= MAX_STORED_RESULT_CHARS) {
    return { result }
  }

  const compactData = result.data === undefined
    ? undefined
    : typeof result.data === "string"
      ? result.data
      : JSON.stringify(result.data)

  const clipped = compactData && compactData.length > MAX_STORED_RESULT_CHARS
    ? `${compactData.slice(0, MAX_STORED_RESULT_CHARS)}\n...[truncated]`
    : compactData

  const reduced: ToolResult = {
    ok: result.ok,
    ...(result.error ? { error: result.error } : {}),
    ...(clipped ? { data: clipped } : {}),
  }

  return {
    result: reduced,
    meta: {
      resultTruncated: true,
      originalChars: raw.length,
      storedChars: JSON.stringify(reduced).length,
    },
  }
}

export async function createSession(rootDir: string, sessionId?: string): Promise<SessionSnapshot> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)

  const id = sessionId ?? randomUUID()
  const existing = await readSnapshot(paths, id)
  if (existing) {
    throw new Error(`session already exists: ${id}`)
  }

  const now = new Date().toISOString()
  const snapshot: SessionSnapshot = {
    sessionId: id,
    createdAt: now,
    updatedAt: now,
    eventCount: 0,
    lastEventType: null,
  }

  await writeFile(sessionLogPath(paths, id), "", "utf8")
  await writeSnapshot(paths, snapshot)
  return snapshot
}

export async function appendSessionEvent(rootDir: string, event: SessionEvent): Promise<SessionSnapshot> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)

  const current = await readSnapshot(paths, event.sessionId)
  if (!current) {
    throw new Error(`unknown session: ${event.sessionId}`)
  }

  await appendFile(sessionLogPath(paths, event.sessionId), `${JSON.stringify(event)}\n`, "utf8")

  const updated: SessionSnapshot = {
    ...current,
    updatedAt: event.timestamp,
    eventCount: current.eventCount + 1,
    lastEventType: event.type,
  }
  await writeSnapshot(paths, updated)
  return updated
}

export async function listSessions(rootDir: string): Promise<SessionSnapshot[]> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)

  const files = await readdir(paths.snapshotsDir)
  const snapshots: SessionSnapshot[] = []
  for (const file of files) {
    if (!file.endsWith(".json")) continue
    const sessionId = file.slice(0, -".json".length)
    const snapshot = await readSnapshot(paths, sessionId)
    if (snapshot) snapshots.push(snapshot)
  }
  snapshots.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  return snapshots
}

export async function deleteSession(rootDir: string, sessionId: string): Promise<boolean> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)
  const snapshot = await readSnapshot(paths, sessionId)
  if (!snapshot) return false

  await rm(sessionLogPath(paths, sessionId), { force: true })
  await rm(snapshotPath(paths, sessionId), { force: true })
  return true
}

export async function pruneSessions(rootDir: string, keep: number): Promise<{
  kept: number
  deleted: string[]
}> {
  const snapshots = await listSessions(rootDir)
  const safeKeep = Math.max(0, keep)
  const toDelete = snapshots.slice(safeKeep).map(s => s.sessionId)
  for (const id of toDelete) {
    await deleteSession(rootDir, id)
  }
  return {
    kept: Math.min(safeKeep, snapshots.length),
    deleted: toDelete,
  }
}

export async function getSessionSnapshot(rootDir: string, sessionId: string): Promise<SessionSnapshot | null> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)
  return readSnapshot(paths, sessionId)
}

export async function readSessionEvents(
  rootDir: string,
  sessionId: string,
  limit?: number,
): Promise<SessionEvent[]> {
  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)

  const raw = await readFile(sessionLogPath(paths, sessionId), "utf8")
  const events: SessionEvent[] = []
  for (const line of raw.split("\n")) {
    const trimmed = line.trim()
    if (trimmed.length === 0) continue
    try {
      events.push(JSON.parse(trimmed) as SessionEvent)
    } catch {
      // Skip corrupted lines rather than crashing the entire session read.
      // Corruption can occur from interrupted writes or disk errors.
    }
  }

  if (typeof limit === "number" && limit > 0) {
    return events.slice(-limit)
  }
  return events
}

export async function exportSessionBundle(
  rootDir: string,
  sessionId: string,
): Promise<SessionExportBundle> {
  const snapshot = await getSessionSnapshot(rootDir, sessionId)
  if (!snapshot) {
    throw new Error(`unknown session: ${sessionId}`)
  }
  const events = await readSessionEvents(rootDir, sessionId)
  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    snapshot,
    events,
  }
}

export async function importSessionBundle(
  rootDir: string,
  bundle: SessionExportBundle,
  sessionIdOverride?: string,
  options?: { force?: boolean },
): Promise<SessionSnapshot> {
  const targetSessionId = sessionIdOverride ?? bundle.snapshot.sessionId
  const existing = await getSessionSnapshot(rootDir, targetSessionId)
  if (existing && !options?.force) {
    throw new Error(`session already exists: ${targetSessionId}`)
  }
  if (existing && options?.force) {
    await deleteSession(rootDir, targetSessionId)
  }

  const now = new Date().toISOString()
  const mappedEvents = bundle.events.map(event => ({
    ...event,
    sessionId: targetSessionId,
  }))
  const lastTimestamp = mappedEvents.length > 0
    ? mappedEvents[mappedEvents.length - 1]!.timestamp
    : now

  const snapshot: SessionSnapshot = {
    sessionId: targetSessionId,
    createdAt: bundle.snapshot.createdAt ?? now,
    updatedAt: lastTimestamp,
    eventCount: mappedEvents.length,
    lastEventType: mappedEvents.length > 0
      ? mappedEvents[mappedEvents.length - 1]!.type
      : null,
  }

  const paths = getSessionPaths(rootDir)
  await ensureDirs(paths)
  const logBody =
    mappedEvents.map(event => JSON.stringify(event)).join("\n") +
    (mappedEvents.length > 0 ? "\n" : "")
  await writeFile(sessionLogPath(paths, targetSessionId), logBody, "utf8")
  await writeSnapshot(paths, snapshot)
  return snapshot
}

export function summarizeSession(snapshot: SessionSnapshot, events: SessionEvent[]): JsonValue {
  const lastEvent = events.length > 0 ? events[events.length - 1] : null
  return {
    sessionId: snapshot.sessionId,
    createdAt: snapshot.createdAt,
    updatedAt: snapshot.updatedAt,
    eventCount: snapshot.eventCount,
    lastEventType: snapshot.lastEventType,
    lastTool: lastEvent?.payload.toolName ?? null,
    lastResultOk: lastEvent?.payload.result.ok ?? null,
  }
}
