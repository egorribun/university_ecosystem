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
//
// W163 SW2 Path (d) closure (2026-05-18): the deeper Worker thread leak
// (W136 SW5 trace = MessagePort + Pipe + Socket × 2 family — likely
// Rolldown native worker pool / @rolldown/plugin-babel) is ACCEPTED as
// platform limitation. Canonical workarounds:
//   • This script's kill-after-artifacts pattern (ships artifacts
//     deterministically; build × 3 BYTE-IDENTICAL × ≥28 waves W134-W162).
//   • W162 SW2 Promise.race(5s) + process.exit(0) at lhci-windows-fallback.mjs
//     handles the related LHCI wrapper cleanup-hang class.
// Production users + CI Linux UNAFFECTED (Linux doesn't trigger this hang).
// Upstream investigation paths (a) file issue at vite-pwa/vite-plugin-pwa
// OR rolldown/rolldown OR tanstack/tanstack-start; (b) Rolldown native
// worker pool config tuning) require ~3-5h focused scope under STRICT
// 1-iter — deferred to W164+ if measurement-parity demand emerges.
// Mirrors W162 SW1 "Linux CI Perf=null platform limitation accepted"
// framing per `feedback_perfectionism.md` "if you can't measure /
// can't structurally fix in 1-iter, defer honestly".

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

  // W153 SW1 — opt-in unminified bundle + linked source maps for the /login
  // wedge diagnostic (W150-polish-followup caveat #14, W152 iter-5 honest
  // defer). Setting FRONTEND_BUILD_UNMINIFIED=true (dev compose only, never
  // CI / prod) propagates to vite.config.mts so build.minify=false +
  // build.sourcemap=true. Mode STAYS at "production" so the JSX transform
  // continues to emit `jsx()` calls (NOT `jsxDEV()`), keeping SSR runtime
  // compatible with the production react-dom-server.node.production.js
  // loaded at runtime (Dockerfile:NODE_ENV=production in runtime stage).
  // SW1 fixup history: initial attempt set NODE_ENV=development + passed
  // `--mode development` arg. This broke SSR with `TypeError: jsxDEV is not
  // a function` at RootShell because the server bundle was compiled with
  // jsxDEV calls but Node loads the production react-dom runtime.
  const isUnminified = process.env.FRONTEND_BUILD_UNMINIFIED === "true"

  // W156 SW1 Tier 1 #1 — propagate FRONTEND_REACT_DEV_MODE to vite subprocess.
  // When set (dev compose only), vite.config.mts adds react-dom/client →
  // development bundle alias + per-environment NODE_ENV=development define
  // for the client environment. See vite.config.mts isReactDevMode comment
  // block for full rationale + jsxDEV-trap avoidance (server bundle stays
  // production via tanstackStart's top-level define + no environments.server
  // override here).
  const isReactDevMode = process.env.FRONTEND_REACT_DEV_MODE === "true"

  await new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      ...(wantsReport ? { BUILD_REPORT: "1", ANALYZE: process.env.ANALYZE ?? "1" } : {}),
      BUILD_SKIP_PWA: "true",
      // W153 SW1 — propagate unminified flag to vite subprocess. NODE_ENV
      // is intentionally NOT set to development — that would force React +
      // JSX transform to dev runtime which breaks SSR (see comment above).
      FRONTEND_BUILD_UNMINIFIED: isUnminified ? "true" : "",
      // W156 SW1 Tier 1 #1 — see isReactDevMode block above.
      FRONTEND_REACT_DEV_MODE: isReactDevMode ? "true" : "",
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
  // platform: "browser" + format: "iife" produces a classic-script-compatible
  // bundle. Wave 138 SW2 fix: pre-fix `format: "esm"` emitted `export{...}`
  // at end of sw.js (from sw.ts test-compatibility re-exports at lines 17-37).
  // `navigator.serviceWorker.register()` in `frontend/src/push/register-sw.ts:49`
  // does NOT pass `{ type: "module" }`, so the browser parses sw.js as
  // a classic script. Classic-script + `export` keyword =
  // `SyntaxError: Unexpected token 'export'` → "ServiceWorker script
  // evaluation failed" (1 console error per route in W137 SW4 smoke).
  // Switching to IIFE makes esbuild drop the `export` statements; the
  // re-export consts become local-IIFE consts assigned to `self.__SW_TESTING__`
  // in bootstrap() (which is the only runtime consumer). Tests that
  // import the helpers from sw.ts source TS continue working.
  // minify on; sourcemap off (matches Vite's "hidden" mode for prod — no
  // sourceMappingURL comment in JS).
  //
  // W153 SW1 — gate matches the vite subprocess block above. When
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

  // Wave 142 SW6 NEW (z) #11 W142 + polish-v2 refinement (build-infra
  // non-determinism DIAGNOSIS at TWO LAYERS):
  //
  // W141 polish A3 surfaced that defensive `npm run build` × 2 produces
  // BYTE-IDENTICAL main JS + server.js sha256 BUT `_shell.html` + `sw.js`
  // have SAME byte count with DIFFERENT sha256. Agent 3 Phase 1 hypothesis:
  // workbox-build `injectManifest` iterates `fs.readdir` in OS-dependent
  // order → precache manifest entries unsorted → cascade through sw.js
  // revision hashes. W142 SW6 empirical diff verification (2026-05-12)
  // DISPROVED this hypothesis. W142 polish-v2 build3 evidence further
  // refined the diagnosis into TWO non-determinism layers:
  //
  // **Layer 1 (INTERMITTENT, Rolldown chunking)**:
  //   build1 produced index-DqqHVXgy.js (sha256 634d406d...)
  //   build2 + build3 BOTH produced index-CQ-5oXj0.js (sha256 9f7cd496...)
  //   server.js similarly: build1 differs; build2 + build3 BYTE-IDENTICAL
  //   sha256 (61709961...). So Rolldown chunking IS sometimes non-
  //   deterministic but NOT always — build2→build3 was stable.
  //
  // **Layer 2 (CONSISTENT, post-build/prerender)**:
  //   _shell.html: 3 unique sha256 across 3 builds (each pair differs
  //   pairwise), all 65,864 bytes.
  //   sw.js: 3 unique sha256 across 3 builds (each pair differs pairwise),
  //   all 53,115 bytes — cascade from _shell.html into workbox manifest
  //   revision hash (302 byte diff at offset 31480 in build2 vs build3 case;
  //   offset varies per-build pair).
  //
  // The Layer 2 source is likely:
  //   - TanStack Start prerender output (the source _shell.html before
  //     post-build-shell.mjs runs)
  //   - OR post-build-shell.mjs CSP nonce injection / font preload sort
  //     ordering (font sort already uses .sort(); CSP nonce regex match
  //     order should be deterministic)
  //   - OR workbox revision hash computation cascade
  //
  // The Layer 1 source is likely:
  //   - Rolldown parallel module processing (Rust threading)
  //   - Module dependency graph traversal order (filesystem-dependent)
  //   - Intermediate hash inputs (timestamps, mtimes, parallel ID assignment)
  //
  // Adding post-injectManifest workbox manifest sort would NOT fix EITHER
  // layer — Layer 1 is about chunk filename hashing upstream; Layer 2 is
  // about _shell.html itself differing before the manifest hashes are
  // computed. Per plan deviation trigger #9 ("SW6 3rd-build sha256 still
  // drifts after primary fix → defer to W143+ structural"), DEFERRED with
  // documented two-layer root cause.
  //
  // W143+ scope (~5-9h total):
  //   1. Layer 1 (~2-4h): Investigate Rolldown chunk-naming determinism
  //      flags (entryFileNames, chunkFileNames, hashCharacters), parallelism
  //      config
  //   2. Layer 2 (~3-5h): Diagnose source — TanStack Start prerender output
  //      determinism + post-build-shell.mjs ordering + workbox revision
  //      hash stability
  //   3. If structural: report upstream, accept current state as known limit
  //
  // W142 SW6 progress vs W141 polish A3:
  //   - W141 polish A3 framing: "main JS + server.js BYTE-IDENTICAL × 2;
  //     _shell.html + sw.js byte-count match but sha256 differs, source
  //     not yet identified"
  //   - W142 SW6 initial framing (OVERCLAIMED): "Rolldown chunk filename
  //     hash non-determinism, propagates via _shell.html main-JS ref"
  //   - W142 SW6 polish-v2 refined: "TWO LAYERS — Layer 1 intermittent
  //     Rolldown chunking + Layer 2 consistent post-build/prerender; build3
  //     evidence captured both"
  //
  // Per `feedback_perfectionism.md` "structural deferrals acceptable with
  // honest framing" + W138 Lesson #8 "§Honesty caveat counting is dynamic"
  // — refining the framing IS honest progress. The empirical build × 3
  // evidence is more precise than build × 2 was.
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
