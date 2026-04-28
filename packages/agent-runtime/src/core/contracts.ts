export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [k: string]: JsonValue }

export type ToolInput = { [k: string]: JsonValue }

export type ToolExecutionContext = {
  rootDir: string
  /** Per-tool execution timeout in milliseconds. Enforced by tools that support it. */
  timeoutMs?: number
}

export type ToolResult = {
  ok: boolean
  data?: JsonValue
  error?: string
}

export type ToolPermissionDecision = {
  allowed: boolean
  reason: string
}

export type ToolJsonSchema = {
  type: "string" | "number" | "boolean" | "array" | "object"
  description: string
  required?: string[]
  items?: ToolJsonSchema
  properties?: Record<string, ToolJsonSchema>
}

export type ToolListEntry = {
  name: string
  description: string
  contractVersion: number
  inputSchema: ToolJsonSchema
  outputSchema: ToolJsonSchema
  permissionSummary: string
  exampleInput?: ToolInput
}

export interface Tool {
  readonly name: string
  readonly description: string
  readonly contractVersion: number
  readonly inputSchema: ToolJsonSchema
  readonly outputSchema: ToolJsonSchema
  readonly permissionSummary: string
  readonly exampleInput?: ToolInput
  checkPermission(
    input: ToolInput,
    context: ToolExecutionContext,
  ): ToolPermissionDecision
  run(input: ToolInput, context: ToolExecutionContext): Promise<ToolResult>
}
