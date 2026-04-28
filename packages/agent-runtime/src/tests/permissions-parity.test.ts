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

test("glob denies parent-escape patterns like read does", () => {
  const globResult = runCli(["run", "glob", '{"pattern":"../*"}'])
  assert.equal(globResult.status, 1, globResult.stderr)
  const globBody = JSON.parse(globResult.stdout) as { ok: boolean; error?: string }
  assert.equal(globBody.ok, false)
  assert.match(globBody.error ?? "", /permission denied/i)

  const readResult = runCli(["run", "read", '{"path":"../README.md"}'])
  assert.equal(readResult.status, 1, readResult.stderr)
  const readBody = JSON.parse(readResult.stdout) as { ok: boolean; error?: string }
  assert.equal(readBody.ok, false)
  assert.match(readBody.error ?? "", /permission denied/i)
})
