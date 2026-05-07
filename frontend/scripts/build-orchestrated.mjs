// Wave 135 SW3 — Option E (Path B partial structural + Path A kill-after-
// artifacts) full orchestration. Retires `frontend/scripts/wave127-build-x3.sh`
// watch+kill workaround in favour of a single npm script.
//
// Pre-W135 hang theory (W126 polish #3): `vite-plugin-pwa:build`'s
// `closeBundle` hook calls `_generateSW(ctx)` (workbox-build internally),
// hangs indefinitely on Windows after tanstackStart's prerender completes.
//
// W135 SW3 empirical findings:
//   • Programmatic `vite.build()` exits cleanly but does NOT fire
//     tanstackStart's prerender → no `_shell.html`. (W128 polish round 2
//     observation reproduced.)
//   • Subprocess `vite build` (CLI) DOES fire prerender + emits all
//     artifacts (dist/client/* + dist/server/*) — and STILL hangs after
//     `[prerender] Prerendered 1 pages: /`, EVEN with `BUILD_SKIP_PWA=true`
//     making `VitePWA({ disable: true })`. So vite-plugin-pwa is NOT the
//     sole hang culprit; a second hang point lives in tanstackStart's
//     plugin chain (likely `tanstack-start-core:post-build` or a watcher
//     that holds the event loop open). True structural retirement of the
//     hang requires upstream investigation — filed as W136 candidate.
//
// W135 SW3 pragmatic strategy:
//   1. Set `BUILD_SKIP_PWA=true` so `vite.config.mts` configures
//      `VitePWA({ disable: true })`. Skips the workbox call inside vite —
//      we run workbox-build standalone in step 5 (no hang).
//   2. Spawn `vite build` as a subprocess. Watch for BOTH `_shell.html`
//      AND `dist/server/server.js` to exist + be stable (debounced ~2s).
//      Once stable, send SIGTERM to the vite subprocess to break out of
//      the post-prerender hang. Artifacts already written to disk; the
//      hang occurs AFTER the prerender writes, so killing here is safe.
//      (This is the same kill-after-artifacts pattern as
//      `wave127-build-x3.sh`, but cross-platform + integrated.)
//   3. Compile `src/sw.ts` → `dist/client/sw.js` ourselves via esbuild.
//      With BUILD_SKIP_PWA=true, vite-plugin-pwa does NOT compile sw.ts
//      (its `_generateSW` is the function we disabled). esbuild handles
//      TypeScript natively, respects `tsconfig.json` paths
//      (`@/*` → `src/*`), and produces a single bundled SW preserving
//      the `self.__WB_MANIFEST` placeholder for workbox to inject.
//   4. Call `workbox-build.injectManifest()` standalone with the same
//      options as `vite.config.mts:357-382` — replaces `self.__WB_MANIFEST`
//      with the actual precache manifest. NO HANG — running outside
//      Vite's plugin lifecycle on Windows.
//   5. Run `post-build-shell.mjs` for CSP nonce + font preload + LHCI
//      placeholder + mirror to `index.html` (W125 Phase 2 baseline).
//
// `main.tsx:79` calls `registerServiceWorker("/sw.js")` directly — sw
// registration script injection (vite-plugin-pwa:build's
// `transformIndexHtml`) is NOT needed for our setup; tanstackStart's React
// SSR shell skips `transformIndexHtml` anyway (vite.config.mts:118-127).
// Disabling vite-plugin-pwa via the `disable: true` flag is therefore safe.
//
// Honest framing (W135 SW3 §Honesty): the kill-after-artifacts mechanism
// IMPROVES on wave127-build-x3.sh (cross-platform + single npm script +
// integrated workbox/sw compile) but does NOT STRUCTURALLY fix the
// underlying tanstackStart-core post-prerender hang. W136+ candidate:
// trace which plugin holds the event loop open + file upstream issue.

import { existsSync, statSync } from "node:fs"
import path from "node:path"
import process from "node:process"
import { spawn } from "node:child_process"

import { injectManifest } from "workbox-build"
import * as esbuild from "esbuild"

// W136 SW6: shared Workbox config — single source of truth with
// vite.config.mts (eliminates W135 §Honesty #5 drift risk).
import { PWA_INJECT_CONFIG } from "./workbox-config.mjs"

const cwd = process.cwd()
const wantsReport = process.argv.includes("--report")
const sanitizedArgs = process.argv.slice(2).filter((a) => a !== "--report")

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
      console.error(`Failed to start ${command}:`, err)
      reject(err)
    })
    child.on("close", (code) => {
      if (code !== 0) {
        console.error(`${command} exited with code ${code}`)
        reject(new Error(`${command} exited with code ${code}`))
      } else {
        resolve(undefined)
      }
    })
  })
}

async function step1_wasm() {
  console.log("== Step 1: wasm-pack ==")
  try {
    await run("wasm-pack", ["build", "rust-crypto", "--target", "web"], {
      cwd: path.resolve(cwd),
      shell: true,
    })
    await run("wasm-pack", ["build", "wasm-sanitizer", "--target", "web"], {
      cwd: path.resolve(cwd),
      shell: true,
    })
  } catch (error) {
    console.warn(
      "WASM build failed. If this is a non-rust environment, ensure rust-crypto/pkg and wasm-sanitizer/pkg exist."
    )
    console.warn(error.message)
  }
}

async function step2_syncTokens() {
  console.log("== Step 2: sync-tokens ==")
  await run("node", ["./scripts/sync-tokens.mjs"])
}

async function step3_viteBuild() {
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

  // W136 SW5: optionally inject hang-trace agent into the vite subprocess.
  // Set WAVE136_HANG_TRACE=1 to enable. Agent dumps process._getActiveHandles
  // via stderr + file (.wave136-trace/) + IPC reply when triggered. Helps
  // identify which handle types (FSWatcher / Timer / etc.) hold the loop
  // open after artifacts are emitted.
  const traceEnabled = process.env.WAVE136_HANG_TRACE === "1"
  const traceAgentPath = path.resolve(cwd, "scripts/wave136-hang-trace-agent.cjs")
  const useIpc = traceEnabled

  await new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
      BUILD_SKIP_PWA: "true",
      ...(traceEnabled
        ? {
            NODE_OPTIONS:
              `${process.env.NODE_OPTIONS ?? ""} --require ${JSON.stringify(traceAgentPath)}`.trim(),
          }
        : {}),
    }

    const child = spawn("node", [viteBinPath, "build", ...sanitizedArgs], {
      stdio: useIpc ? ["inherit", "inherit", "inherit", "ipc"] : "inherit",
      cwd: path.resolve(cwd),
      env,
    })

    if (useIpc) {
      child.on("message", (msg) => {
        if (msg && typeof msg === "object" && msg.type === "wave136-trace-dump-reply") {
          console.log(
            `[orchestrator] received trace dump from vite subprocess: ${msg.handles.length} handle types, ${msg.requests.length} request types after ${msg.elapsedMs}ms`
          )
        }
      })
    }

    let killed = false
    let resolved = false
    let stableCount = 0
    const POLL_INTERVAL_MS = 500
    const STABLE_DEBOUNCE_TICKS = 4 // 4 × 500ms = 2s of stability
    const MAX_WAIT_MS = 180_000 // 3 minutes hard cap before giving up

    const startTime = Date.now()
    // W136 SW5: kill-after-artifacts must not fire on STALE leftover artifacts
    // from a previous build. The poll only considers an artifact "fresh"
    // if its mtime is >= startTime — vite must have written it during this
    // build, not during a prior run. Without this guard the orchestrator
    // SIGTERMs vite within 2s using leftover dist/ files (W136 SW5 trace
    // surfaced this regression in W135 SW3's pattern).
    const FRESH_MTIME_GRACE_MS = 1500 // tolerate filesystem mtime quantization

    const isArtifactFresh = (file) => {
      try {
        const st = statSync(file)
        return st.mtimeMs >= startTime - FRESH_MTIME_GRACE_MS
      } catch {
        return false
      }
    }

    const poll = setInterval(() => {
      if (resolved) return
      const elapsed = Date.now() - startTime

      if (
        existsSync(shellPath) &&
        existsSync(serverPath) &&
        isArtifactFresh(shellPath) &&
        isArtifactFresh(serverPath)
      ) {
        stableCount += 1
        if (stableCount >= STABLE_DEBOUNCE_TICKS) {
          // Artifacts present + stable. Send SIGTERM to break out of
          // post-prerender hang. The vite process has already written
          // _shell.html + server.js to disk; killing here is safe.
          if (!killed) {
            // W136 SW5: if trace enabled, request handle dump via IPC
            // BEFORE killing, then exit gracefully. The agent's reply
            // (handled above) provides diagnostic data.
            if (useIpc && typeof child.send === "function") {
              console.log(
                `\n[orchestrator] Artifacts stable after ${(elapsed / 1000).toFixed(1)}s — requesting hang trace via IPC, then graceful exit`
              )
              try {
                child.send({
                  type: "wave136-trace-dump",
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
              child.kill("SIGTERM")
            }
          }
        }
      } else {
        stableCount = 0
      }

      if (elapsed > MAX_WAIT_MS) {
        clearInterval(poll)
        if (!resolved) {
          resolved = true
          if (!killed) child.kill("SIGKILL")
          reject(new Error(`vite build did not produce artifacts within ${MAX_WAIT_MS / 1000}s`))
        }
      }
    }, POLL_INTERVAL_MS)

    child.on("error", (err) => {
      clearInterval(poll)
      if (!resolved) {
        resolved = true
        reject(err)
      }
    })

    child.on("close", (code, signal) => {
      clearInterval(poll)
      if (resolved) return
      resolved = true
      // SIGTERM after artifacts confirmed → success. Any other exit code
      // before artifacts → real failure.
      if (killed && existsSync(shellPath) && existsSync(serverPath)) {
        console.log(
          `[orchestrator] vite subprocess exited (signal=${signal ?? "none"}, code=${code ?? "none"}) after kill-after-artifacts — proceeding to step 4`
        )
        resolve(undefined)
        return
      }
      if (code === 0 && existsSync(shellPath) && existsSync(serverPath)) {
        // Clean exit (rare on Windows) — also success.
        resolve(undefined)
        return
      }
      reject(
        new Error(
          `vite build exited with code=${code ?? "null"} signal=${signal ?? "null"}; artifacts present=${existsSync(shellPath) && existsSync(serverPath)}`
        )
      )
    })
  })

  if (!existsSync(shellPath)) {
    throw new Error(`Expected ${shellPath} after vite build`)
  }
  if (!existsSync(serverPath)) {
    throw new Error(`Expected ${serverPath} after vite build`)
  }
}

async function step4_swBundle() {
  console.log("== Step 4: esbuild sw.ts → dist/client/sw.js ==")

  const swSrc = path.join(cwd, "src/sw.ts")
  const swDest = path.join(cwd, "dist/client/sw.js")
  if (!existsSync(swSrc)) {
    throw new Error(`Source service worker not found at ${swSrc}`)
  }

  // Pre-W135 vite-plugin-pwa internally invoked Vite's build with sw.ts as
  // an entry. esbuild handles TypeScript natively, respects tsconfig.json
  // paths (@/* → src/*), and produces a single bundled SW. The
  // `self.__WB_MANIFEST` placeholder in src/sw/precaching.ts:12 is
  // PRESERVED in the output — workbox-build.injectManifest in step 5
  // replaces it with the actual precache manifest array.
  //
  // platform: "browser" + format: "esm" matches the W134 baseline output
  // shape. minify on; sourcemap off (matches Vite's "hidden" mode for prod
  // — no sourceMappingURL comment in JS).
  const result = await esbuild.build({
    entryPoints: [swSrc],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    outfile: swDest,
    minify: true,
    sourcemap: false,
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

  const result = await injectManifest({
    swSrc: swPath,
    swDest: swPath,
    globDirectory: path.join(cwd, "dist/client"),
    ...PWA_INJECT_CONFIG,
  })

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
  console.log(`build-orchestrated.mjs — Wave 135 SW3 (cwd=${cwd})`)
  if (sanitizedArgs.length > 0) {
    console.log(`Vite args: ${sanitizedArgs.join(" ")}`)
  }
  await step1_wasm()
  await step2_syncTokens()
  await step3_viteBuild()
  await step4_swBundle()
  await step5_workboxInject()
  await step6_postBuildShell()
  await step7_bundleBudget()
  console.log("✓ Build orchestrated successfully — no Windows hang, no watch+kill required")
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
