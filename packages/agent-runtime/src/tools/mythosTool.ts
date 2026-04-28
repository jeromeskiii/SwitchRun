import http from "node:http"
import type {
  Tool,
  ToolExecutionContext,
  ToolInput,
  ToolPermissionDecision,
  ToolResult,
} from "../core/contracts.js"
import { resolveEcosystemRoot } from "./ecosystemRoot.js"

const MYTHOS_PORT = Number(process.env.MYTHOS_API_PORT ?? process.env.MYTHOS_PORT ?? 3001)

/**
 * Resolve the Mythos service base URL. Port is overridable via MYTHOS_PORT.
 * The host is always localhost — Mythos is a local service.
 */
function mythosUrl(pathname: string): { hostname: string; port: number; path: string } {
  return { hostname: "localhost", port: MYTHOS_PORT, path: pathname }
}

function httpGet(opts: { hostname: string; port: number; path: string }, timeoutMs = 30_000): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = http.request({ ...opts, method: "GET" }, (res) => {
      let body = ""
      res.on("data", (chunk: Buffer) => { body += chunk.toString("utf8") })
      res.on("end", () => resolve(body))
    })
    req.on("error", reject)
    req.setTimeout(timeoutMs, () => {
      req.destroy()
      reject(new Error(`mythos GET timed out after ${timeoutMs}ms`))
    })
    req.end()
  })
}

function httpPost(
  opts: { hostname: string; port: number; path: string },
  payload: string,
  timeoutMs = 30_000,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        ...opts,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
      },
      (res) => {
        let body = ""
        res.on("data", (chunk: Buffer) => { body += chunk.toString("utf8") })
        res.on("end", () => resolve(body))
      },
    )
    req.on("error", reject)
    req.setTimeout(timeoutMs, () => {
      req.destroy()
      reject(new Error(`mythos POST timed out after ${timeoutMs}ms`))
    })
    req.write(payload)
    req.end()
  })
}

function parseResponse(raw: string): ToolResult["data"] {
  try {
    return JSON.parse(raw) as ToolResult["data"]
  } catch {
    return raw.trim()
  }
}

export const MythosTool: Tool = {
  name: "mythos",
  description: "Route tasks to Mythos Greek Pantheon AI system for skill-based execution",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Execute Mythos skills or get MCTS model selection",
    required: ["action"],
    properties: {
      action: {
        type: "string",
        description: "Action to perform: select (MCTS model), status, candidates",
      },
      taskType: {
        type: "string",
        description: "Task type for MCTS selection (general, coding, review, architect, etc.)",
      },
      framework: {
        type: "string",
        description: "Framework for MCTS (coder, planner, creative, etc.)",
      },
      language: {
        type: "string",
        description: "Programming language for context",
      },
      simulations: {
        type: "number",
        description: "Number of MCTS simulations (default: 60)",
      },
    },
  },
  outputSchema: {
    type: "object",
    description: "Mythos response",
  },
  permissionSummary:
    "Makes HTTP requests to localhost Mythos service (port overridable via MYTHOS_API_PORT, default 3001). No filesystem access.",
  exampleInput: {
    action: "select",
    taskType: "coding",
    framework: "coder",
    language: "typescript",
  },
  checkPermission(
    input: ToolInput,
    _context: ToolExecutionContext,
  ): ToolPermissionDecision {
    if (typeof input.action !== "string" || input.action.length === 0) {
      return { allowed: false, reason: "input.action must be a non-empty string" }
    }
    const allowed = ["select", "status", "candidates"]
    if (!allowed.includes(input.action as string)) {
      return {
        allowed: false,
        reason: `unknown action: ${input.action}. Allowed: ${allowed.join(", ")}`,
      }
    }
    return { allowed: true, reason: "mythos tool is permitted" }
  },
  async run(input: ToolInput, _context: ToolExecutionContext): Promise<ToolResult> {
    const action = input.action as string

    // resolveEcosystemRoot() validates ECOSYSTEM_ROOT is set; for mythos we only
    // need it to confirm the ecosystem is configured — actual calls go to HTTP.
    try {
      resolveEcosystemRoot()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      return { ok: false, error: message }
    }

    try {
      let raw: string

      if (action === "select") {
        const taskType = typeof input.taskType === "string" ? input.taskType : "general"
        const framework = typeof input.framework === "string" ? input.framework : "general"
        const language = typeof input.language === "string" ? input.language : "typescript"
        const simulations = typeof input.simulations === "number" ? input.simulations : 60

        const payload = JSON.stringify({ taskType, framework, language, simulations })
        raw = await httpPost(mythosUrl("/select"), payload)
      } else if (action === "status") {
        raw = await httpGet(mythosUrl("/status"))
      } else {
        // "candidates"
        raw = await httpGet(mythosUrl("/candidates"))
      }

      return { ok: true, data: parseResponse(raw) }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      return { ok: false, error: `mythos request failed: ${message}` }
    }
  },
}
