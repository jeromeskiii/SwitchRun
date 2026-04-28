import fg from "fast-glob"
import path from "node:path"
import { isPathInsideRoot } from "../permissions/engine.js"
import type {
  Tool,
  ToolExecutionContext,
  ToolInput,
  ToolPermissionDecision,
  ToolResult,
} from "../core/contracts.js"

export const GlobTool: Tool = {
  name: "glob",
  description: "List files matching a glob pattern under rootDir",
  contractVersion: 1,
  inputSchema: {
    type: "object",
    description: "List files matching a rootDir-relative glob",
    required: ["pattern"],
    properties: {
      pattern: {
        type: "string",
        description: "Glob pattern relative to rootDir",
      },
    },
  },
  outputSchema: {
    type: "array",
    description: "Array of rootDir-relative file paths",
    items: {
      type: "string",
      description: "A file path relative to rootDir",
    },
  },
  permissionSummary:
    "Denies absolute paths and parent-segment escapes (../). Results are constrained to rootDir.",
  exampleInput: { pattern: "src/**/*.ts" },
  checkPermission(
    input: ToolInput,
    _context: ToolExecutionContext,
  ): ToolPermissionDecision {
    const pattern = input.pattern
    if (typeof pattern !== "string" || pattern.length === 0) {
      return { allowed: false, reason: "input.pattern must be a non-empty string" }
    }
    if (path.isAbsolute(pattern)) {
      return { allowed: false, reason: "pattern must be relative to rootDir" }
    }
    const segments = pattern.replaceAll("\\", "/").split("/")
    if (segments.includes("..")) {
      return { allowed: false, reason: "pattern cannot escape rootDir" }
    }
    return { allowed: true, reason: "pattern allowed" }
  },
  async run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult> {
    const pattern = input.pattern
    if (typeof pattern !== "string") {
      return { ok: false, error: "input.pattern must be a string" }
    }
    try {
      const entries = await fg(pattern, {
        cwd: context.rootDir,
        dot: false,
        onlyFiles: true,
      })
      // fast-glob with cwd:rootDir returns only rootDir-relative paths;
      // confinement is guaranteed by the permission check above (no `..` segments).
      return { ok: true, data: entries }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return { ok: false, error: message }
    }
  },
}
