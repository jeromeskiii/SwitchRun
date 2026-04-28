import type { Tool, ToolInput, ToolPermissionDecision, ToolResult, ToolExecutionContext } from "../core/contracts.js"
import { runBridge } from "./bridgeHelper.js"

export const PantheonRouteTool: Tool = {
  name: "pantheon.route",
  description: "Route input to the Pantheon registry through Switchboard",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Send input to Switchboard and force Pantheon registry routing",
    required: ["input"],
    properties: {
      input: {
        type: "string",
        description: "The prompt/task to route through Pantheon",
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
    description: "Pantheon routing result returned by Switchboard",
  },
  permissionSummary: "Fixed agent (pantheon). Input length capped. Subprocess has a 60s timeout.",
  exampleInput: {
    input: "implement auth system",
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
    return { allowed: true, reason: "pantheon.route is fixed to pantheon agent" }
  },
  run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    const raw = input.input
    if (typeof raw !== "string" || raw.length === 0) {
      return Promise.resolve({ ok: false, error: "input.input must be a non-empty string" })
    }
    const inputText: string = raw

    const args: string[] = ["--input", inputText, "--force-agent", "pantheon"]

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
