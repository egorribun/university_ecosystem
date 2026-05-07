/**
 * wave136-hang-trace-agent.cjs — diagnostic agent for build-orchestrated.mjs
 *
 * Injected into the vite subprocess via NODE_OPTIONS=--require so it runs
 * INSIDE the vite child process, not in the orchestrator parent. Captures
 * the handle list that's keeping the event loop alive after vite finishes
 * its prerender + asset emission but before the process exits naturally.
 *
 * ## Why this exists
 *
 * Wave 135 SW3 retired wave127-build-x3.sh via build-orchestrated.mjs but
 * left the underlying hang structurally unfixed (kill-after-artifacts is a
 * workaround). Two suspected hang points:
 * 1. vite-plugin-pwa Windows post-build hook (KNOWN per W126 polish #3)
 * 2. A second hang point in tanstackStart's plugin chain (W135 SW3 surfaced;
 *    even with VitePWA({disable: true}) the subprocess still hung)
 *
 * Wave 136 SW5 (Q3a Medium): instrument the vite subprocess with
 * `process._getActiveHandles()` + `process._getActiveRequests()` AFTER the
 * artifact-stable point but BEFORE force-exit. This identifies which handle
 * types (FSWatcher / Timer / TLSWRAP / ChildProcess) are holding the loop.
 *
 * ## How it works
 *
 * 1. On require, the agent registers SIGUSR2 handler (Unix) AND a `message`
 *    listener for IPC. Either signal triggers a handle dump.
 * 2. The orchestrator (parent) sends `{ type: "wave136-trace-dump" }` via
 *    IPC after artifact-stable detection.
 * 3. The agent dumps handles to stderr (visible via stdio inherit) AND via
 *    IPC reply, then exits the process gracefully.
 *
 * ## Output format
 *
 * stderr lines prefixed with `[wave136-trace]`:
 *   [wave136-trace] dump triggered after Xms
 *   [wave136-trace] active handles: N
 *     - HandleConstructorName (count if multiple)
 *   [wave136-trace] active requests: M
 *     - RequestConstructorName
 *
 * IPC reply payload: `{ type, elapsedMs, handles: string[], requests: string[] }`
 *
 * ## Limitations
 *
 * - Constructor names give type information but not "which plugin owns
 *   this handle". To get plugin attribution, we'd need to monkey-patch
 *   FSWatcher / Timer constructors and capture creation stack traces. That's
 *   out of W136 SW5 scope (would be Q3a "Heavy" investigation).
 * - On Windows, SIGUSR2 doesn't exist; we only use IPC. Linux/macOS support
 *   both signals + IPC for parity with future cross-platform investigations.
 *
 * ## Future work (W137+)
 *
 * If handle types alone don't pinpoint the culprit, escalate to:
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

  process.stderr.write(`\n[wave136-trace] === handle dump (${reason}) ===\n`)
  process.stderr.write(`[wave136-trace] elapsed: ${elapsed}ms\n`)
  process.stderr.write(`[wave136-trace] active handles: ${handles.length}\n`)
  for (const [name, count] of [...handleCounts.entries()].sort()) {
    process.stderr.write(`[wave136-trace]   - ${name}${count > 1 ? ` × ${count}` : ""}\n`)
  }
  process.stderr.write(`[wave136-trace] active requests: ${requests.length}\n`)
  for (const [name, count] of [...requestCounts.entries()].sort()) {
    process.stderr.write(`[wave136-trace]   - ${name}${count > 1 ? ` × ${count}` : ""}\n`)
  }
  process.stderr.write(`[wave136-trace] === end dump ===\n\n`)

  // Also write to file so orchestrator can capture even if stderr is buffered
  const traceDir = path.join(process.cwd(), ".wave136-trace")
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
        type: "wave136-trace-dump-reply",
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
  if (msg && typeof msg === "object" && msg.type === "wave136-trace-dump") {
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
const MAX_WAIT_MS = parseInt(process.env.WAVE136_TRACE_MAX_WAIT_MS ?? "300000", 10)
const watchdog = setTimeout(() => {
  dumpHandles("watchdog-timeout")
  process.exit(2)
}, MAX_WAIT_MS)
watchdog.unref()
