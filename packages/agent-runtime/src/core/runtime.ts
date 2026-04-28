import type { ToolInput, ToolListEntry, ToolResult } from "./contracts.js"
import { TOOLS } from "../tools/index.js"

export type RuntimeOptions = {
  rootDir: string
  /** Default per-tool execution timeout in milliseconds. Passed to every tool context. */
  defaultTimeoutMs?: number
}

export type RunToolOptions = {
  /** Per-call timeout override in milliseconds. Supersedes defaultTimeoutMs when set. */
  timeoutMs?: number
}

export class AgentRuntime {
  private readonly rootDir: string
  private readonly defaultTimeoutMs: number | undefined

  constructor(options: RuntimeOptions) {
    this.rootDir = options.rootDir
    this.defaultTimeoutMs = options.defaultTimeoutMs
  }

  listTools(): ToolListEntry[] {
    return Object.values(TOOLS).map(tool => ({
      name: tool.name,
      description: tool.description,
      contractVersion: tool.contractVersion,
      inputSchema: tool.inputSchema,
      outputSchema: tool.outputSchema,
      permissionSummary: tool.permissionSummary,
      exampleInput: tool.exampleInput,
    }))
  }

  async runTool(
    toolName: string,
    input: ToolInput,
    options?: RunToolOptions,
  ): Promise<ToolResult> {
    const tool = TOOLS[toolName]
    if (!tool) {
      return { ok: false, error: `unknown tool: ${toolName}` }
    }
    const timeoutMs = options?.timeoutMs ?? this.defaultTimeoutMs
    const context = { rootDir: this.rootDir, ...(timeoutMs !== undefined ? { timeoutMs } : {}) }
    const decision = tool.checkPermission(input, context)
    if (!decision.allowed) {
      return { ok: false, error: `permission denied: ${decision.reason}` }
    }
    return tool.run(input, context)
  }
}
