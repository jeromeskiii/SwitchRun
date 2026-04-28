export type PendingSessionTransfer = {
  action: "import" | "export"
  file: string
}

export function detectPendingSessionTransfer(
  cliArgs: string[],
): PendingSessionTransfer | null {
  if (cliArgs[0] !== "session") return null
  const action = cliArgs[1]
  const file = cliArgs[2]
  if ((action === "import" || action === "export") && typeof file === "string") {
    return { action, file }
  }
  return null
}

// TODO: AGENT_RUNTIME_PENDING_TRANSFER is set in index.ts but not yet consumed by any
// downstream handler. This is scaffolding for a future inter-process handoff protocol
// where a parent process signals an in-flight session transfer to a child agent instance.
// When that feature is built, read this env var in the child's startup path and
// auto-resume the import/export instead of requiring the user to re-issue the command.

