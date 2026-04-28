export function initializeEntrypoint(isNonInteractive: boolean): void {
  if (process.env.AGENT_RUNTIME_ENTRYPOINT) {
    return
  }
  process.env.AGENT_RUNTIME_ENTRYPOINT = isNonInteractive ? "script" : "cli"
}

