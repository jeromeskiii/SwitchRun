import process from "node:process"
import { AgentRuntime } from "./core/runtime.js"
import { handleAlphamuCommand } from "./commands/alphamu.js"
import { handleMctsCommand } from "./commands/mcts.js"
import { handleMetaCommand } from "./commands/meta.js"
import { handleRunCommand } from "./commands/run.js"
import { handleSessionCommand } from "./commands/session.js"
import { handleStatusCommand, handleVersionCommand } from "./commands/version.js"
import { printUsage } from "./commands/usage.js"
import { initializeEntrypoint } from "./entrypoints/startup/entrypoint.js"
import { detectPendingSessionTransfer } from "./entrypoints/startup/pending-connections.js"
import { startDeferredPrefetches } from "./entrypoints/startup/prefetch.js"
import { eagerLoadStartupSettings } from "./entrypoints/startup/settings-loader.js"

async function main(): Promise<void> {
  const rawArgs = process.argv.slice(2)
  const { settings, cliArgs } = eagerLoadStartupSettings(rawArgs)
  const isNonInteractive = !process.stdout.isTTY
  initializeEntrypoint(isNonInteractive)
  startDeferredPrefetches(settings.rootDir)
  const pendingTransfer = detectPendingSessionTransfer(cliArgs)
  if (pendingTransfer) {
    process.env.AGENT_RUNTIME_PENDING_TRANSFER = pendingTransfer.action
  }

  const runtime = new AgentRuntime({ rootDir: settings.rootDir })
  const [command, ...rest] = cliArgs

  if (!command) {
    printUsage()
    process.exitCode = 1
    return
  }

  if (command === "list-tools") {
    console.log(JSON.stringify(runtime.listTools(), null, 2))
    return
  }

  if (command === "run") {
    await handleRunCommand(runtime, rest, printUsage)
    return
  }

  if (command === "meta") {
    await handleMetaCommand(runtime, settings.rootDir, rest, printUsage)
    return
  }

  if (command === "session") {
    await handleSessionCommand(runtime, settings.rootDir, rest, printUsage)
    return
  }

  if (command === "mcts") {
    await handleMctsCommand(rest, printUsage)
    return
  }

  if (command === "alphamu") {
    await handleAlphamuCommand(rest, printUsage)
    return
  }

  if (command === "version") {
    await handleVersionCommand()
    return
  }

  if (command === "status") {
    await handleStatusCommand(runtime, settings.rootDir)
    return
  }

  printUsage()
  process.exitCode = 1
}

void main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error)
  console.error(message)
  process.exitCode = 1
})
