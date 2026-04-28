import type { ToolResult } from "../core/contracts.js"

/**
 * Parse a string that may contain one or more concatenated JSON values
 * (objects or arrays) mixed with non-JSON text (e.g. progress lines).
 *
 * - Zero JSON values found → returns the raw trimmed text
 * - One JSON value found  → returns that value directly
 * - Multiple values found → returns them as an array
 */
export function parseJsonStream(stdout: string): ToolResult["data"] {
  const values: Exclude<ToolResult["data"], undefined>[] = []
  const text = stdout.trim()
  let start = -1
  let depth = 0
  let inString = false
  let escapeNext = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]

    if (start === -1) {
      if (char === "{" || char === "[") {
        start = index
        depth = 1
      }
      continue
    }

    if (inString) {
      if (escapeNext) {
        escapeNext = false
      } else if (char === "\\") {
        escapeNext = true
      } else if (char === '"') {
        inString = false
      }
      continue
    }

    if (char === '"') {
      inString = true
      continue
    }

    if (char === "{" || char === "[") {
      depth += 1
      continue
    }

    if (char === "}" || char === "]") {
      depth -= 1
      if (depth === 0 && start !== -1) {
        const parsed = JSON.parse(text.slice(start, index + 1)) as ToolResult["data"]
        if (parsed !== undefined) {
          values.push(parsed)
        }
        start = -1
      }
    }
  }

  if (values.length === 0) {
    return text
  }
  if (values.length === 1) {
    return values[0]
  }
  return values
}
