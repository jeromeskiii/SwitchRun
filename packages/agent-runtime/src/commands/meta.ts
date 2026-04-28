import type { AgentRuntime } from "../core/runtime.js"
import { readPackageMetadata } from "../lib/packageMetadata.js"
import { getStartupPrefetchSnapshot } from "../entrypoints/startup/prefetch.js"
import { listSessions } from "../sessions/store.js"

export async function handleMetaCommand(
  runtime: AgentRuntime,
  rootDir: string,
  args: string[],
  printUsage: () => void,
): Promise<boolean> {
  const [action, targetArg] = args
  if (action !== "report") {
    printUsage()
    process.exitCode = 1
    return true
  }
  const target = targetArg ?? "agent-runtime"
  const pkg = await readPackageMetadata()
  const tools = runtime.listTools()
  const sessions = await listSessions(rootDir)
  const startupPrefetch = await getStartupPrefetchSnapshot(rootDir)
  const latestSession = sessions[0] ?? null

  console.log(
    JSON.stringify(
      {
        meta: {
          target,
          generatedAt: new Date().toISOString(),
        },
        runtime: {
          name: pkg.name,
          version: pkg.version,
          rootDir,
          entrypoint: process.env.AGENT_RUNTIME_ENTRYPOINT ?? null,
          pendingTransfer: process.env.AGENT_RUNTIME_PENDING_TRANSFER ?? null,
          toolCount: tools.length,
          tools: tools.map(tool => tool.name),
        },
        sessions: {
          count: sessions.length,
          totalEvents: sessions.reduce((sum, session) => sum + session.eventCount, 0),
          latestSessionId: latestSession?.sessionId ?? null,
          latestUpdatedAt: latestSession?.updatedAt ?? null,
        },
        startupPrefetch: {
          loadedAt: startupPrefetch.loadedAt,
          sessionCount: startupPrefetch.sessionCount,
          latestSessionId: startupPrefetch.latestSessionId,
        },
      },
      null,
      2,
    ),
  )
  return true
}
