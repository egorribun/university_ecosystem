// Rolldown allocates outside V8's heap. Report both at build boundaries so an
// RSS watchdog failure identifies the expensive phase. Stderr is intentional:
// Playwright captures it even when webServer stdout is hidden. No timers,
// retained bundles, environment values, paths, or error payloads are recorded.
export function buildMemoryTelemetry() {
  const report = (environment, phase) => {
    const label = environment?.config?.isWorker
      ? "worker"
      : environment?.config?.consumer === "client"
        ? "client"
        : environment?.config?.consumer === "server"
          ? "ssr"
          : "other"
    const memory = process.memoryUsage()
    const mib = (bytes) => (bytes / 1024 / 1024).toFixed(1)
    process.stderr.write(
      `[build-memory] environment=${label} phase=${phase}` +
        ` rss_mib=${mib(memory.rss)} heap_used_mib=${mib(memory.heapUsed)}` +
        ` heap_total_mib=${mib(memory.heapTotal)} external_mib=${mib(memory.external)}` +
        ` array_buffers_mib=${mib(memory.arrayBuffers)}\n`
    )
  }

  return {
    name: "build-memory-telemetry",
    apply: "build",
    enforce: "post",
    buildStart() {
      report(this.environment, "build-start")
    },
    buildEnd(error) {
      report(this.environment, error ? "transform-failed" : "transform-complete")
    },
    renderStart() {
      report(this.environment, "render-start")
    },
    generateBundle() {
      report(this.environment, "render-complete")
    },
    writeBundle() {
      report(this.environment, "write-complete")
    },
    closeBundle() {
      report(this.environment, "build-closed")
    },
  }
}
