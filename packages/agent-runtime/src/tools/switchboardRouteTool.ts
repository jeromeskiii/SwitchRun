import type { Tool, ToolInput, ToolPermissionDecision, ToolResult, ToolExecutionContext } from "../core/contracts.js"
import { validateForceAgent, runBridge } from "./bridgeHelper.js"

export const SwitchboardRouteTool: Tool = {
  name: "switchboard.route",
  description: "Route input to Python-based Switchboard system for LLM routing and agent orchestration",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Send input to Switchboard for classification, planning, and execution",
    required: ["input"],
    properties: {
      input: {
        type: "string",
        description: "The prompt/task to route through Switchboard",
      },
      forceAgent: {
        type: "string",
        description: "Optional: force specific agent (coding, data_analysis, creative_writing, etc.)",
      },
      verbose: {
        type: "boolean",
        description: "Optional: include routing metadata in output",
      },
      routeOnly: {
        type: "boolean",
        description: "Optional: return routing decision without execution",
      },
      json: {
        type: "boolean",
        description: "Optional: return JSON output",
      },
    },
  },
  outputSchema: {
    type: "object",
    description: "Switchboard routing result or execution output",
  },
  permissionSummary: "Validated against known agent IDs. Input length capped. Subprocess has a 60s timeout.",
  exampleInput: {
    input: "analyze this codebase and summarize findings",
    verbose: true,
  },
  checkPermission(input: ToolInput, _context: ToolExecutionContext): ToolPermissionDecision {
    const raw = input.input
    if (typeof raw !== "string" || raw.length === 0) {
      return { allowed: false, reason: "input must be a non-empty string" }
    }
    const MAX_INPUT_BYTES = 100_000
    if (raw.length > MAX_INPUT_BYTES) {
      return { allowed: false, reason: `input exceeds maximum length of ${MAX_INPUT_BYTES} characters` }
    }
    return validateForceAgent(input.forceAgent as string | undefined)
  },
  run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    const raw = input.input
    if (typeof raw !== "string" || raw.length === 0) {
      return Promise.resolve({ ok: false, error: "input.input must be a non-empty string" })
    }
    const inputText: string = raw

    const args: string[] = ["--input", inputText]

    if (typeof input.forceAgent === "string") {
      args.push("--force-agent", input.forceAgent)
    }
    if (input.verbose === true) {
      args.push("--verbose")
    }
    if (input.routeOnly === true) {
      args.push("--route-only")
    }
    if (input.json === true) {
      args.push("--json")
    }

    return runBridge(args, context)
  },
}
