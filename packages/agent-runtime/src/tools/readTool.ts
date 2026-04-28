import { readFile } from "node:fs/promises"
import path from "node:path"
import { isPathInsideRoot } from "../permissions/engine.js"
import type {
  Tool,
  ToolExecutionContext,
  ToolInput,
  ToolPermissionDecision,
  ToolResult,
} from "../core/contracts.js"

export const ReadTool: Tool = {
  name: "read",
  description: "Read a UTF-8 file from disk",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "Read a UTF-8 file from rootDir-relative path",
    required: ["path"],
    properties: {
      path: {
        type: "string",
        description: "Path to file relative to rootDir",
      },
    },
  },
  outputSchema: {
    type: "string",
    description: "UTF-8 file content",
  },
  permissionSummary: "Denies absolute and parent-escape paths outside rootDir.",
  exampleInput: { path: "README.md" },
  checkPermission(
    input: ToolInput,
    context: ToolExecutionContext,
  ): ToolPermissionDecision {
    const rawPath = input.path
    if (typeof rawPath !== "string" || rawPath.length === 0) {
      return { allowed: false, reason: "input.path must be a non-empty string" }
    }
    if (!isPathInsideRoot(context.rootDir, rawPath)) {
      return { allowed: false, reason: "path is outside rootDir" }
    }
    return { allowed: true, reason: "path allowed" }
  },
  async run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    const rawPath = input.path
    if (typeof rawPath !== "string") {
      return { ok: false, error: "input.path must be a string" }
    }
    try {
      const target = path.resolve(context.rootDir, rawPath)
      const content = await readFile(target, "utf8")
      return { ok: true, data: content }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return { ok: false, error: message }
    }
  },
}
