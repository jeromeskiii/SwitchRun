/**
 * Runtime telemetry for metrics collection.
 * 
 * Provides counters and histograms for:
 * - Tool executions (by name, status)
 * - Session operations (by type)
 * - Tool latency
 */

export type MetricLabels = Record<string, string>

export interface Counter {
  inc(labels?: MetricLabels): void
  get(labels?: MetricLabels): number
}

export interface Histogram {
  observe(value: number, labels?: MetricLabels): void
  getBuckets(labels?: MetricLabels): Map<number, number>
}

class CounterImpl implements Counter {
  private values = new Map<string, number>()

  inc(labels?: MetricLabels): void {
    const key = this.serializeLabels(labels ?? {})
    this.values.set(key, (this.values.get(key) ?? 0) + 1)
  }

  get(labels?: MetricLabels): number {
    const key = this.serializeLabels(labels ?? {})
    return this.values.get(key) ?? 0
  }

  private serializeLabels(labels: MetricLabels): string {
    return Object.entries(labels)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(",")
  }

  getAll(): Map<string, number> {
    return new Map(this.values)
  }
}

class HistogramImpl implements Histogram {
  private buckets: number[]
  private values = new Map<string, Map<number, number>>()

  constructor(buckets: number[] = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]) {
    this.buckets = [...buckets].sort((a, b) => a - b)
  }

  observe(value: number, labels?: MetricLabels): void {
    const key = this.serializeLabels(labels ?? {})
    let bucketMap = this.values.get(key)
    if (!bucketMap) {
      bucketMap = new Map<number, number>()
      this.values.set(key, bucketMap)
    }

    for (const bucket of this.buckets) {
      if (value <= bucket) {
        bucketMap.set(bucket, (bucketMap.get(bucket) ?? 0) + 1)
      }
    }
    // +Inf bucket always increments
    bucketMap.set(Infinity, (bucketMap.get(Infinity) ?? 0) + 1)
  }

  getBuckets(labels?: MetricLabels): Map<number, number> {
    const key = this.serializeLabels(labels ?? {})
    return new Map(this.values.get(key) ?? new Map())
  }

  private serializeLabels(labels: MetricLabels): string {
    return Object.entries(labels)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(",")
  }
}

export class RuntimeTelemetry {
  private toolExecutions = new CounterImpl()
  private sessionOperations = new CounterImpl()
  private toolLatency = new HistogramImpl([0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])

  recordToolExecution(toolName: string, latencyMs: number, success: boolean): void {
    this.toolExecutions.inc({ tool: toolName, status: success ? "success" : "failure" })
    this.toolLatency.observe(latencyMs / 1000)
  }

  recordSessionOperation(operation: string, latencyMs: number): void {
    this.sessionOperations.inc({ operation })
  }

  getMetrics(): {
    toolExecutions: Array<{ labels: MetricLabels; value: number }>
    sessionOperations: Array<{ labels: MetricLabels; value: number }>
  } {
    const toolExecutions: Array<{ labels: MetricLabels; value: number }> = []
    for (const [key, value] of this.toolExecutions.getAll()) {
      toolExecutions.push({ labels: this.parseLabels(key), value })
    }

    const sessionOperations: Array<{ labels: MetricLabels; value: number }> = []
    for (const [key, value] of this.sessionOperations.getAll()) {
      sessionOperations.push({ labels: this.parseLabels(key), value })
    }

    return { toolExecutions, sessionOperations }
  }

  private parseLabels(key: string): MetricLabels {
    if (key === "") return {}
    const labels: MetricLabels = {}
    for (const part of key.split(",")) {
      const [k, v] = part.split("=")
      if (k && v) labels[k] = v
    }
    return labels
  }

  formatPrometheus(): string {
    const lines: string[] = []
    
    lines.push("# HELP agent_runtime_tool_executions_total Total tool executions")
    lines.push("# TYPE agent_runtime_tool_executions_total counter")
    for (const [key, value] of this.toolExecutions.getAll()) {
      const labels = this.formatPrometheusLabels(this.parseLabels(key))
      lines.push(`agent_runtime_tool_executions_total${labels} ${value}`)
    }

    lines.push("")
    lines.push("# HELP agent_runtime_session_operations_total Total session operations")
    lines.push("# TYPE agent_runtime_session_operations_total counter")
    for (const [key, value] of this.sessionOperations.getAll()) {
      const labels = this.formatPrometheusLabels(this.parseLabels(key))
      lines.push(`agent_runtime_session_operations_total${labels} ${value}`)
    }

    return lines.join("\n")
  }

  private formatPrometheusLabels(labels: MetricLabels): string {
    const entries = Object.entries(labels)
    if (entries.length === 0) return ""
    const formatted = entries
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}="${v}"`)
      .join(",")
    return `{${formatted}}`
  }
}

// Global telemetry instance
let globalTelemetry: RuntimeTelemetry | null = null

export function getTelemetry(): RuntimeTelemetry {
  if (!globalTelemetry) {
    globalTelemetry = new RuntimeTelemetry()
  }
  return globalTelemetry
}

export function resetTelemetry(): void {
  globalTelemetry = null
}
