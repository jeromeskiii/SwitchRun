import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { isAllowedBashPrefix } from "../permissions/engine.js"
import type {
  Tool,
  ToolExecutionContext,
  ToolInput,
  ToolPermissionDecision,
  ToolResult,
} from "../core/contracts.js"

const execFileAsync = promisify(execFile)

export const BashTool: Tool = {
  name: "bash",
  description: "Execute a constrained command using execFile",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Execute an allowlisted command with optional string args",
    required: ["cmd"],
    properties: {
      cmd: {
        type: "string",
        description: "Executable name",
      },
      args: {
        type: "array",
        description: "Optional string arguments",
        items: {
          type: "string",
          description: "Single command-line argument",
        },
      },
    },
  },
  outputSchema: {
    type: "object",
    description: "Captured command output",
    required: ["stdout", "stderr"],
    properties: {
      stdout: {
        type: "string",
        description: "Process standard output",
      },
      stderr: {
        type: "string",
        description: "Process standard error",
      },
    },
  },
  permissionSummary: "Denies command prefixes not listed in BASH_ALLOW_PREFIXES.",
  exampleInput: { cmd: "git", args: ["status"] },
  checkPermission(
    input: ToolInput,
    _context: ToolExecutionContext,
  ): ToolPermissionDecision {
    const cmd = input.cmd
    const args = input.args
    if (typeof cmd !== "string" || cmd.length === 0) {
      return { allowed: false, reason: "input.cmd must be a non-empty string" }
    }
    const safeArgs =
      Array.isArray(args) && args.every(a => typeof a === "string")
        ? (args as string[])
        : []
    if (!isAllowedBashPrefix(cmd, safeArgs)) {
      return { allowed: false, reason: "command prefix is not allowed" }
    }
    return { allowed: true, reason: "command allowed by prefix policy" }
  },
  async run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    const cmd = input.cmd
    if (typeof cmd !== "string") {
      return { ok: false, error: "input.cmd must be a string" }
    }
    const args =
      Array.isArray(input.args) && input.args.every(a => typeof a === "string")
        ? (input.args as string[])
        : []
    try {
      const { stdout, stderr } = await execFileAsync(cmd, args, {
        cwd: context.rootDir,
        maxBuffer: 2 * 1024 * 1024,
        timeout: context.timeoutMs,
      })
      return { ok: true, data: { stdout, stderr } }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return { ok: false, error: message }
    }
  },
}
