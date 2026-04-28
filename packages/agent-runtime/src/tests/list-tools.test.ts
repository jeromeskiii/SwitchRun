import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import test from "node:test"
import path from "node:path"
import { fileURLToPath } from "node:url"

function projectRoot(): string {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")
}

function runCli(args: string[]): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync("node", ["dist/index.js", ...args], {
    cwd: projectRoot(),
    encoding: "utf8",
  })
  return {
    status: result.status,
    stdout: result.stdout,
    stderr: result.stderr,
  }
}

test("list-tools returns audited contract metadata for each tool", () => {
  const result = runCli(["list-tools"])
  assert.equal(result.status, 0, result.stderr)

  const parsed = JSON.parse(result.stdout) as Array<Record<string, unknown>>
  assert.ok(Array.isArray(parsed))

  const expectedTools = ["read", "glob", "bash", "switchboard.route", "mythos", "pantheon.route"]
  const returnedNames = parsed.map(tool => tool.name)
  for (const name of expectedTools) {
    assert.ok(returnedNames.includes(name), `expected tool "${name}" to be present`)
  }
  assert.equal(parsed.length, expectedTools.length, "unexpected extra tools in registry")

  for (const tool of parsed) {
    assert.equal(typeof tool.name, "string")
    assert.equal(typeof tool.description, "string")
    assert.equal(tool.contractVersion, 1)
    assert.equal(typeof tool.permissionSummary, "string")
    assert.equal(typeof tool.inputSchema, "object")
    assert.equal(typeof tool.outputSchema, "object")
    assert.equal(typeof tool.exampleInput, "object")
  }
})
