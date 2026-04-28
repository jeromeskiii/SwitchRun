import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { spawnSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

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

test("version and status report the package manifest version", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("../../package.json", import.meta.url), "utf8"),
  ) as { name?: string; version?: string }

  const versionResult = runCli(["version"])
  assert.equal(versionResult.status, 0, versionResult.stderr)
  const versionOutput = JSON.parse(versionResult.stdout) as { name?: string; version?: string }
  assert.equal(versionOutput.name, packageJson.name)
  assert.equal(versionOutput.version, packageJson.version)

  const statusResult = runCli(["status"])
  assert.equal(statusResult.status, 0, statusResult.stderr)
  const statusOutput = JSON.parse(statusResult.stdout) as {
    version?: string
    tools?: { names?: string[] }
  }
  assert.equal(statusOutput.version, packageJson.version)
  assert.ok(Array.isArray(statusOutput.tools?.names))
})
