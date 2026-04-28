import assert from "node:assert/strict"
import test from "node:test"
import { RuntimeTelemetry, getTelemetry, resetTelemetry } from "../telemetry.js"

test("RuntimeTelemetry - records tool executions", () => {
  resetTelemetry()
  const telemetry = new RuntimeTelemetry()
  
  telemetry.recordToolExecution("read", 150, true)
  telemetry.recordToolExecution("read", 200, true)
  telemetry.recordToolExecution("glob", 100, false)
  
  const metrics = telemetry.getMetrics()
  
  const readSuccess = metrics.toolExecutions.find(
    m => m.labels.tool === "read" && m.labels.status === "success"
  )
  assert.equal(readSuccess?.value, 2)
  
  const globFailure = metrics.toolExecutions.find(
    m => m.labels.tool === "glob" && m.labels.status === "failure"
  )
  assert.equal(globFailure?.value, 1)
})

test("RuntimeTelemetry - records session operations", () => {
  resetTelemetry()
  const telemetry = new RuntimeTelemetry()
  
  telemetry.recordSessionOperation("create", 50)
  telemetry.recordSessionOperation("create", 60)
  telemetry.recordSessionOperation("delete", 30)
  
  const metrics = telemetry.getMetrics()
  
  const creates = metrics.sessionOperations.find(m => m.labels.operation === "create")
  assert.equal(creates?.value, 2)
  
  const deletes = metrics.sessionOperations.find(m => m.labels.operation === "delete")
  assert.equal(deletes?.value, 1)
})

test("RuntimeTelemetry - formats Prometheus metrics", () => {
  resetTelemetry()
  const telemetry = new RuntimeTelemetry()
  
  telemetry.recordToolExecution("read", 150, true)
  telemetry.recordSessionOperation("create", 50)
  
  const formatted = telemetry.formatPrometheus()
  
  assert.ok(formatted.includes("# HELP agent_runtime_tool_executions_total"))
  assert.ok(formatted.includes("# TYPE agent_runtime_tool_executions_total counter"))
  assert.ok(formatted.includes('tool="read"'))
  assert.ok(formatted.includes('status="success"'))
  assert.ok(formatted.includes("# HELP agent_runtime_session_operations_total"))
})

test("getTelemetry - returns singleton instance", () => {
  resetTelemetry()
  const t1 = getTelemetry()
  const t2 = getTelemetry()
  assert.strictEqual(t1, t2)
})
