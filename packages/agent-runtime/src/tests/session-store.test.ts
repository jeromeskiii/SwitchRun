import assert from "node:assert/strict"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
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
} from "../sessions/store.js"
import { writeFile, mkdir } from "node:fs/promises"

async function withTempDir(fn: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(path.join(tmpdir(), "agent-runtime-test-"))
  try {
    await fn(dir)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

test("createSession — creates snapshot with zero events", async () => {
  await withTempDir(async dir => {
    const snapshot = await createSession(dir, "test-session")
    assert.equal(snapshot.sessionId, "test-session")
    assert.equal(snapshot.eventCount, 0)
    assert.equal(snapshot.lastEventType, null)
  })
})

test("createSession — auto-generates id when omitted", async () => {
  await withTempDir(async dir => {
    const snapshot = await createSession(dir)
    assert.ok(typeof snapshot.sessionId === "string")
    assert.ok(snapshot.sessionId.length > 0)
  })
})

test("createSession — throws if session already exists", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "dupe")
    await assert.rejects(() => createSession(dir, "dupe"), /already exists/)
  })
})

test("appendSessionEvent — increments eventCount and updates snapshot", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "s1")
    const event = createToolRunEvent("s1", "read", { path: "README.md" }, { ok: true, data: "hello" })
    const updated = await appendSessionEvent(dir, event)
    assert.equal(updated.eventCount, 1)
    assert.equal(updated.lastEventType, "tool_run")
  })
})

test("readSessionEvents — returns all events in order", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "s2")
    for (let i = 0; i < 3; i++) {
      const event = createToolRunEvent("s2", "read", { path: `file${i}.ts` }, { ok: true, data: `content${i}` })
      await appendSessionEvent(dir, event)
    }
    const events = await readSessionEvents(dir, "s2")
    assert.equal(events.length, 3)
    assert.equal(events[0]!.payload.input.path, "file0.ts")
    assert.equal(events[2]!.payload.input.path, "file2.ts")
  })
})

test("readSessionEvents — limit caps from the tail", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "s3")
    for (let i = 0; i < 5; i++) {
      const event = createToolRunEvent("s3", "read", { path: `f${i}.ts` }, { ok: true })
      await appendSessionEvent(dir, event)
    }
    const events = await readSessionEvents(dir, "s3", 2)
    assert.equal(events.length, 2)
    assert.equal(events[0]!.payload.input.path, "f3.ts")
    assert.equal(events[1]!.payload.input.path, "f4.ts")
  })
})

test("readSessionEvents — skips corrupted JSONL lines instead of throwing", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "corrupt")
    // Manually write a valid event, a corrupted line, then another valid event
    const e1 = createToolRunEvent("corrupt", "read", { path: "a.ts" }, { ok: true })
    const e2 = createToolRunEvent("corrupt", "glob", { pattern: "**/*.ts" }, { ok: true })
    const sessionLog = path.join(dir, ".agent-runtime", "sessions", "corrupt.jsonl")
    await mkdir(path.dirname(sessionLog), { recursive: true })
    await writeFile(
      sessionLog,
      `${JSON.stringify(e1)}\n{CORRUPTED LINE\n${JSON.stringify(e2)}\n`,
      "utf8",
    )
    // Also write a snapshot so readSnapshot succeeds
    const snapshotDir = path.join(dir, ".agent-runtime", "snapshots")
    await mkdir(snapshotDir, { recursive: true })
    await writeFile(
      path.join(snapshotDir, "corrupt.json"),
      JSON.stringify({
        sessionId: "corrupt",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        eventCount: 3,
        lastEventType: "tool_run",
      }),
      "utf8",
    )

    // Should not throw; corrupted line is silently skipped
    const events = await readSessionEvents(dir, "corrupt")
    assert.equal(events.length, 2)
    assert.equal(events[0]!.payload.toolName, "read")
    assert.equal(events[1]!.payload.toolName, "glob")
  })
})

test("deleteSession — removes session and returns true", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "to-delete")
    const removed = await deleteSession(dir, "to-delete")
    assert.equal(removed, true)
    const snapshot = await getSessionSnapshot(dir, "to-delete")
    assert.equal(snapshot, null)
  })
})

test("deleteSession — returns false for unknown session", async () => {
  await withTempDir(async dir => {
    const removed = await deleteSession(dir, "nonexistent")
    assert.equal(removed, false)
  })
})

test("listSessions — returns sessions sorted by updatedAt descending", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "alpha")
    await new Promise(r => setTimeout(r, 10))
    await createSession(dir, "beta")
    const sessions = await listSessions(dir)
    assert.equal(sessions[0]!.sessionId, "beta")
    assert.equal(sessions[1]!.sessionId, "alpha")
  })
})

test("pruneSessions — keeps the most recent N and deletes the rest", async () => {
  await withTempDir(async dir => {
    for (const id of ["a", "b", "c", "d"]) {
      await createSession(dir, id)
      await new Promise(r => setTimeout(r, 10))
    }
    const result = await pruneSessions(dir, 2)
    assert.equal(result.kept, 2)
    assert.equal(result.deleted.length, 2)
    const remaining = await listSessions(dir)
    assert.equal(remaining.length, 2)
    assert.deepEqual(
      remaining.map((s: { sessionId: string }) => s.sessionId),
      ["d", "c"],
    )
  })
})

test("pruneSessions — keep 0 deletes all", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "x")
    await createSession(dir, "y")
    const result = await pruneSessions(dir, 0)
    assert.equal(result.kept, 0)
    assert.equal(result.deleted.length, 2)
    const remaining = await listSessions(dir)
    assert.equal(remaining.length, 0)
  })
})

test("exportSessionBundle — round-trips events and snapshot", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "export-me")
    const event = createToolRunEvent("export-me", "read", { path: "README.md" }, { ok: true, data: "hi" })
    await appendSessionEvent(dir, event)

    const bundle = await exportSessionBundle(dir, "export-me")
    assert.equal(bundle.version, 1)
    assert.equal(bundle.snapshot.sessionId, "export-me")
    assert.equal(bundle.events.length, 1)
    assert.equal(bundle.events[0]!.payload.toolName, "read")
  })
})

test("importSessionBundle — imports into new session id", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "src-session")
    const event = createToolRunEvent("src-session", "glob", { pattern: "**/*.ts" }, { ok: true, data: [] })
    await appendSessionEvent(dir, event)
    const bundle = await exportSessionBundle(dir, "src-session")

    await withTempDir(async dir2 => {
      const snapshot = await importSessionBundle(dir2, bundle, "imported-session")
      assert.equal(snapshot.sessionId, "imported-session")
      assert.equal(snapshot.eventCount, 1)
      const events = await readSessionEvents(dir2, "imported-session")
      assert.equal(events.length, 1)
      assert.equal(events[0]!.sessionId, "imported-session")
    })
  })
})

test("importSessionBundle — --force overwrites existing session", async () => {
  await withTempDir(async dir => {
    await createSession(dir, "existing")
    const bundle: SessionExportBundle = {
      version: 1,
      exportedAt: new Date().toISOString(),
      snapshot: {
        sessionId: "existing",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        eventCount: 0,
        lastEventType: null,
      },
      events: [],
    }
    // Without force — should throw
    await assert.rejects(() => importSessionBundle(dir, bundle), /already exists/)
    // With force — should succeed
    const snapshot = await importSessionBundle(dir, bundle, undefined, { force: true })
    assert.equal(snapshot.sessionId, "existing")
  })
})
