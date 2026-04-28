import { spawn } from "node:child_process"
import path from "node:path"
import type { ToolExecutionContext, ToolPermissionDecision, ToolResult } from "../core/contracts.js"
import { parseJsonStream } from "./parseJsonStream.js"
import { resolveEcosystemRoot } from "./ecosystemRoot.js"

const KNOWN_AGENT_IDS = new Set([
  "reverse_engineering",
  "data_analysis",
  "coding",
  "documentation",
  "self_upgrade",
  "trading_analysis",
  "creative_writing",
  "master_alpha",
  "nexus",
  "agent_runtime",
  "mythos",
  "pantheon",
  "general",
])

const DEFAULT_TIMEOUT_MS = 60_000

export function validateForceAgent(agent: string | undefined): ToolPermissionDecision {
  if (agent === undefined || agent === "") {
    return { allowed: true, reason: "No agent forced; routing is free" }
  }
  if (KNOWN_AGENT_IDS.has(agent)) {
    return { allowed: true, reason: `forceAgent '${agent}' is a known agent ID` }
  }
  return {
    allowed: false,
    reason: `forceAgent '${agent}' is not a known agent ID. Valid IDs: ${[...KNOWN_AGENT_IDS].join(", ")}`,
  }
}

export function resolveTimeout(context: ToolExecutionContext): number {
  if (context.timeoutMs !== undefined && context.timeoutMs > 0) {
    return context.timeoutMs
  }
  return DEFAULT_TIMEOUT_MS
}

export function runBridge(args: string[], context: ToolExecutionContext): Promise<ToolResult> {
  return new Promise((resolve) => {
    const switchboardPath = path.join(resolveEcosystemRoot(), "packages", "switchboard")
    const venvPython = path.join(switchboardPath, ".venv", "bin", "python3")
    const timeoutMs = resolveTimeout(context)

    let timer: NodeJS.Timeout | undefined

    const proc = spawn(venvPython, ["-m", "switchboard", ...args], {
      cwd: switchboardPath,
      stdio: ["ignore", "pipe", "pipe"],
    })

    let stdout = ""
    let stderr = ""

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString("utf8")
    })

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString("utf8")
    })

    const cleanup = () => {
      if (timer !== undefined) {
        clearTimeout(timer)
        timer = undefined
      }
    }

    const handleClose = (code: number | null) => {
      cleanup()
      if (code !== 0) {
        resolve({ ok: false, error: `Switchboard exited with code ${code}. stderr: ${stderr}` })
        return
      }
      let data: ToolResult["data"]
      try {
        data = parseJsonStream(stdout)
      } catch {
        data = stdout.trim()
      }
      resolve({ ok: true, data, ...(stderr && { error: stderr.trim() }) })
    }

    timer = setTimeout(() => {
      proc.kill("SIGTERM")
      setTimeout(() => {
        if (!proc.killed) {
          proc.kill("SIGKILL")
        }
        resolve({ ok: false, error: `Switchboard timed out after ${timeoutMs}ms` })
      }, 5_000)
    }, timeoutMs)

    proc.on("close", handleClose)
    proc.on("error", (err) => {
      cleanup()
      resolve({ ok: false, error: `Failed to spawn switchboard: ${err.message}` })
    })
  })
}
