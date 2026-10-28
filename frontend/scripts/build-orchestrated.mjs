/**
 * Cross-platform frontend build orchestration.
 *
 * The Vite CLI is required for TanStack Start prerendering, but on Windows its
 * plugin chain can retain event-loop handles after both client and server
 * artifacts are complete. This runner disables the in-plugin PWA phase,
 * watches fresh `_shell.html` and `server.js` artifacts until stable, then
 * terminates the lingering child process. It subsequently bundles the service
 * worker, injects the Workbox manifest, processes the static shell, and checks
 * the optional bundle report.
 *
 * `BUILD_HANG_TRACE=1` injects build-hang-trace-agent.cjs for handle evidence.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { rename, rm } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { execFile, spawn } from "node:child_process"
import { createHash } from "node:crypto"
import { fileURLToPath } from "node:url"

import { injectManifest } from "workbox-build"
import * as esbuild from "esbuild"

// Shared with vite.config.mts to keep Workbox behavior identical.
import { PWA_INJECT_CONFIG } from "./workbox-config.mjs"
import { buildWasmArtifacts } from "./build-wasm.mjs"

const cwd = process.cwd()
const wantsReport = process.argv.includes("--report")
const sanitizedArgs = process.argv.slice(2).filter((a) => a !== "--report")

const ARTIFACT_METADATA_FIELDS = ["dev", "ino", "mode", "size", "mtimeNs", "ctimeNs", "birthtimeNs"]

function artifactMetadataToken(stats) {
  return ARTIFACT_METADATA_FIELDS.map((field) => String(stats[field] ?? "")).join(":")
}

function readStableArtifact(filePath, { startedAt, freshnessGraceMs }, io) {
  try {
    const before = io.statSync(filePath, { bigint: true })
    if (!before.isFile()) return null

    if (startedAt !== null && startedAt !== undefined) {
      const modifiedAtMs = Number(before.mtimeNs) / 1_000_000
      if (!Number.isFinite(modifiedAtMs) || modifiedAtMs < startedAt - freshnessGraceMs) {
        return null
      }
    }

    const contents = io.readFileSync(filePath)
    if (!(contents instanceof Uint8Array)) return null

    const after = io.statSync(filePath, { bigint: true })
    const beforeToken = artifactMetadataToken(before)
    const afterToken = artifactMetadataToken(after)
    if (
      !after.isFile() ||
      beforeToken !== afterToken ||
      before.size !== BigInt(contents.byteLength)
    ) {
      return null
    }

    return {
      metadata: afterToken,
      digest: createHash("sha256").update(contents).digest("hex"),
      text: Buffer.isBuffer(contents)
        ? contents.toString("utf8")
        : Buffer.from(contents).toString("utf8"),
    }
  } catch {
    // The build can replace or remove an artifact while a poll samples it.
    return null
  }
}

/**
 * Capture a usable, fresh (when startedAt is provided), paired Vite artifact
 * snapshot. Content hashes make same-size writes visible even when timestamp
 * resolution is too coarse to distinguish them.
 */
export function captureViteArtifactSnapshot(
  { shellPath, serverPath, assetsDir, startedAt = null, freshnessGraceMs = 1500 } = {},
  io = { statSync, readFileSync, readdirSync }
) {
  if (
    typeof shellPath !== "string" ||
    typeof serverPath !== "string" ||
    typeof assetsDir !== "string" ||
    !Number.isFinite(freshnessGraceMs) ||
    freshnessGraceMs < 0 ||
    (startedAt !== null && startedAt !== undefined && !Number.isFinite(startedAt))
  ) {
    return null
  }

  const options = { startedAt, freshnessGraceMs }
  const shell = readStableArtifact(shellPath, options, io)
  const server = readStableArtifact(serverPath, options, io)
  if (!shell || !server || !/<html\b/i.test(shell.text) || server.text.trim().length <= 32) {
    return null
  }

  try {
    const hasClientAsset = io.readdirSync(assetsDir).some((file) => /\.(?:js|css|wasm)$/.test(file))
    if (!hasClientAsset) return null
  } catch {
    return null
  }

  const fingerprint = createHash("sha256")
    .update(
      JSON.stringify([
        ["shell", shell.metadata, shell.digest],
        ["server", server.metadata, server.digest],
      ])
    )
    .digest("hex")

  return { fingerprint }
}

/** Count consecutive identical usable paired snapshots. */
export function advanceArtifactStability(previousState, snapshot, requiredTicks = 4) {
  const fingerprint =
    typeof snapshot?.fingerprint === "string" && snapshot.fingerprint.length > 0
      ? snapshot.fingerprint
      : null
  if (!fingerprint) return { fingerprint: null, count: 0, stable: false }

  const previousCount =
    Number.isInteger(previousState?.count) && previousState.count > 0 ? previousState.count : 0
  const count = previousState?.fingerprint === fingerprint ? previousCount + 1 : 1
  return { fingerprint, count, stable: count >= requiredTicks }
}

const parseMemoryLimit = (rawValue, fallback) => {
  const parsed = Number.parseInt(rawValue ?? "", 10)
  return Number.isFinite(parsed) && parsed >= 256 ? parsed : fallback
}

function parseBuildMaxWaitMs(rawValue) {
  if (rawValue === undefined || rawValue === "") return 360_000

  const milliseconds = Number(rawValue)
  if (!Number.isSafeInteger(milliseconds) || milliseconds < 1 || milliseconds > 2_147_483_647) {
    throw new Error("BUILD_MAX_WAIT_MS must be an integer from 1 to 2147483647 milliseconds")
  }
  return milliseconds
}

const readProcessRssBytes = (pid) => {
  if (!pid) return Promise.resolve(null)

  if (process.platform === "win32") {
    const command =
      `$p = Get-Process -Id ${pid} -ErrorAction SilentlyContinue; ` +
      "if ($p) { [Console]::Write($p.WorkingSet64) }"
    return new Promise((resolve) => {
      execFile(
        "powershell.exe",
        ["-NoProfile", "-NonInteractive", "-Command", command],
        { windowsHide: true, timeout: 1500 },
        (error, stdout) => {
          if (error) {
            resolve(null)
            return
          }
          const bytes = Number.parseInt(stdout.trim(), 10)
          resolve(Number.isFinite(bytes) ? bytes : null)
        }
      )
    })
  }

  try {
    const status = readFileSync(`/proc/${pid}/status`, "utf8")
    const match = status.match(/^VmRSS:\s+(\d+)\s+kB$/m)
    return Promise.resolve(match ? Number.parseInt(match[1], 10) * 1024 : null)
  } catch {
    return Promise.resolve(null)
  }
}

const terminateProcessTree = (pid) => {
  if (!pid) return
  if (process.platform === "win32") {
    const killer = spawn("taskkill.exe", ["/PID", String(pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    })
    killer.unref()
    return
  }
  try {
    process.kill(pid, "SIGKILL")
  } catch {
    // The child may already have exited between the RSS probe and the kill.
  }
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
      ...(options.env ?? {}),
    }
    const child = spawn(command, args, {
      stdio: "inherit",
      ...options,
      env,
    })
    child.on("error", (err) => {
      console.error("Failed to start command:", command, err)
      reject(err)
    })
    child.on("close", (code) => {
      if (code !== 0) {
        console.error("Command exited with code:", command, code)
        reject(new Error(`${command} exited with code ${code}`))
      } else {
        resolve(undefined)
      }
    })
  })
}

async function step1_wasm() {
  console.log("== Step 1: wasm-pack ==")
  await buildWasmArtifacts(path.resolve(cwd))
}

async function step2_syncTokens() {
  console.log("== Step 2: sync-tokens ==")
  await run("node", ["./scripts/sync-tokens.mjs"])
}

export async function step3_viteBuild(configuredMaxWaitMs = process.env.BUILD_MAX_WAIT_MS) {
  const MAX_WAIT_MS = parseBuildMaxWaitMs(configuredMaxWaitMs)
  console.log("== Step 3: vite build (BUILD_SKIP_PWA=true) + kill-after-artifacts ==")

  // Spawn `vite build` as a subprocess. Watch for both spa-mode artifacts
  // to be emitted, then SIGTERM the subprocess to break out of the
  // post-prerender hang (see file-header comment for empirical findings).
  //
  // Invoke vite via node + the package's bin entry point — `spawn("vite")`
  // doesn't resolve through node_modules/.bin on Windows even with
  // shell: true. node + bin path is portable across Windows / Linux / CI.
  const viteBinPath = path.resolve(cwd, "node_modules/vite/bin/vite.js")
  const shellPath = path.join(cwd, "dist/client/_shell.html")
  const serverPath = path.join(cwd, "dist/server/server.js")

  const assetsDir = path.join(cwd, "dist", "client", "assets")
  const hasUsableViteArtifacts = () =>
    captureViteArtifactSnapshot({ shellPath, serverPath, assetsDir }) !== null

  // Optionally inject the hang-trace agent into the Vite subprocess.
  // Set BUILD_HANG_TRACE=1 to enable. The agent reports active handles
  // via stderr + file (.build-hang-trace/) + IPC reply when triggered. This
  // helps identify which handle types (FSWatcher / Timer / etc.) hold the loop
  // open after artifacts are emitted.
  const traceEnabled = process.env.BUILD_HANG_TRACE === "1"
  const traceAgentPath = path.resolve(cwd, "scripts/build-hang-trace-agent.cjs")
  const useIpc = traceEnabled

  // FRONTEND_BUILD_UNMINIFIED=true enables an unminified diagnostic bundle
  // with linked source maps. Mode stays at "production" so the JSX transform
  // continues to emit `jsx()` calls (NOT `jsxDEV()`), keeping SSR runtime
  // compatible with the production react-dom-server.node.production.js
  // loaded at runtime. Never enable this in CI or production deployments.
  const isUnminified = process.env.FRONTEND_BUILD_UNMINIFIED === "true"

  // Resource-safety guard: Rolldown's native worker pool can retain memory
  // after client emission while TanStack Start is producing the SSR bundle.
  // Keep the default below an unbounded process, but above the last verified
  // successful Windows build peak. Operators can tighten or raise the ceiling
  // explicitly for machines with different memory budgets.
  const maxRssMb = parseMemoryLimit(process.env.FRONTEND_BUILD_MAX_RSS_MB, 1536)
  const maxOldSpaceMb = parseMemoryLimit(process.env.FRONTEND_BUILD_MAX_OLD_SPACE_MB, 1536)
  const inheritedNodeOptions = process.env.NODE_OPTIONS ?? ""
  const hasOldSpaceLimit = /(?:^|\s)--max-old-space-size(?:=|\s)/.test(inheritedNodeOptions)

  // FRONTEND_REACT_DEV_MODE propagates a client-only diagnostic mode.
  // When set locally, vite.config.mts adds react-dom/client →
  // development bundle alias + per-environment NODE_ENV=development define
  // for the client environment. See vite.config.mts isReactDevMode comment
  // block for full rationale + jsxDEV-trap avoidance (server bundle stays
  // production via tanstackStart's top-level define + no environments.server
  // override here).
  const isReactDevMode = process.env.FRONTEND_REACT_DEV_MODE === "true"
  const rolldownWorkerThreads = process.env.ROLLDOWN_WORKER_THREADS?.trim() || "4"

  const nodeOptions = [
    inheritedNodeOptions,
    hasOldSpaceLimit ? "" : `--max-old-space-size=${maxOldSpaceMb}`,
    traceEnabled ? `--require ${JSON.stringify(traceAgentPath)}` : "",
  ]
    .filter(Boolean)
    .join(" ")

  await new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
      BUILD_SKIP_PWA: "true",
      // Propagate the unminified flag. NODE_ENV
      // is intentionally NOT set to development — that would force React +
      // JSX transform to dev runtime which breaks SSR (see comment above).
      FRONTEND_BUILD_UNMINIFIED: isUnminified ? "true" : "",
      // See isReactDevMode above.
      FRONTEND_REACT_DEV_MODE: isReactDevMode ? "true" : "",
      // Bound Rolldown's native Tokio pool independently of the host CPU count.
      ROLLDOWN_WORKER_THREADS: rolldownWorkerThreads,
      NODE_OPTIONS: nodeOptions,
    }

    console.log(
      `[orchestrator] Vite child RSS watchdog: ${maxRssMb} MB; V8 heap cap: ${maxOldSpaceMb} MB`
    )

    const child = spawn("node", [viteBinPath, "build", ...sanitizedArgs], {
      stdio: useIpc ? ["inherit", "inherit", "inherit", "ipc"] : "inherit",
      cwd: path.resolve(cwd),
      env,
    })

    if (useIpc) {
      child.on("message", (msg) => {
        if (msg && typeof msg === "object" && msg.type === "build-hang-trace-dump-reply") {
          console.log(
            `[orchestrator] received trace dump from vite subprocess: ${msg.handles.length} handle types, ${msg.requests.length} request types after ${msg.elapsedMs}ms`
          )
        }
      })
    }

    let killed = false
    let resolved = false
    let stabilityState = { fingerprint: null, count: 0, stable: false }
    let memoryProbeInFlight = false
    const POLL_INTERVAL_MS = 500
    const STABLE_DEBOUNCE_TICKS = 4 // 4 × 500ms = 2s of stability
    const startTime = Date.now()
    // Never terminate a build based on stale artifacts from a previous run.
    const FRESH_MTIME_GRACE_MS = 1500 // tolerate filesystem mtime quantization

    let memoryPoll
    const checkMemory = async () => {
      if (resolved || killed || memoryProbeInFlight) return
      memoryProbeInFlight = true
      try {
        const rssBytes = await readProcessRssBytes(child.pid)
        if (rssBytes === null || rssBytes <= maxRssMb * 1024 * 1024 || resolved) return

        const rssMb = (rssBytes / 1024 / 1024).toFixed(1)
        resolved = true
        clearInterval(poll)
        clearInterval(memoryPoll)
        terminateProcessTree(child.pid)
        reject(
          new Error(
            `vite child exceeded RSS watchdog (${rssMb} MB > ${maxRssMb} MB); process tree terminated`
          )
        )
      } finally {
        memoryProbeInFlight = false
      }
    }

    const poll = setInterval(() => {
      if (resolved) return
      const elapsed = Date.now() - startTime

      const snapshot = captureViteArtifactSnapshot({
        shellPath,
        serverPath,
        assetsDir,
        startedAt: startTime,
        freshnessGraceMs: FRESH_MTIME_GRACE_MS,
      })
      stabilityState = advanceArtifactStability(stabilityState, snapshot, STABLE_DEBOUNCE_TICKS)
      if (stabilityState.stable) {
        // Artifacts present + stable. Send SIGTERM to break out of
        // post-prerender hang. The vite process has already written
        // _shell.html + server.js to disk; killing here is safe.
        if (!killed) {
          // If tracing is enabled, request a handle dump via IPC
          // BEFORE killing, then exit gracefully. The agent's reply
          // (handled above) provides diagnostic data.
          if (useIpc && typeof child.send === "function") {
            console.log(
              `\n[orchestrator] Artifacts stable after ${(elapsed / 1000).toFixed(1)}s — requesting hang trace via IPC, then graceful exit`
            )
            try {
              child.send({
                type: "build-hang-trace-dump",
                reason: "orchestrator-artifact-stable",
                thenExit: true,
              })
            } catch {
              // IPC may have closed; fall through to SIGTERM
            }
            killed = true
            // Give the agent ~3s to dump + exit, then SIGTERM as fallback
            setTimeout(() => {
              try {
                child.kill("SIGTERM")
              } catch {
                // best-effort
              }
            }, 3000)
          } else {
            console.log(
              `\n[orchestrator] Artifacts stable after ${(elapsed / 1000).toFixed(1)}s — sending SIGTERM to vite subprocess`
            )
            killed = true
            terminateProcessTree(child.pid)
          }
        }
      }

      if (elapsed > MAX_WAIT_MS) {
        clearInterval(poll)
        if (!resolved) {
          resolved = true
          clearInterval(memoryPoll)
          if (!killed) terminateProcessTree(child.pid)
          reject(new Error(`vite build did not produce artifacts within ${MAX_WAIT_MS / 1000}s`))
        }
      }
    }, POLL_INTERVAL_MS)

    memoryPoll = setInterval(() => {
      void checkMemory()
    }, 2000)
    void checkMemory()

    child.on("error", (err) => {
      clearInterval(poll)
      clearInterval(memoryPoll)
      if (!resolved) {
        resolved = true
        reject(err)
      }
    })

    child.on("close", (code, signal) => {
      clearInterval(poll)
      clearInterval(memoryPoll)
      if (resolved) return
      resolved = true
      // SIGTERM after artifacts confirmed → success. Any other exit code
      // before artifacts → real failure.
      if (killed && hasUsableViteArtifacts()) {
        console.log(
          `[orchestrator] vite subprocess exited (signal=${signal ?? "none"}, code=${code ?? "none"}) after kill-after-artifacts — proceeding to step 4`
        )
        resolve(undefined)
        return
      }
      if (code === 0 && hasUsableViteArtifacts()) {
        // Clean exit (rare on Windows) — also success.
        resolve(undefined)
        return
      }
      reject(
        new Error(
          `vite build exited with code=${code ?? "null"} signal=${signal ?? "null"}; complete artifacts present=${hasUsableViteArtifacts()}`
        )
      )
    })
  })

  if (!hasUsableViteArtifacts()) {
    throw new Error(
      `Vite completed without a usable client shell, server bundle, and client asset set under ${path.join(cwd, "dist")}`
    )
  }
}

async function step4_swBundle() {
  console.log("== Step 4: esbuild sw.ts → dist/client/sw.js ==")

  const swSrc = path.join(cwd, "src/sw.ts")
  const swDest = path.join(cwd, "dist/client/sw.js")
  if (!existsSync(swSrc)) {
    throw new Error(`Source service worker not found at ${swSrc}`)
  }

  // esbuild handles TypeScript natively, respects tsconfig.json
  // paths (@/* → src/*), and produces a single bundled SW. The
  // `self.__WB_MANIFEST` placeholder in src/sw/precaching.ts:12 is
  // PRESERVED in the output — workbox-build.injectManifest in step 5
  // replaces it with the actual precache manifest array.
  //
  // platform: "browser" + format: "iife" produces a classic-script-compatible
  // bundle. An ESM output would emit `export{...}`
  // at end of sw.js (from sw.ts test-compatibility re-exports at lines 17-37).
  // `navigator.serviceWorker.register()` in `frontend/src/push/register-sw.ts:49`
  // does NOT pass `{ type: "module" }`, so the browser parses sw.js as
  // a classic script. Classic-script + `export` keyword =
  // `SyntaxError: Unexpected token 'export'` → "ServiceWorker script
  // evaluation failed".
  // Switching to IIFE makes esbuild drop the `export` statements; the
  // re-export consts become local-IIFE consts assigned to `self.__SW_TESTING__`
  // in bootstrap() (which is the only runtime consumer). Tests that
  // import the helpers from sw.ts source TS continue working.
  // minify on; sourcemap off (matches Vite's "hidden" mode for prod — no
  // sourceMappingURL comment in JS).
  //
  // The diagnostic gate matches the Vite subprocess block above. When
  // FRONTEND_BUILD_UNMINIFIED=true, the service worker bundle ships
  // unminified with inline source maps so SW errors are readable in
  // Chrome DevTools alongside the main client bundle. import.meta.env.*
  // defines STAY at production values — sw.ts production-mode runtime is
  // fine even when unminified, and this avoids any chance of conditionally
  // compiled production-vs-dev code paths breaking at runtime.
  const swIsUnminified = process.env.FRONTEND_BUILD_UNMINIFIED === "true"
  const result = await esbuild.build({
    entryPoints: [swSrc],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    outfile: swDest,
    minify: !swIsUnminified,
    sourcemap: swIsUnminified ? "inline" : false,
    tsconfig: path.join(cwd, "tsconfig.json"),
    define: {
      "import.meta.env.DEV": "false",
      "import.meta.env.PROD": "true",
      "import.meta.env.MODE": '"production"',
    },
    legalComments: "none",
    write: true,
    metafile: false,
    logLevel: "warning",
  })
  if (result.errors.length > 0) {
    throw new Error(`esbuild produced ${result.errors.length} error(s) for sw.ts`)
  }
}

async function step5_workboxInject() {
  console.log("== Step 5: workbox-build.injectManifest (standalone, no Windows hang) ==")

  const swPath = path.join(cwd, "dist/client/sw.js")
  if (!existsSync(swPath)) {
    throw new Error(
      `Compiled service worker not found at ${swPath} — step 4 should have produced it`
    )
  }

  // Workbox 7 rejects `swSrc === swDest` before it scans the source. Stage the
  // generated service worker in the same directory, then atomically replace
  // the un-injected bundle. A same-directory rename keeps the operation on a
  // single filesystem (and therefore atomic on POSIX); Windows may require a
  // short remove-and-rename fallback when the target is still open.
  const workboxTempPath = path.join(
    path.dirname(swPath),
    `.sw-workbox-${process.pid}-${Date.now()}.tmp.js`
  )

  let result
  try {
    result = await injectManifest({
      swSrc: swPath,
      swDest: workboxTempPath,
      globDirectory: path.join(cwd, "dist/client"),
      ...PWA_INJECT_CONFIG,
    })

    try {
      await rename(workboxTempPath, swPath)
    } catch (error) {
      if (!error || !["EEXIST", "EPERM"].includes(error.code)) throw error
      await rm(swPath, { force: true })
      await rename(workboxTempPath, swPath)
    }
  } finally {
    await rm(workboxTempPath, { force: true })
  }

  console.log(
    `Workbox: precached ${result.count} files (${(result.size / 1024 / 1024).toFixed(2)} MB)`
  )
  if (result.warnings.length > 0) {
    console.warn(`Workbox warnings (${result.warnings.length}):`)
    for (const warning of result.warnings) {
      console.warn(`  - ${warning}`)
    }
  }
}

async function step6_postBuildShell() {
  console.log("== Step 6: post-build-shell.mjs ==")
  await run("node", [path.resolve(cwd, "scripts/post-build-shell.mjs")])
}

async function step7_bundleBudget() {
  if (!wantsReport) return
  console.log("== Step 7 (--report): check-bundle-budget.mjs ==")
  await run("node", [path.resolve(cwd, "scripts/check-bundle-budget.mjs")])
}

async function main() {
  const maxWaitMs = parseBuildMaxWaitMs(process.env.BUILD_MAX_WAIT_MS)
  console.log(`build-orchestrated.mjs (cwd=${cwd})`)
  if (sanitizedArgs.length > 0) {
    console.log(`Vite args: ${sanitizedArgs.join(" ")}`)
  }
  await step1_wasm()
  await step2_syncTokens()
  await step3_viteBuild(maxWaitMs)
  await step4_swBundle()
  await step5_workboxInject()
  await step6_postBuildShell()
  await step7_bundleBudget()
  console.log("✓ Build orchestrated successfully — no Windows hang, no watch+kill required")
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : null
const modulePath = fileURLToPath(import.meta.url)
const isEntrypoint =
  invokedPath !== null &&
  (process.platform === "win32"
    ? invokedPath.toLowerCase() === modulePath.toLowerCase()
    : invokedPath === modulePath)

if (isEntrypoint) {
  main().catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
}
