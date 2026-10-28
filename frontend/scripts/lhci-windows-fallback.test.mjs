import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

import {
  assertCompleteLighthouseResults,
  buildSafeCommandInvocation,
  clearLhrDir,
  DEFAULT_PATHS,
  normalizePath,
  parseLhr,
  recoverLhrAfterKnownCleanupFailure,
  resolveLockedLighthouseCli,
  runLighthouse,
  runCommand,
  resolveNpmCliPath,
  resolveLhciPaths,
} from "./lhci-windows-fallback.mjs"
import routePolicyConfig from "./lhci-route-policy-config.cjs"

function completeLhr() {
  return {
    categories: {
      performance: { score: 1 },
      accessibility: { score: 1 },
      "best-practices": { score: 1 },
      seo: { score: 1 },
    },
    audits: {
      "cumulative-layout-shift": { numericValue: 0 },
      "largest-contentful-paint": { numericValue: 100 },
      "total-blocking-time": { numericValue: 0 },
    },
  }
}

function reportPath(args) {
  const output = args.find((arg) => arg.startsWith("--output-path="))?.slice(14)
  assert.ok(output)
  return output
}

function lighthouseCleanupError({
  exitCode = 1,
  description = "lighthouse http://127.0.0.1:4174/login/ run 1",
  tempPath = "C:\\Temp\\lhci\\lighthouse.Abc123",
  stderr,
} = {}) {
  const message =
    stderr ??
    [
      `Error: EPERM: operation not permitted, rmSync '${tempPath}'`,
      "    at Object.rmSync (node:fs:1234:5)",
      "    at Launcher.destroyTmp (C:\\fixture\\node_modules\\chrome-launcher\\dist\\chrome-launcher.js:123:5)",
    ].join("\n")
  const error = new Error(`${description} exited with code ${exitCode}\n${message}`)
  error.command = process.execPath
  error.exitCode = exitCode
  error.description = description
  error.stderr = message
  return error
}

test("Windows fallback uses the canonical ten-route LHCI inventory", () => {
  assert.deepEqual(DEFAULT_PATHS, routePolicyConfig.defaultLhciPaths)
  assert.equal(DEFAULT_PATHS.length, 10)
  assert.deepEqual(DEFAULT_PATHS, [
    "/",
    "/login/",
    "/dashboard/",
    "/news/",
    "/schedule/",
    "/events/",
    "/activity/",
    "/map/",
    "/messenger/",
    "/404/",
  ])
})

test("Windows LHCI path normalization preserves explicit directory slashes", () => {
  assert.equal(normalizePath(""), "/")
  assert.equal(normalizePath("dashboard"), "/dashboard")
  assert.equal(normalizePath("dashboard/"), "/dashboard/")
  assert.equal(normalizePath("/events/"), "/events/")
  assert.equal(normalizePath("  /messenger///  "), "/messenger/")
})

test("Windows fallback uses defaults only for an omitted or empty override", () => {
  assert.deepEqual(resolveLhciPaths(undefined), DEFAULT_PATHS)
  assert.deepEqual(resolveLhciPaths(""), DEFAULT_PATHS)
  assert.deepEqual(resolveLhciPaths(",dashboard/,,events"), ["/", "/dashboard/", "/events"])
})

test("Windows fallback rejects routes that would overwrite each other's reports", () => {
  for (const override of [",root", "a/b,a_b", "a,A"]) {
    assert.throws(() => resolveLhciPaths(override), /Lighthouse report filename collision/u)
  }
})

test("Windows npm invocation runs the JavaScript CLI without cmd.exe", () => {
  const unsafeUrl = "https://127.0.0.1:4174/login&whoami"
  const invocation = buildSafeCommandInvocation(
    "npm",
    ["exec", "--yes", "--", "lighthouse", unsafeUrl],
    {
      platform: "win32",
      execPath: "C:\\node\\node.exe",
      npmCliPath: "C:\\node\\node_modules\\npm\\bin\\npm-cli.js",
    }
  )

  assert.equal(invocation.executable, "C:\\node\\node.exe")
  assert.equal(invocation.args[0], "C:\\node\\node_modules\\npm\\bin\\npm-cli.js")
  assert.deepEqual(invocation.args.slice(1), ["exec", "--yes", "--", "lighthouse", unsafeUrl])
  assert.notEqual(invocation.executable.toLowerCase(), "cmd.exe")
})

test("Windows refuses an unresolved npm CLI instead of falling back to cmd.exe", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npm", ["run", "build"], {
        platform: "win32",
        execPath: "C:\\node\\node.exe",
        env: {},
        exists: () => false,
      }),
    /refusing to invoke cmd\.exe/u
  )
})

test("Windows rejects accidental npx use so shell injection cannot regress", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npx", ["lighthouse", "https://example.test/a&b"], {
        platform: "win32",
        npmCliPath: "C:\\node\\npm-cli.js",
      }),
    /npx is not supported on Windows/u
  )
})

test("Windows rejects a cmd shim supplied as the npm CLI path", () => {
  assert.throws(
    () =>
      buildSafeCommandInvocation("npm", ["run", "build"], {
        platform: "win32",
        execPath: "C:\\node\\node.exe",
        npmCliPath: "C:\\node\\npm.cmd",
      }),
    /refusing to invoke cmd\.exe/u
  )
})

test("npm CLI resolution prefers npm's package-script entrypoint", () => {
  const configured = "/tooling/npm-cli.js"
  const resolved = resolveNpmCliPath({
    env: { npm_execpath: configured },
    execPath: "/node/node.exe",
    exists: (candidate) => candidate === configured,
  })
  assert.equal(resolved, configured)
})

test("runCommand captures output, attaches close metadata, and rejects spawn errors", async () => {
  const inheritedStdio = await runCommand(
    process.execPath,
    ["-e", "process.exitCode = 0"],
    "inherited stdio"
  )
  assert.deepEqual(inheritedStdio, { stdout: "", stderr: "" })

  const success = await runCommand(
    process.execPath,
    ["-e", "process.stdout.write('child stdout'); process.stderr.write('child stderr')"],
    "child success",
    { silent: true }
  )
  assert.deepEqual(success, { stdout: "child stdout", stderr: "child stderr" })

  await assert.rejects(
    () =>
      runCommand(
        process.execPath,
        ["-e", "process.stderr.write('planned stderr'); process.exitCode = 7"],
        "child failure",
        { silent: true }
      ),
    (error) => {
      assert.equal(error.command, process.execPath)
      assert.equal(error.exitCode, 7)
      assert.equal(error.description, "child failure")
      assert.match(error.stderr, /planned stderr/u)
      return true
    }
  )

  const missingExecutable = path.join(tmpdir(), `aud486-missing-${process.pid}.exe`)
  await assert.rejects(
    () => runCommand(missingExecutable, [], "missing child", { silent: true }),
    (error) => error.code === "ENOENT"
  )
})

test("runLighthouse uses the installed CLI identified by the lockfile", async () => {
  const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
  const lockfile = JSON.parse(await readFile(path.join(frontendRoot, "package-lock.json"), "utf8"))
  const lighthouse = lockfile.packages["node_modules/lighthouse"]
  const cliPath = path.join(frontendRoot, "node_modules", "lighthouse", lighthouse.bin.lighthouse)
  const url = `http://127.0.0.1:4174/aud405-${process.pid}`
  const root = await mkdtemp(path.join(tmpdir(), "lhci-locked-run-test-"))
  const directory = path.join(root, "reports")
  let outputPath

  try {
    const result = await runLighthouse(
      url,
      1,
      async (command, args, description, options) => {
        outputPath = reportPath(args)
        assert.equal(path.dirname(path.dirname(outputPath)), directory)
        assert.equal(command, process.execPath)
        assert.equal(args[0], cliPath)
        assert.equal(args[1], url)
        assert.equal(description, `lighthouse ${url} run 1`)
        assert.equal(options.silent, true)
        await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
      },
      directory
    )
    assert.equal(result, outputPath)
    await assert.doesNotReject(() => parseLhr(result))
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("locked Lighthouse CLI validation rejects inconsistent package metadata", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "lhci-locked-cli-test-"))
  const packageRoot = path.join(root, "node_modules", "lighthouse")
  const bin = { lighthouse: "cli/index.js" }
  const locked = { version: "13.5.0", bin }
  const installed = { name: "lighthouse", version: "13.5.0", bin }
  const previous = process.env.LIGHTHOUSE_VERSION
  const writeMetadata = (lockEntry, packageEntry) =>
    Promise.all([
      writeFile(
        path.join(root, "package-lock.json"),
        JSON.stringify({ packages: { "node_modules/lighthouse": lockEntry } })
      ),
      writeFile(path.join(packageRoot, "package.json"), JSON.stringify(packageEntry)),
    ])
  try {
    delete process.env.LIGHTHOUSE_VERSION
    await mkdir(packageRoot, { recursive: true })
    await writeMetadata(locked, installed)
    assert.equal(await resolveLockedLighthouseCli(root), path.join(packageRoot, "cli", "index.js"))
    process.env.LIGHTHOUSE_VERSION = locked.version
    assert.equal(await resolveLockedLighthouseCli(root), path.join(packageRoot, "cli", "index.js"))
    delete process.env.LIGHTHOUSE_VERSION

    for (const [lockEntry, packageEntry] of [
      [{ bin }, installed],
      [{ version: "", bin }, installed],
      [{ version: locked.version, bin: {} }, installed],
      [locked, { ...installed, name: "other-package" }],
      [locked, { ...installed, version: "13.1.0" }],
      [locked, { ...installed, bin: {} }],
    ]) {
      await writeMetadata(lockEntry, packageEntry)
      await assert.rejects(
        () => resolveLockedLighthouseCli(root),
        /does not match frontend lockfile/u
      )
    }
  } finally {
    if (previous === undefined) delete process.env.LIGHTHOUSE_VERSION
    else process.env.LIGHTHOUSE_VERSION = previous
    await rm(root, { recursive: true, force: true })
  }
})

test("runLighthouse rejects a version override that differs from the lockfile", async () => {
  const previous = process.env.LIGHTHOUSE_VERSION
  let launched = false
  try {
    process.env.LIGHTHOUSE_VERSION = "12.8.2"
    await assert.rejects(
      () =>
        runLighthouse(`http://127.0.0.1:4174/aud405-override-${process.pid}`, 1, async () => {
          launched = true
        }),
      /LIGHTHOUSE_VERSION.*lockfile/u
    )
    assert.equal(launched, false)
  } finally {
    if (previous === undefined) delete process.env.LIGHTHOUSE_VERSION
    else process.env.LIGHTHOUSE_VERSION = previous
  }
})

test(
  "runLighthouse recovers only a complete report after the known cleanup error",
  { skip: process.platform !== "win32" },
  async () => {
    const url = `http://127.0.0.1:4174/aud486-${process.pid}`
    const runIndex = 1
    const root = await mkdtemp(path.join(tmpdir(), "lhci-recovery-run-test-"))
    const directory = path.join(root, "reports")
    const tempPath = path.win32.join(tmpdir(), "lighthouse.Abc123")
    const cleanupError = lighthouseCleanupError({
      description: `lighthouse ${url} run ${runIndex}`,
      tempPath,
    })
    let report = completeLhr()
    let outputPath
    const baseRunner = async (command, args, description, options) => {
      outputPath = reportPath(args)
      assert.equal(command, process.execPath)
      assert.equal(description, `lighthouse ${url} run ${runIndex}`)
      assert.equal(options.silent, true)
      assert.equal(args[1], url)
      await writeFile(outputPath, JSON.stringify(report), "utf8")
      throw cleanupError
    }

    try {
      const recovered = await runLighthouse(url, runIndex, baseRunner, directory)
      assert.equal(recovered, outputPath)
      await assert.doesNotReject(() => parseLhr(recovered))
      assert.equal(
        await runLighthouse(
          url,
          runIndex,
          async (_command, args) => {
            outputPath = reportPath(args)
            await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
          },
          directory
        ),
        outputPath
      )

      const partialLhr = completeLhr()
      delete partialLhr.audits["total-blocking-time"]
      partialLhr.audits["network-requests"] = {
        details: { items: ["partial Lighthouse data".repeat(80)] },
      }
      assert.ok(Buffer.byteLength(JSON.stringify(partialLhr)) > 1000)
      report = partialLhr
      await assert.rejects(
        () => runLighthouse(url, runIndex, baseRunner, directory),
        /invalid or incomplete LHR/u
      )

      const unrelatedError = new Error("Lighthouse failed for an unrelated reason")
      await assert.rejects(
        () =>
          runLighthouse(
            url,
            runIndex,
            async (_command, args) => {
              outputPath = reportPath(args)
              await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
              throw unrelatedError
            },
            directory
          ),
        (error) => error === unrelatedError
      )
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  }
)

test(
  "runLighthouse rejects a cleanup failure when only a stale report exists",
  { skip: process.platform !== "win32" },
  async () => {
    const url = `http://127.0.0.1:4174/aud486-stale-${process.pid}`
    const root = await mkdtemp(path.join(tmpdir(), "lhci-stale-run-test-"))
    const directory = path.join(root, "reports")
    const stalePath = path.join(directory, `lhr_aud486-stale-${process.pid}_run1.json`)
    const cleanupError = lighthouseCleanupError({
      description: `lighthouse ${url} run 1`,
      tempPath: path.win32.join(tmpdir(), "lighthouse.Abc123"),
    })

    await mkdir(directory, { recursive: true })
    try {
      const staleContents = JSON.stringify(completeLhr())
      await writeFile(stalePath, staleContents, "utf8")
      await assert.rejects(
        () =>
          runLighthouse(
            url,
            1,
            async () => {
              throw cleanupError
            },
            directory
          ),
        (error) => error instanceof AggregateError && error.errors[0] === cleanupError
      )
      assert.equal(await readFile(stalePath, "utf8"), staleContents)
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  }
)

test(
  "real child status permits only a fresh complete report after the cleanup failure",
  { skip: process.platform !== "win32" },
  async () => {
    const url = `http://127.0.0.1:4174/aud486-child-${process.pid}`
    const root = await mkdtemp(path.join(tmpdir(), "lhci-child-run-test-"))
    const directory = path.join(root, "reports")
    const cleanupError = lighthouseCleanupError({
      description: `lighthouse ${url} run 1`,
      tempPath: path.win32.join(tmpdir(), "lighthouse.Abc123"),
    })
    const childScript = [
      'const fs = require("node:fs")',
      "const [output, contents, stderr, code] = process.argv.slice(1)",
      "if (contents) fs.writeFileSync(output, contents)",
      "process.stderr.write(stderr)",
      "process.exitCode = Number(code)",
    ].join("; ")
    let outputPath
    const runner = (contents, exitCode) => (command, args, description, options) => {
      outputPath = reportPath(args)
      return runCommand(
        command,
        ["-e", childScript, outputPath, contents, cleanupError.stderr, String(exitCode)],
        description,
        options
      )
    }

    try {
      const firstReport = await runLighthouse(
        url,
        1,
        runner(JSON.stringify(completeLhr()), 1),
        directory
      )
      assert.equal(firstReport, outputPath)
      await assert.rejects(
        () => runLighthouse(url, 1, runner("", 1), directory),
        (error) => error instanceof AggregateError && error.errors[0].exitCode === 1
      )
      await assert.doesNotReject(() => parseLhr(firstReport))
      await assert.rejects(
        () => runLighthouse(url, 1, runner(JSON.stringify(completeLhr()), 2), directory),
        (error) => error.exitCode === 2 && !(error instanceof AggregateError)
      )
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  }
)

async function exerciseOverlappingAttempts(startSecondAfterWrite, sameUrl = false) {
  const route = `aud486-race-${process.pid}-${startSecondAfterWrite ? "late" : "early"}`
  const firstUrl = `http://127.0.0.1:4174/${route}`
  const secondUrl = sameUrl ? firstUrl : `http://127.0.0.1:4175/${route}`
  const root = await mkdtemp(path.join(tmpdir(), "lhci-overlapping-run-test-"))
  const reportsDir = path.join(root, "reports")
  const firstEntered = Promise.withResolvers()
  const secondEntered = Promise.withResolvers()
  const firstMayWrite = Promise.withResolvers()
  const firstHasWritten = Promise.withResolvers()
  const firstMayFinish = Promise.withResolvers()
  const secondMayFinish = Promise.withResolvers()
  const createdPaths = new Set()
  const outcome = (promise) => promise.then((value) => ({ value }), (error) => ({ error }))
  const runner = (url, first) => async (_command, args) => {
    const output = reportPath(args)
    createdPaths.add(output)
    if (first) {
      firstEntered.resolve()
      await firstMayWrite.promise
      await writeFile(output, JSON.stringify(completeLhr()), "utf8")
      firstHasWritten.resolve()
      await firstMayFinish.promise
    } else {
      secondEntered.resolve()
      await secondMayFinish.promise
    }
    throw lighthouseCleanupError({
      description: `lighthouse ${url} run 1`,
      tempPath: path.win32.join(tmpdir(), "lighthouse.Abc123"),
    })
  }

  const first = outcome(runLighthouse(firstUrl, 1, runner(firstUrl, true), reportsDir))
  let second
  try {
    await firstEntered.promise
    if (startSecondAfterWrite) {
      firstMayWrite.resolve()
      await firstHasWritten.promise
    }
    second = outcome(runLighthouse(secondUrl, 1, runner(secondUrl, false), reportsDir))
    await secondEntered.promise
    if (!startSecondAfterWrite) {
      firstMayWrite.resolve()
      await firstHasWritten.promise
    }
    secondMayFinish.resolve()
    const secondResult = await second
    firstMayFinish.resolve()
    const firstResult = await first

    assert.ok(secondResult.error instanceof AggregateError, "second attempt must reject")
    assert.equal(typeof firstResult.value, "string", "first attempt must retain its report")
    assert.equal(createdPaths.size, 2, "attempts must use different report paths")
  } finally {
    firstMayWrite.resolve()
    firstMayFinish.resolve()
    secondMayFinish.resolve()
    await Promise.allSettled([first, second])
    await rm(root, { recursive: true, force: true })
  }
}

test(
  "overlapping Lighthouse attempts cannot recover each other's reports",
  { skip: process.platform !== "win32", timeout: 5000 },
  () => exerciseOverlappingAttempts(false)
)

test(
  "overlapping Lighthouse attempts cannot delete another attempt's report",
  { skip: process.platform !== "win32", timeout: 5000 },
  () => exerciseOverlappingAttempts(true)
)

test(
  "overlapping Lighthouse attempts with the same URL remain isolated",
  { skip: process.platform !== "win32", timeout: 5000 },
  () => exerciseOverlappingAttempts(false, true)
)

test("clearing legacy reports preserves independent attempt directories", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "lhci-clear-test-"))
  const directory = path.join(root, "reports")
  const attemptDir = path.join(directory, "attempt-other")
  const attemptReport = path.join(attemptDir, "lhr_login_run1.json")
  const legacyReport = path.join(directory, "lhr_login_run1.json")
  try {
    await clearLhrDir(directory)
    await mkdir(attemptDir)
    await writeFile(attemptReport, "other attempt", "utf8")
    await writeFile(legacyReport, "legacy report", "utf8")
    await clearLhrDir(directory)
    await assert.rejects(() => readFile(legacyReport), (error) => error.code === "ENOENT")
    assert.equal(await readFile(attemptReport, "utf8"), "other attempt")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("Lighthouse fallback rejects a partial URL/run result set", () => {
  const measured = { perf: 1, a11y: 1, bp: 1, seo: 1, cls: 0, lcp: 100, tbt: 0 }
  const complete = new Map([
    ["/login", [measured, measured]],
    ["/events", [measured, measured]],
  ])
  assert.doesNotThrow(() => assertCompleteLighthouseResults(complete, 2))

  const partial = new Map([
    ["/login", [measured, null]],
    ["/events", [measured]],
  ])
  assert.throws(
    () => assertCompleteLighthouseResults(partial, 2),
    /did not produce a valid LHR for every URL\/run/u
  )
})

test("empty metrics cannot satisfy the complete Lighthouse result contract", () => {
  const empty = { perf: null, a11y: null, bp: null, seo: null, cls: null, lcp: null, tbt: null }
  assert.throws(
    () => assertCompleteLighthouseResults(new Map([["/login", [empty]]]), 1),
    /did not produce a valid LHR for every URL\/run/u
  )
})

test("only a known Windows chrome-launcher cleanup failure recovers a complete LHR", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "lhci-cleanup-recovery-test-"))
  const outputPath = path.join(root, "lhr_login_run1.json")
  const tempDir = "C:\\Temp\\lhci"
  try {
    await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
    const knownFailure = lighthouseCleanupError()
    assert.equal(
      await recoverLhrAfterKnownCleanupFailure(knownFailure, outputPath, {
        platform: "win32",
        tempDir,
      }),
      outputPath
    )

    const extendedTempDir = "\\\\?\\C:\\Temp\\lhci"
    const extendedFailure = lighthouseCleanupError({
      tempPath: `${extendedTempDir}\\lighthouse.Abc123`,
    })
    assert.equal(
      await recoverLhrAfterKnownCleanupFailure(extendedFailure, outputPath, {
        platform: "win32",
        tempDir: extendedTempDir,
      }),
      outputPath
    )

    if (process.platform === "win32") {
      const defaultTempFailure = lighthouseCleanupError({
        tempPath: path.win32.join(tmpdir(), "lighthouse.Abc123"),
      })
      assert.equal(
        await recoverLhrAfterKnownCleanupFailure(defaultTempFailure, outputPath),
        outputPath
      )
    }

    const relativeTempPath = lighthouseCleanupError({ tempPath: "lighthouse.Abc123" })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(relativeTempPath, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === relativeTempPath
    )

    const multipleErrorHeaders = lighthouseCleanupError({
      stderr: [
        `Error: EPERM: operation not permitted, rmSync '${path.win32.join(tempDir, "lighthouse.Abc123")}'`,
        "TypeError: secondary failure",
        "    at Launcher.destroyTmp (C:\\fixture\\node_modules\\chrome-launcher\\dist\\chrome-launcher.js:123:5)",
      ].join("\n"),
    })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(multipleErrorHeaders, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === multipleErrorHeaders
    )

    const missingCleanupStack = lighthouseCleanupError({
      stderr: [
        `Error: EPERM: operation not permitted, rmSync '${path.win32.join(tempDir, "lighthouse.Abc123")}'`,
        "    at Object.rmSync (node:fs:1234:5)",
      ].join("\n"),
    })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(missingCleanupStack, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === missingCleanupStack
    )
    const plausiblePartialLhr = completeLhr()
    delete plausiblePartialLhr.audits["total-blocking-time"]
    plausiblePartialLhr.audits["network-requests"] = {
      details: {
        items: ["partial report that was large enough for the old size-only recovery".repeat(20)],
      },
    }
    const partialContents = JSON.stringify(plausiblePartialLhr)
    assert.ok(Buffer.byteLength(partialContents) > 1000)
    await writeFile(outputPath, partialContents, "utf8")
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(knownFailure, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => {
        assert.ok(error instanceof AggregateError)
        assert.equal(error.errors.length, 2)
        assert.equal(error.errors[0], knownFailure)
        assert.equal(error.errors[1], error.cause)
        assert.match(
          error.message,
          /invalid or incomplete LHR: (?:Error: )?Invalid Lighthouse result/u
        )
        return true
      }
    )

    await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
    const unrelatedFailure = lighthouseCleanupError({
      stderr: "Error: connect ECONNREFUSED 127.0.0.1:4174",
    })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(unrelatedFailure, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === unrelatedFailure
    )

    const wrongExitCode = lighthouseCleanupError({ exitCode: 2 })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(wrongExitCode, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === wrongExitCode
    )

    const wrongCommand = lighthouseCleanupError()
    wrongCommand.command = "npm"
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(wrongCommand, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === wrongCommand
    )

    const wrongTempPath = lighthouseCleanupError({
      tempPath: "C:\\Temp\\other\\lighthouse.Abc123",
    })
    await assert.rejects(
      () =>
        recoverLhrAfterKnownCleanupFailure(wrongTempPath, outputPath, {
          platform: "win32",
          tempDir,
        }),
      (error) => error === wrongTempPath
    )
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("parseLhr rejects malformed or structurally incomplete reports", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "lhci-fallback-test-"))
  try {
    const malformed = path.join(root, "malformed.json")
    await writeFile(malformed, JSON.stringify({ categories: {}, audits: {} }), "utf8")
    await assert.rejects(() => parseLhr(malformed), /Invalid Lighthouse result/u)

    const valid = path.join(root, "valid.json")
    await writeFile(valid, JSON.stringify(completeLhr()), "utf8")
    await assert.doesNotReject(() => parseLhr(valid))

    const incomplete = path.join(root, "incomplete.json")
    const incompleteLhr = completeLhr()
    delete incompleteLhr.audits["total-blocking-time"]
    await writeFile(incomplete, JSON.stringify(incompleteLhr), "utf8")
    await assert.rejects(() => parseLhr(incomplete), /Invalid Lighthouse result/u)

    const explicitNullRuntimeError = completeLhr()
    explicitNullRuntimeError.runtimeError = null
    await writeFile(valid, JSON.stringify(explicitNullRuntimeError), "utf8")
    await assert.doesNotReject(() => parseLhr(valid))

    const runtimeError = completeLhr()
    runtimeError.runtimeError = { code: "NO_FCP" }
    await writeFile(valid, JSON.stringify(runtimeError), "utf8")
    await assert.rejects(() => parseLhr(valid), /Invalid Lighthouse result/u)

    const arrayCategory = completeLhr()
    arrayCategory.categories.performance = []
    await writeFile(valid, JSON.stringify(arrayCategory), "utf8")
    await assert.rejects(() => parseLhr(valid), /Invalid Lighthouse result/u)
    const invalidScore = path.join(root, "invalid-score.json")
    const invalidScoreLhr = completeLhr()
    invalidScoreLhr.categories.performance.score = 1.1
    await writeFile(invalidScore, JSON.stringify(invalidScoreLhr), "utf8")
    await assert.rejects(() => parseLhr(invalidScore), /Invalid Lighthouse result/u)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
