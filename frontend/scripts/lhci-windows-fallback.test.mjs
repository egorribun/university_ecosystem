import assert from "node:assert/strict"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

import {
  assertCompleteLighthouseResults,
  buildSafeCommandInvocation,
  DEFAULT_PATHS,
  normalizePath,
  parseLhr,
  recoverLhrAfterKnownCleanupFailure,
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
  error.command = "npm"
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

test(
  "runLighthouse recovers only a complete report after the known cleanup error",
  { skip: process.platform !== "win32" },
  async () => {
    const url = `http://127.0.0.1:4174/aud486-${process.pid}`
    const runIndex = 1
    const outputPath = path.join(
      path.dirname(fileURLToPath(import.meta.url)),
      "..",
      ".lighthouseci",
      `lhr_aud486-${process.pid}_run${runIndex}.json`
    )
    const outputDir = path.dirname(outputPath)
    const tempPath = path.win32.join(tmpdir(), "lighthouse.Abc123")
    const cleanupError = lighthouseCleanupError({
      description: `lighthouse ${url} run ${runIndex}`,
      tempPath,
    })
    const baseRunner = async (command, args, description, options) => {
      assert.equal(command, "npm")
      assert.equal(description, `lighthouse ${url} run ${runIndex}`)
      assert.equal(options.silent, true)
      assert.equal(args[args.indexOf("lighthouse") + 1], url)
      throw cleanupError
    }

    await mkdir(outputDir, { recursive: true })
    try {
      await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
      assert.equal(await runLighthouse(url, runIndex, baseRunner), outputPath)
      assert.equal(await runLighthouse(url, runIndex, async () => {}), outputPath)

      const partialLhr = completeLhr()
      delete partialLhr.audits["total-blocking-time"]
      partialLhr.audits["network-requests"] = {
        details: { items: ["partial Lighthouse data".repeat(80)] },
      }
      assert.ok(Buffer.byteLength(JSON.stringify(partialLhr)) > 1000)
      await writeFile(outputPath, JSON.stringify(partialLhr), "utf8")
      await assert.rejects(
        () => runLighthouse(url, runIndex, baseRunner),
        /invalid or incomplete LHR/u
      )

      await writeFile(outputPath, JSON.stringify(completeLhr()), "utf8")
      const unrelatedError = new Error("npm exec failed for an unrelated reason")
      await assert.rejects(
        () =>
          runLighthouse(url, runIndex, async () => {
            throw unrelatedError
          }),
        (error) => error === unrelatedError
      )
    } finally {
      await rm(outputPath, { force: true })
    }
  }
)
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
