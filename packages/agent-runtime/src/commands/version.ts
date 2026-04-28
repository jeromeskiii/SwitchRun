import { readPackageMetadata } from "../lib/packageMetadata.js"
import type { AgentRuntime } from "../core/runtime.js"
import { listSessions } from "../sessions/store.js"

export async function handleVersionCommand(): Promise<boolean> {
  const pkg = await readPackageMetadata()
  console.log(JSON.stringify({
    name: pkg.name,
    version: pkg.version,
    nodeVersion: process.version,
    platform: process.platform,
  }, null, 2))
  return true
}

export async function handleStatusCommand(
  runtime: AgentRuntime,
  rootDir: string,
): Promise<boolean> {
  const sessions = await listSessions(rootDir)
  const toolNames = runtime.listTools().map(tool => tool.name)
  const pkg = await readPackageMetadata()
  
  console.log(JSON.stringify({
    status: "healthy",
    version: pkg.version,
    timestamp: new Date().toISOString(),
    tools: {
      registered: toolNames.length,
      names: toolNames,
    },
    sessions: {
      count: sessions.length,
      mostRecent: sessions.length > 0 ? sessions[0]!.sessionId : null,
    },
    environment: {
      adaEngineDir: process.env.ADA_ENGINE_DIR ?? null,
      alphamuPath: process.env.ALPHAMU_PATH ?? null,
      ecosystemRoot: process.env.ECOSYSTEM_ROOT ?? null,
      mythosPort: process.env.MYTHOS_PORT ?? null,
    },
  }, null, 2))
  return true
}
