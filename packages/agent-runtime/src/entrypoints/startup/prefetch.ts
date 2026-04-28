import { listSessions } from "../../sessions/store.js"

export type StartupPrefetchSnapshot = {
  loadedAt: string
  sessionCount: number
  latestSessionId: string | null
}

let prefetched: Promise<StartupPrefetchSnapshot> | null = null
let prefetchedRootDir: string | null = null

async function prefetchStartupSnapshot(rootDir: string): Promise<StartupPrefetchSnapshot> {
  const sessions = await listSessions(rootDir)
  return {
    loadedAt: new Date().toISOString(),
    sessionCount: sessions.length,
    latestSessionId: sessions[0]?.sessionId ?? null,
  }
}

export function startDeferredPrefetches(rootDir: string): void {
  if (prefetched && prefetchedRootDir === rootDir) {
    return
  }
  prefetchedRootDir = rootDir
  prefetched = prefetchStartupSnapshot(rootDir).catch(() => ({
    loadedAt: new Date().toISOString(),
    sessionCount: 0,
    latestSessionId: null,
  }))
}

export async function getStartupPrefetchSnapshot(
  rootDir: string,
): Promise<StartupPrefetchSnapshot> {
  startDeferredPrefetches(rootDir)
  return prefetched as Promise<StartupPrefetchSnapshot>
}

