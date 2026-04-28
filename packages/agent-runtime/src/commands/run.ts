import type { ToolInput } from "../core/contracts.js"
import type { AgentRuntime } from "../core/runtime.js"

export function parseJsonInput(rawInput: string): ToolInput | null {
  try {
    return JSON.parse(rawInput) as ToolInput
  } catch {
    return null
  }
}

export async function handleRunCommand(
  runtime: AgentRuntime,
  args: string[],
  printUsage: () => void,
): Promise<boolean> {
  const [toolName, rawInput] = args
  if (!toolName || !rawInput) {
    printUsage()
    process.exitCode = 1
    return true
  }
  const input = parseJsonInput(rawInput)
  if (!input) {
    console.error("invalid JSON input")
    process.exitCode = 1
    return true
  }
  const result = await runtime.runTool(toolName, input)
  console.log(JSON.stringify(result, null, 2))
  process.exitCode = result.ok ? 0 : 1
  return true
}

