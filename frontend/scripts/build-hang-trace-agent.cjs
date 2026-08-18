/**
 * build-hang-trace-agent.cjs — diagnostic agent for build-orchestrated.mjs
 *
 * Injected into the vite subprocess via NODE_OPTIONS=--require so it runs
 * INSIDE the vite child process, not in the orchestrator parent. Captures
 * the handle list that's keeping the event loop alive after vite finishes
 * its prerender + asset emission but before the process exits naturally.
 *
 * The orchestrator may reach a stable-artifact point while a Vite plugin still
 * owns event-loop resources. This agent records active handles and requests
 * before the orchestrator ends that child process.
 *
 * ## How it works
 *
 * 1. On require, the agent registers SIGUSR2 handler (Unix) AND a `message`
 *    listener for IPC. Either signal triggers a handle dump.
 * 2. The orchestrator (parent) sends `{ type: "build-hang-trace-dump" }` via
 *    IPC after artifact-stable detection.
 * 3. The agent dumps handles to stderr (visible via stdio inherit) AND via
 *    IPC reply, then exits the process gracefully.
 *
 * ## Output format
 *
 * stderr lines prefixed with `[build-hang-trace]`:
 *   [build-hang-trace] dump triggered after Xms
 *   [build-hang-trace] active handles: N
 *     - HandleConstructorName (count if multiple)
 *   [build-hang-trace] active requests: M
 *     - RequestConstructorName
 *
 * IPC reply payload: `{ type, elapsedMs, handles: string[], requests: string[] }`
 *
 * ## Limitations
 *
 * - Constructor names identify handle types, not the plugin that created
 *   them. Plugin attribution would require constructor instrumentation and
 *   creation-stack capture.
 * - On Windows, SIGUSR2 doesn't exist; we only use IPC. Linux/macOS support
 *   both signals + IPC for parity with future cross-platform investigations.
 *
 * If handle types alone do not pinpoint the culprit, use:
 * - Monkey-patch with stack capture (heavy)
 * - Node Inspector Protocol via --inspect-port (chrome://inspect)
 * - File upstream issue at vitejs/vite or tanstackStart with full repro
 */

const fs = require("node:fs")
const path = require("node:path")

const startTime = Date.now()

function dumpHandles(reason) {
  const elapsed = Date.now() - startTime
  const handles = process._getActiveHandles()
  const requests = process._getActiveRequests()

  // Aggregate by constructor name
  const handleCounts = new Map()
  for (const h of handles) {
    const name = h.constructor?.name ?? typeof h
    handleCounts.set(name, (handleCounts.get(name) ?? 0) + 1)
  }
  const requestCounts = new Map()
  for (const r of requests) {
    const name = r.constructor?.name ?? typeof r
    requestCounts.set(name, (requestCounts.get(name) ?? 0) + 1)
  }

  process.stderr.write(`\n[build-hang-trace] === handle dump (${reason}) ===\n`)
  process.stderr.write(`[build-hang-trace] elapsed: ${elapsed}ms\n`)
  process.stderr.write(`[build-hang-trace] active handles: ${handles.length}\n`)
  for (const [name, count] of [...handleCounts.entries()].sort()) {
    process.stderr.write(`[build-hang-trace]   - ${name}${count > 1 ? ` × ${count}` : ""}\n`)
  }
  process.stderr.write(`[build-hang-trace] active requests: ${requests.length}\n`)
  for (const [name, count] of [...requestCounts.entries()].sort()) {
    process.stderr.write(`[build-hang-trace]   - ${name}${count > 1 ? ` × ${count}` : ""}\n`)
  }
  process.stderr.write(`[build-hang-trace] === end dump ===\n\n`)

  // Also write to file so orchestrator can capture even if stderr is buffered
  const traceDir = path.join(process.cwd(), ".build-hang-trace")
  try {
    if (!fs.existsSync(traceDir)) fs.mkdirSync(traceDir, { recursive: true })
    const traceFile = path.join(traceDir, `dump-${Date.now()}.json`)
    fs.writeFileSync(
      traceFile,
      JSON.stringify(
        {
          reason,
          elapsedMs: elapsed,
          handles: [...handleCounts.entries()].map(([name, count]) => ({ name, count })),
          requests: [...requestCounts.entries()].map(([name, count]) => ({ name, count })),
          timestamp: new Date().toISOString(),
        },
        null,
        2
      )
    )
  } catch {
    // best-effort
  }

  if (typeof process.send === "function") {
    try {
      process.send({
        type: "build-hang-trace-dump-reply",
        elapsedMs: elapsed,
        handles: [...handleCounts.entries()].map(([name, count]) => ({ name, count })),
        requests: [...requestCounts.entries()].map(([name, count]) => ({ name, count })),
      })
    } catch {
      // IPC may be closed; we already wrote stderr + file
    }
  }
}

// Listen for IPC trigger from orchestrator
process.on("message", (msg) => {
  if (msg && typeof msg === "object" && msg.type === "build-hang-trace-dump") {
    dumpHandles(msg.reason ?? "ipc-request")
    if (msg.thenExit) {
      // Schedule exit after stderr flush
      setImmediate(() => process.exit(0))
    }
  }
})

// Linux/macOS only — Windows doesn't support SIGUSR2
if (process.platform !== "win32") {
  process.on("SIGUSR2", () => dumpHandles("sigusr2"))
}

// Self-trigger: if no IPC dump request after MAX_WAIT_MS, dump anyway
// This catches the scenario where the orchestrator can't send IPC (no IPC
// channel set up) — gives diagnostic value via stderr + file.
const MAX_WAIT_MS = parseInt(process.env.BUILD_HANG_TRACE_MAX_WAIT_MS ?? "300000", 10)
const watchdog = setTimeout(() => {
  dumpHandles("watchdog-timeout")
  process.exit(2)
}, MAX_WAIT_MS)
watchdog.unref()
