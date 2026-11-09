import assert from "node:assert/strict"
import { EventEmitter, once } from "node:events"
import { execFile, spawn } from "node:child_process"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { promisify } from "node:util"
import { fileURLToPath } from "node:url"
import { processIsAlive } from "./run-stryker-test-helpers.mjs"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
const processTreeFixtureSetupTimeoutMs = 5_000
const execFileAsync = promisify(execFile)

async function waitForProcessTreeFixtureMessage(child) {
  const listenerController = new AbortController()
  let setupTimer
  const setupTimeout = new Promise((_, reject) => {
    setupTimer = setTimeout(
      () => reject(new Error("Process-tree fixture did not report readiness within 5000ms")),
      processTreeFixtureSetupTimeoutMs
    )
  })
  try {
    return await Promise.race([
      once(child, "message", { signal: listenerController.signal }).then(([message]) => message),
      once(child, "close", { signal: listenerController.signal }).then(([code, signal]) => {
        throw new Error(
          `Process-tree fixture closed before readiness (code=${String(code)}, signal=${String(signal)})`
        )
      }),
      setupTimeout,
    ])
  } finally {
    clearTimeout(setupTimer)
    listenerController.abort()
  }
}

async function spawnProcessTreeFixture({
  createProcessTreeOwnership,
  processTreeSpawnOptions,
  registerFixture,
}) {
  const fixtureScript = String.raw`
    const { spawn } = require("node:child_process");
    const descendant = spawn(
      process.execPath,
      ["-e", "setInterval(() => {}, 1000)", "university-ecosystem-stryker-descendant"],
      { stdio: "ignore", windowsHide: true }
    );
    const abortFixture = () => {
      try {
        descendant.kill("SIGKILL");
      } finally {
        process.exit(1);
      }
    };
    process.once("disconnect", abortFixture);
    process.send({ descendantPid: descendant.pid }, (error) => {
      if (error) abortFixture();
    });
    setInterval(() => {}, 1000);
  `
  const child = spawn(
    process.execPath,
    ["-e", fixtureScript, "university-ecosystem-stryker-parent"],
    {
      ...processTreeSpawnOptions(process.platform),
      stdio: ["ignore", "ignore", "ignore", "ipc"],
    }
  )
  const fixture = { child, descendantPid: undefined, ownership: undefined }
  registerFixture(fixture)
  fixture.ownership = createProcessTreeOwnership(child, { platform: process.platform })
  const message = await waitForProcessTreeFixtureMessage(child)
  assert.equal(Number.isSafeInteger(message.descendantPid), true)
  assert.equal(message.descendantPid > 0, true)
  fixture.descendantPid = message.descendantPid
  return fixture
}

test("evidence identity makes dirty worktrees explicit and detects TOCTOU drift", async () => {
  const { buildEvidenceIdentity, assertEvidenceUnchanged } = await import(runnerUrl)
  const clean = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: { "frontend/src/a.ts": "1".repeat(64) },
  })
  const dirty = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [" M frontend/src/a.ts"],
    inputHashes: { "frontend/src/a.ts": "2".repeat(64) },
  })

  assert.equal(clean.repositoryDirty, false)
  assert.equal(clean.revision, clean.headSha)
  assert.equal(dirty.repositoryDirty, true)
  assert.match(dirty.revision, /^a{40}-dirty\.[a-f0-9]{12}$/u)
  assert.doesNotThrow(() => assertEvidenceUnchanged(clean, { ...clean }))
  assert.throws(() => assertEvidenceUnchanged(clean, dirty), /changed while Stryker was running/u)
})

test("evidence identity keeps source, tested, and base commit identities distinct", async () => {
  const { buildEvidenceIdentity, assertEvidenceUnchanged } = await import(runnerUrl)
  const common = {
    headSha: "a".repeat(40),
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
    dirtyPaths: [],
    inputHashes: { "frontend/src/a.ts": "1".repeat(64) },
  }

  const identity = buildEvidenceIdentity(common)
  assert.equal(identity.headSha, common.headSha)
  assert.equal(identity.sourceHeadSha, common.sourceHeadSha)
  assert.equal(identity.baseSha, common.baseSha)
  assert.equal(identity.baseRef, common.baseRef)
  assert.notEqual(
    identity.evidenceDigest,
    buildEvidenceIdentity({ ...common, sourceHeadSha: "d".repeat(40) }).evidenceDigest
  )
  assert.notEqual(
    identity.evidenceDigest,
    buildEvidenceIdentity({ ...common, baseSha: "e".repeat(40) }).evidenceDigest
  )
  assert.throws(
    () =>
      assertEvidenceUnchanged(identity, {
        ...identity,
        sourceHeadSha: "d".repeat(40),
      }),
    /changed while Stryker was running/u
  )
})

test("workflow provenance maps PR source and base identities without trusting the merge SHA", async () => {
  const { buildWorkflowEvidenceIdentity } = await import(runnerUrl)
  const testedSha = "a".repeat(40)
  const sourceSha = "b".repeat(40)
  const baseSha = "c".repeat(40)

  assert.deepEqual(
    buildWorkflowEvidenceIdentity(testedSha, {
      STRYKER_SOURCE_HEAD_SHA: sourceSha,
      STRYKER_BASE_SHA: baseSha,
      STRYKER_BASE_REF: "main",
    }),
    {
      sourceHeadSha: sourceSha,
      baseSha,
      baseRef: "main",
    }
  )
  assert.deepEqual(buildWorkflowEvidenceIdentity(testedSha, {}), {
    sourceHeadSha: testedSha,
    baseSha: testedSha,
    baseRef: null,
  })
  assert.deepEqual(
    buildWorkflowEvidenceIdentity(testedSha, {
      GITHUB_BASE_REF: "",
      GITHUB_REF_NAME: "release",
    }),
    {
      sourceHeadSha: testedSha,
      baseSha: testedSha,
      baseRef: "release",
    }
  )
  assert.throws(
    () =>
      buildWorkflowEvidenceIdentity(testedSha, {
        STRYKER_SOURCE_HEAD_SHA: "not-a-sha",
      }),
    /source head/u
  )
})

test("focused source snapshots bind the complete frontend evidence graph", async () => {
  const { captureEvidence, selectEvidenceFiles } = await import(runnerUrl)
  const selectedSource = "src/components/ui/Button.tsx"
  const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")
  const { stdout: deletedFilesOutput } = await execFileAsync(
    "git",
    ["ls-files", "--deleted", "--", "frontend", "quality/coverage-source-policy.json"],
    { cwd: repositoryRoot }
  )
  const deletedFiles = deletedFilesOutput.split(/\r?\n/u).filter(Boolean)

  assert.deepEqual(
    selectEvidenceFiles(
      "frontend/src/kept.ts\nfrontend/src/deleted.ts\nfrontend/src/added.ts\n",
      "frontend/src/deleted.ts\n"
    ),
    ["frontend/src/added.ts", "frontend/src/kept.ts"]
  )
  const snapshot = await captureEvidence([selectedSource])

  assert.deepEqual([...snapshot.sourceByFile.keys()], [selectedSource])
  for (const file of deletedFiles) {
    assert.equal(
      Object.hasOwn(snapshot.identity.inputHashes, file),
      false,
      `Deleted tracked file must remain represented by dirty status, not a content hash: ${file}`
    )
    assert.ok(
      snapshot.identity.dirtyPaths.some((status) => status.endsWith(file)),
      `Deleted tracked file must remain represented in dirty-path evidence: ${file}`
    )
  }
  assert.equal(typeof snapshot.identity.inputHashes[`frontend/${selectedSource}`], "string")
  assert.equal(
    typeof snapshot.identity.inputHashes["frontend/src/components/ui/Select.tsx"],
    "string"
  )
  assert.equal(typeof snapshot.identity.inputHashes["frontend/scripts/run-stryker.mjs"], "string")
  assert.equal(
    typeof snapshot.identity.inputHashes["quality/coverage-source-policy.json"],
    "string"
  )
})

test("canonical cleanup removes only stale mutation evidence", async (t) => {
  const { cleanupCanonicalArtifacts } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-cleanup-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  await Promise.all([
    mkdir(path.join(root, "runs", "old"), { recursive: true }),
    mkdir(path.join(root, "historical-costs"), { recursive: true }),
  ])
  await Promise.all([
    writeFile(path.join(root, "mutation.json"), "stale"),
    writeFile(path.join(root, "mutation.html"), "stale"),
    writeFile(path.join(root, "inventory.json"), "stale"),
    writeFile(path.join(root, "VALIDATED.json"), "stale"),
    writeFile(path.join(root, "runs", "old", "report.json"), "stale"),
    writeFile(path.join(root, "historical-costs", "HISTORICAL_COSTS.json"), "stale"),
    writeFile(path.join(root, "keep.txt"), "keep"),
  ])

  await cleanupCanonicalArtifacts(root)
  assert.equal(await readFile(path.join(root, "keep.txt"), "utf8"), "keep")
  await assert.rejects(() => readFile(path.join(root, "mutation.json")), /ENOENT/u)
  await assert.rejects(() => readFile(path.join(root, "runs", "old", "report.json")), /ENOENT/u)
  await assert.rejects(
    () => readFile(path.join(root, "historical-costs", "HISTORICAL_COSTS.json")),
    /ENOENT/u
  )
})

test("fresh run directories are recreated after cleanup and remain exclusive", async (t) => {
  const { cleanupCanonicalArtifacts, createExclusiveRunDirectory } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-run-directory-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  await mkdir(path.join(root, "runs", "stale"), { recursive: true })

  await cleanupCanonicalArtifacts(root)

  const freshRunRoot = path.join(root, "runs", "fresh-run")
  await createExclusiveRunDirectory(freshRunRoot)
  await writeFile(path.join(freshRunRoot, "evidence.json"), "fresh")
  assert.equal(await readFile(path.join(freshRunRoot, "evidence.json"), "utf8"), "fresh")
  await assert.rejects(
    () => createExclusiveRunDirectory(freshRunRoot),
    /EEXIST/u,
    "A colliding run ID must fail closed instead of reusing existing evidence"
  )

  const concurrentRunRoot = path.join(root, "runs", "concurrent-run")
  const attempts = await Promise.allSettled([
    createExclusiveRunDirectory(concurrentRunRoot),
    createExclusiveRunDirectory(concurrentRunRoot),
  ])
  assert.equal(attempts.filter(({ status }) => status === "fulfilled").length, 1)
  const rejected = attempts.find(({ status }) => status === "rejected")
  assert.equal(rejected?.status, "rejected")
  assert.match(String(rejected.reason), /EEXIST/u)
})

test("process-tree ownership is explicit and POSIX children start in a dedicated group", async () => {
  const { createProcessTreeOwnership, processTreeSpawnOptions } = await import(runnerUrl)
  const child = { pid: 4321 }

  assert.deepEqual(processTreeSpawnOptions("linux"), {
    detached: true,
    windowsHide: true,
  })
  assert.deepEqual(processTreeSpawnOptions("win32"), {
    detached: false,
    windowsHide: true,
  })
  assert.deepEqual(createProcessTreeOwnership(child, { platform: "linux" }), {
    kind: "posix-process-group",
    rootPid: 4321,
    groupId: 4321,
  })
  assert.deepEqual(createProcessTreeOwnership(child, { platform: "win32" }), {
    kind: "windows-process-tree",
    rootPid: 4321,
  })
  assert.throws(
    () => createProcessTreeOwnership({ pid: 0 }, { platform: "linux" }),
    /positive safe integer/u
  )
})

test("process-tree termination rejects mismatched PID and PGID ownership", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const child = { pid: 2222, exitCode: null, signalCode: null }

  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, {
        kind: "windows-process-tree",
        rootPid: 3333,
      }),
    /does not match the child PID/u
  )
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, {
        kind: "posix-process-group",
        rootPid: 2222,
        groupId: 3333,
      }),
    /must be led by the owned child/u
  )
})

test("Windows tree-kill failure stays authoritative after a successful direct-child fallback", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const treeFailure = Object.assign(new Error("taskkill access denied"), { code: "EACCES" })
  const calls = []
  const child = {
    pid: 5432,
    exitCode: null,
    signalCode: null,
    kill(signal) {
      calls.push(["direct", signal])
      return true
    },
  }
  const ownership = { kind: "windows-process-tree", rootPid: 5432 }

  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, ownership, {
        execFileCommand: async (command, args, options) => {
          calls.push([command, args, options])
          throw treeFailure
        },
      }),
    (error) => error === treeFailure
  )
  assert.deepEqual(calls, [
    ["taskkill", ["/pid", "5432", "/t", "/f"], { timeout: 10_000, windowsHide: true }],
    ["direct", "SIGKILL"],
  ])
})

test("Windows tree-kill retains direct fallback errors without replacing the tree failure", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const treeFailure = new Error("taskkill timed out")
  const directFailure = new Error("direct kill failed")
  const child = {
    pid: 6543,
    exitCode: null,
    signalCode: null,
    kill() {
      throw directFailure
    },
  }

  await assert.rejects(
    () =>
      terminateOwnedProcessTree(
        child,
        { kind: "windows-process-tree", rootPid: 6543 },
        {
          execFileCommand: async () => {
            throw treeFailure
          },
        }
      ),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.equal(error.cause, treeFailure)
      assert.deepEqual(error.errors, [treeFailure, directFailure])
      return true
    }
  )

  let postExitActions = 0
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(
        {
          pid: 6543,
          exitCode: 0,
          signalCode: null,
          kill() {
            postExitActions += 1
            return true
          },
        },
        { kind: "windows-process-tree", rootPid: 6543 },
        {
          execFileCommand: async () => {
            postExitActions += 1
          },
        }
      ),
    /root exited before tree termination could be proven/u
  )
  assert.equal(postExitActions, 0)

  const falseChild = {
    pid: 6543,
    exitCode: null,
    signalCode: null,
    kill: () => false,
  }
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(
        falseChild,
        { kind: "windows-process-tree", rootPid: 6543 },
        {
          execFileCommand: async () => {
            throw treeFailure
          },
        }
      ),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.equal(error.cause, treeFailure)
      assert.equal(error.errors[0], treeFailure)
      assert.match(error.errors[1].message, /direct child kill returned false/u)
      return true
    }
  )
})

test("POSIX termination only probes the owned group after its leader exits", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const calls = []
  let probes = 0
  const child = {
    pid: 7654,
    exitCode: 0,
    signalCode: null,
    kill() {
      assert.fail("a direct-child kill cannot prove POSIX process-group quiescence")
    },
  }

  const result = await terminateOwnedProcessTree(
    child,
    { kind: "posix-process-group", rootPid: 7654, groupId: 7654 },
    {
      signalProcess(pid, signal) {
        calls.push([pid, signal])
        if (signal === 0) {
          probes += 1
          if (probes === 2) throw Object.assign(new Error("group absent"), { code: "ESRCH" })
        }
        return true
      },
      delay: async (milliseconds) => calls.push(["delay", milliseconds]),
    }
  )

  assert.equal(result, true)
  assert.deepEqual(calls, [
    [-7654, 0],
    ["delay", 25],
    [-7654, 0],
  ])
})

test("POSIX group kill and liveness uncertainty fail closed", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const child = {
    pid: 8765,
    exitCode: null,
    signalCode: null,
    kill() {
      return true
    },
  }
  const ownership = { kind: "posix-process-group", rootPid: 8765, groupId: 8765 }
  const permissionFailure = Object.assign(new Error("operation not permitted"), { code: "EPERM" })

  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, ownership, {
        signalProcess() {
          throw permissionFailure
        },
      }),
    (error) => error === permissionFailure
  )

  let signals = 0
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, ownership, {
        signalProcess() {
          signals += 1
          if (signals === 1) return true
          throw permissionFailure
        },
      }),
    (error) => error === permissionFailure
  )

  let nowCalls = 0
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(child, ownership, {
        signalProcess: () => true,
        now: () => {
          nowCalls += 1
          return nowCalls === 1 ? 1_000 : 1_011
        },
        groupVerificationTimeoutMs: 10,
        delay: async () => assert.fail("an exhausted liveness bound must not sleep again"),
      }),
    /process group 8765 remained live after 10ms/u
  )
})

test(
  "real owned process trees terminate descendants before timeout or signal completion",
  { timeout: 20_000 },
  async (t) => {
    const {
      createProcessTreeOwnership,
      processTreeSpawnOptions,
      terminateOwnedProcessTree,
      waitForChildClose,
    } = await import(runnerUrl)
    const fixtures = []
    t.after(async () => {
      for (const fixture of fixtures) {
        if (processIsAlive(fixture.descendantPid)) {
          try {
            process.kill(fixture.descendantPid, "SIGKILL")
          } catch (error) {
            if (error?.code !== "ESRCH") throw error
          }
        }
        if (processIsAlive(fixture.child.pid)) {
          if (fixture.ownership) {
            try {
              await terminateOwnedProcessTree(fixture.child, fixture.ownership)
            } catch {
              fixture.child.kill("SIGKILL")
            }
          } else {
            fixture.child.kill("SIGKILL")
          }
        }
      }
    })

    for (const mode of ["signal", "timeout"]) {
      const fixture = await spawnProcessTreeFixture({
        createProcessTreeOwnership,
        processTreeSpawnOptions,
        registerFixture: (spawnedFixture) => fixtures.push(spawnedFixture),
      })
      assert.equal(processIsAlive(fixture.descendantPid), true)
      const controller = new AbortController()
      let fireTimeout
      const timeoutToken = Symbol("timeout")
      const result = waitForChildClose(fixture.child, {
        description: `real ${mode} tree`,
        timeoutMs: 60_000,
        abortSignal: controller.signal,
        processTreeOwnership: fixture.ownership,
        // The production runner never creates legacy PID ownership on
        // Windows.  This explicit test seam keeps the real descendant
        // lifecycle check meaningful on hosts without a prebuilt Job Object
        // helper, while proving taskkill's result by observing the fixture's
        // descendant rather than treating the command exit as proof.
        terminate:
          process.platform === "win32"
            ? async (child) => {
                await execFileAsync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
                  windowsHide: true,
                })
                const startedAt = Date.now()
                while (processIsAlive(fixture.descendantPid)) {
                  if (Date.now() - startedAt >= 5_000) return false
                  await new Promise((resolve) => setTimeout(resolve, 25))
                }
                return true
              }
            : undefined,
        scheduleTimeout(callback, milliseconds) {
          if (fireTimeout === undefined) {
            fireTimeout = callback
            return timeoutToken
          }
          return setTimeout(callback, milliseconds)
        },
        cancelTimeout(timer) {
          if (timer !== timeoutToken) clearTimeout(timer)
        },
      })

      if (mode === "signal") {
        controller.abort(
          Object.assign(new Error("Stryker execution interrupted by SIGTERM"), {
            code: "STRYKER_INTERRUPTED",
            signalName: "SIGTERM",
          })
        )
      } else {
        fireTimeout()
      }

      await assert.rejects(result, (error) => {
        assert.equal(error.processQuiesced, true)
        assert.match(error.message, mode === "signal" ? /SIGTERM/u : /exceeded 60000ms/u)
        return true
      })
      assert.equal(processIsAlive(fixture.descendantPid), false)
      assert.equal(processIsAlive(fixture.child.pid), false)
    }
  }
)

test("child execution settles only after close and awaits timeout termination", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.exitCode = null
  child.signalCode = null
  let timeoutCallback
  let cancelledTimer
  let finishTermination
  const termination = new Promise((resolve) => {
    finishTermination = resolve
  })
  const result = waitForChildClose(child, {
    description: "focused shard",
    timeoutMs: 123,
    terminate: async () => termination,
    scheduleTimeout: (callback) => {
      timeoutCallback = callback
      return "timer"
    },
    cancelTimeout: (timer) => {
      cancelledTimer = timer
    },
  })
  let settled = false
  void result.then(
    () => {
      settled = true
    },
    () => {
      settled = true
    }
  )

  timeoutCallback()
  child.emit("exit", null, "SIGKILL")
  await Promise.resolve()
  assert.equal(settled, false)
  child.emit("close", null, "SIGKILL")
  await Promise.resolve()
  assert.equal(settled, false)

  finishTermination(true)
  await assert.rejects(result, /focused shard exceeded 123ms/u)
  assert.equal(cancelledTimer, "timer")
  assert.equal(child.listenerCount("error"), 0)
  assert.equal(child.listenerCount("exit"), 0)
  assert.equal(child.listenerCount("close"), 0)
})

test("direct-child close cannot replace explicit process-tree quiescence proof", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.exitCode = null
  child.signalCode = null
  let timeoutCallback
  const result = waitForChildClose(child, {
    description: "unproved tree",
    timeoutMs: 321,
    terminate: async () => undefined,
    scheduleTimeout(callback) {
      timeoutCallback = callback
      return "timer"
    },
    cancelTimeout: () => undefined,
  })

  timeoutCallback()
  child.emit("exit", null, "SIGKILL")
  child.emit("close", null, "SIGKILL")

  await assert.rejects(result, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.match(error.errors[0].message, /unproved tree exceeded 321ms/u)
    assert.match(error.errors[1].message, /did not confirm process-tree quiescence/u)
    assert.equal(error.processQuiesced, false)
    return true
  })
})

test("normal POSIX completion proves the owned group is absent before resolving", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 9876
  child.exitCode = null
  child.signalCode = null
  let confirmGroupAbsent
  const verification = new Promise((resolve) => {
    confirmGroupAbsent = resolve
  })
  let verificationCalls = 0
  const result = waitForChildClose(child, {
    description: "normal POSIX shard",
    timeoutMs: 10_000,
    processTreeOwnership: {
      kind: "posix-process-group",
      rootPid: 9876,
      groupId: 9876,
    },
    verifyProcessTree: async () => {
      verificationCalls += 1
      await verification
      return true
    },
  })
  let settled = false
  void result.then(() => {
    settled = true
  })

  child.emit("exit", 0, null)
  child.exitCode = 0
  child.emit("close", 0, null)
  await Promise.resolve()
  assert.equal(settled, false)
  assert.equal(verificationCalls, 1)

  confirmGroupAbsent()
  await result
  assert.equal(settled, true)
})

test("spontaneous POSIX failure proves the exited group absent before artifact finalization", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 9877
  child.exitCode = null
  child.signalCode = null
  let confirmTreeQuiescence
  const treeVerification = new Promise((resolve) => {
    confirmTreeQuiescence = resolve
  })
  let verificationCalls = 0
  const result = waitForChildClose(child, {
    description: "spontaneously failed POSIX shard",
    timeoutMs: 10_000,
    processTreeOwnership: {
      kind: "posix-process-group",
      rootPid: 9877,
      groupId: 9877,
    },
    terminate: async () => assert.fail("an exited process-group identity must not be signalled"),
    verifyProcessTree: async () => {
      verificationCalls += 1
      return treeVerification
    },
  })
  let settled = false
  void result.catch(() => {
    settled = true
  })

  child.emit("exit", 7, null)
  child.exitCode = 7
  child.emit("close", 7, null)
  await Promise.resolve()
  assert.equal(verificationCalls, 1)
  assert.equal(settled, false)

  confirmTreeQuiescence(true)
  await assert.rejects(result, (error) => {
    assert.match(error.message, /exited with code 7/u)
    assert.equal(error.processQuiesced, true)
    return true
  })
})

test("spontaneous Windows failure stays fail-closed when the dead-root tree cannot be proven", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 9878
  child.exitCode = null
  child.signalCode = null
  let terminationCalls = 0
  const result = waitForChildClose(child, {
    description: "spontaneously failed Windows shard",
    timeoutMs: 10_000,
    processTreeOwnership: { kind: "windows-process-tree", rootPid: 9878 },
    terminate: async () => {
      terminationCalls += 1
      assert.fail("taskkill must not target a Windows PID after its root exited")
    },
  })

  child.emit("exit", null, "SIGABRT")
  child.signalCode = "SIGABRT"
  child.emit("close", null, "SIGABRT")

  await assert.rejects(result, (error) => {
    assert.match(error.message, /exited due to signal SIGABRT/u)
    assert.equal(error.processQuiesced, false)
    return true
  })
  assert.equal(terminationCalls, 0)
})

test("Windows job ownership is durable and status identity is strict", async () => {
  const { createWindowsJobOwnership, parseWindowsProcessHostStatus } = await import(runnerUrl)
  const child = { pid: 43210 }
  const control = { write() {} }
  const ownership = createWindowsJobOwnership(child, {
    statusPath: "C:/runs/stryker/proof.json",
    jobToken: "11111111-1111-4111-8111-111111111111",
    control,
  })

  assert.deepEqual(
    {
      kind: ownership.kind,
      rootPid: ownership.rootPid,
      hostPid: ownership.hostPid,
      statusPath: ownership.statusPath,
      jobToken: ownership.jobToken,
      protocolVersion: ownership.protocolVersion,
    },
    {
      kind: "windows-job-object",
      rootPid: 43210,
      hostPid: 43210,
      statusPath: "C:/runs/stryker/proof.json",
      jobToken: "11111111-1111-4111-8111-111111111111",
      protocolVersion: 1,
    }
  )
  assert.throws(
    () =>
      parseWindowsProcessHostStatus(
        JSON.stringify({
          schemaVersion: 1,
          protocolVersion: 1,
          state: "job_empty",
          hostPid: 43210,
          targetPid: 43211,
          jobToken: "not a token!",
          exitCode: 0,
          quiesced: true,
          readyAcknowledged: true,
          reason: null,
        })
      ),
    /job token has an unsafe shape/u
  )
  assert.throws(
    () =>
      createWindowsJobOwnership(child, {
        statusPath: "relative/proof.json",
        jobToken: "11111111-1111-4111-8111-111111111111",
        control,
      }),
    /status path is required/u
  )
})

test("Windows normal success waits for an authoritative empty-job proof", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 43220
  child.exitCode = null
  child.signalCode = null
  let proveEmpty
  const proof = new Promise((resolve) => {
    proveEmpty = resolve
  })
  let verified = 0
  const result = waitForChildClose(child, {
    description: "Windows job shard",
    timeoutMs: 10_000,
    processTreeOwnership: {
      kind: "windows-job-object",
      rootPid: 43220,
      hostPid: 43220,
      statusPath: "C:/runs/stryker/proof.json",
      jobToken: "22222222-2222-4222-8222-222222222222",
      protocolVersion: 1,
    },
    verifyWindowsJob: async () => {
      verified += 1
      await proof
      return true
    },
  })
  let settled = false
  void result.then(() => {
    settled = true
  })

  child.emit("exit", 0, null)
  child.exitCode = 0
  child.emit("close", 0, null)
  await Promise.resolve()
  assert.equal(verified, 1)
  assert.equal(settled, false)

  proveEmpty()
  await result
  assert.equal(settled, true)
})

test("Windows legacy PID ownership cannot claim normal close success", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 43221
  child.exitCode = null
  child.signalCode = null
  const result = waitForChildClose(child, {
    description: "unowned Windows shard",
    timeoutMs: 10_000,
    processTreeOwnership: { kind: "windows-process-tree", rootPid: 43221 },
  })

  child.emit("exit", 0, null)
  child.exitCode = 0
  child.emit("close", 0, null)
  await assert.rejects(result, (error) => {
    assert.equal(error.processQuiesced, false)
    assert.match(error.message, /durable Windows job proof/u)
    return true
  })
})

test("Windows job termination uses its control pipe and accepts only final proof", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const writes = []
  const child = {
    pid: 43222,
    exitCode: null,
    signalCode: null,
    stdin: {
      write(value, callback) {
        writes.push(value)
        callback?.()
      },
    },
  }
  const ownership = {
    kind: "windows-job-object",
    rootPid: 43222,
    hostPid: 43222,
    statusPath: "C:/runs/stryker/proof.json",
    jobToken: "33333333-3333-4333-8333-333333333333",
    protocolVersion: 1,
    control: child.stdin,
  }
  let reads = 0
  const result = await terminateOwnedProcessTree(child, ownership, {
    readStatus: async () => {
      reads += 1
      return reads < 2
        ? undefined
        : {
            schemaVersion: 1,
            protocolVersion: 1,
            state: "job_terminated",
            hostPid: 43222,
            targetPid: 43223,
            jobToken: ownership.jobToken,
            exitCode: 143,
            quiesced: true,
            readyAcknowledged: true,
            reason: null,
          }
    },
    delay: async () => undefined,
  })

  assert.equal(result, true)
  assert.deepEqual(writes, ["TERMINATE\n"])
})

test("Windows job termination never targets a reused host PID after close", async () => {
  const { terminateOwnedProcessTree } = await import(runnerUrl)
  const calls = []
  const child = {
    pid: 43224,
    exitCode: 0,
    signalCode: null,
    stdin: {
      write() {
        calls.push("write")
      },
    },
  }
  await assert.rejects(
    () =>
      terminateOwnedProcessTree(
        child,
        {
          kind: "windows-job-object",
          rootPid: 43224,
          hostPid: 43224,
          statusPath: "C:/runs/stryker/proof.json",
          jobToken: "44444444-4444-4444-8444-444444444444",
          protocolVersion: 1,
          control: { write() {} },
        },
        {
          execFileCommand: async (...args) => calls.push(args),
        }
      ),
    /host exited before durable job termination could be proven/u
  )
  assert.deepEqual(calls, [])
})

test("Windows terminal proof is token-bound and records READY durably", async (t) => {
  const { verifyWindowsJobQuiescence } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-windows-proof-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const statusPath = path.join(root, "proof.json")
  const ownership = {
    kind: "windows-job-object",
    rootPid: 43225,
    hostPid: 43225,
    statusPath,
    jobToken: "55555555-5555-4555-8555-555555555555",
    protocolVersion: 1,
    control: { write() {} },
  }
  await writeFile(
    statusPath,
    JSON.stringify({
      schemaVersion: 1,
      protocolVersion: 1,
      state: "job_empty",
      hostPid: 43225,
      targetPid: 43226,
      jobToken: ownership.jobToken,
      exitCode: 0,
      quiesced: true,
      readyAcknowledged: true,
      reason: null,
    }),
    "utf8"
  )
  assert.equal(await verifyWindowsJobQuiescence(ownership), true)

  await writeFile(
    statusPath,
    JSON.stringify({
      schemaVersion: 1,
      protocolVersion: 1,
      state: "job_empty",
      hostPid: 43225,
      targetPid: 43226,
      jobToken: ownership.jobToken,
      exitCode: 0,
      quiesced: true,
      readyAcknowledged: false,
      reason: null,
    }),
    "utf8"
  )
  await assert.rejects(
    () => verifyWindowsJobQuiescence(ownership, { timeoutMs: 0 }),
    /READY acknowledgement/u
  )
})

test("the checked-in Windows host contains the atomic Job Object lifecycle", async () => {
  const source = await readFile(
    new URL("../tools/stryker-process-host/src/main.rs", runnerUrl),
    "utf8"
  )
  assert.match(source, /CREATE_SUSPENDED/u)
  assert.match(source, /AssignProcessToJobObject/u)
  assert.match(source, /JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE/u)
  assert.match(source, /TerminateJobObject/u)
  assert.match(source, /PROC_THREAD_ATTRIBUTE_HANDLE_LIST/u)
  assert.doesNotMatch(source, /taskkill/u)
})

test("Windows process-host termination failures fail closed without waiting for an empty proof", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 43227
  child.exitCode = null
  child.signalCode = null
  let statusReads = 0
  let timeoutCallback
  const terminationFailure = new Error(
    "Windows process-host reported TerminateJobObject failed with Win32 error 5"
  )
  const result = waitForChildClose(child, {
    description: "Windows termination-failure shard",
    timeoutMs: 1_000,
    terminationGraceMs: 1_000,
    processTreeOwnership: {
      kind: "windows-job-object",
      rootPid: 43227,
      hostPid: 43227,
      statusPath: "C:/runs/stryker/proof.json",
      jobToken: "66666666-6666-4666-8666-666666666666",
      protocolVersion: 1,
      control: { write() {} },
    },
    terminate: async () => {
      throw terminationFailure
    },
    verifyWindowsJob: async () => {
      statusReads += 1
      throw new Error("the runner must not claim quiescence after a failed native termination")
    },
    scheduleTimeout: (callback) => {
      timeoutCallback = callback
      return "timer"
    },
    cancelTimeout: () => undefined,
  })

  timeoutCallback()
  child.emit("exit", null, "SIGTERM")
  child.signalCode = "SIGTERM"
  child.emit("close", null, "SIGTERM")

  await assert.rejects(result, (error) => {
    assert.equal(error.processQuiesced, false)
    assert.equal(error.errors?.[1], terminationFailure)
    return true
  })
  assert.equal(statusReads, 0)
})

test("native host source returns immediately on failed termination and retains a false quiescence proof", async () => {
  const source = await readFile(
    new URL("../tools/stryker-process-host/src/main.rs", runnerUrl),
    "utf8"
  )
  assert.match(source, /termination_error/u)
  assert.match(source, /termination_error\.as_ref\(\)/u)
  assert.match(source, /return Err\(clone_io_error\(error\)\)/u)
  assert.match(source, /terminate_then_wait/u)
  assert.match(source, /state: if quiesced \{\s*"job_terminated"\s*\} else \{\s*"error"/su)
  assert.match(source, /quiesced: false/u)
  assert.doesNotMatch(source, /let _ = terminate_job/u)
})

test("native host bounds successful cancellation while the empty proof is stuck", async () => {
  const source = await readFile(
    new URL("../tools/stryker-process-host/src/main.rs", runnerUrl),
    "utf8"
  )
  const start = source.indexOf("fn wait_for_empty_with_control")
  const end = source.indexOf("fn run()", start)
  assert.ok(start >= 0 && end > start, "controlled empty-proof loop is present")
  const controlledProof = source.slice(start, end)
  assert.match(controlledProof, /cancellation_started/u)
  assert.match(controlledProof, /cancellation_started[\s\S]*FAILURE_CLEANUP_WAIT/u)
  assert.match(controlledProof, /MAX_STATUS_WAIT/u)
  assert.match(controlledProof, /job active-process count did not reach zero after cancellation/u)
  assert.match(source, /quiesced = result\.is_none\(\)/u)
})

test("child close reports normal exits and retains timeout termination failures", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const successfulChild = new EventEmitter()
  const success = waitForChildClose(successfulChild, {
    description: "successful shard",
    timeoutMs: 1_000,
  })
  successfulChild.emit("exit", 0, null)
  successfulChild.emit("close", 0, null)
  await success
  assert.equal(successfulChild.listenerCount("error"), 0)
  assert.equal(successfulChild.listenerCount("exit"), 0)
  assert.equal(successfulChild.listenerCount("close"), 0)

  const failedChild = new EventEmitter()
  const failure = waitForChildClose(failedChild, {
    description: "failed shard",
    timeoutMs: 1_000,
  })
  failedChild.emit("exit", 7, null)
  failedChild.emit("close", 7, null)
  await assert.rejects(failure, /failed shard exited with code 7/u)
  assert.equal(failedChild.listenerCount("error"), 0)
  assert.equal(failedChild.listenerCount("exit"), 0)
  assert.equal(failedChild.listenerCount("close"), 0)

  const timedOutChild = new EventEmitter()
  const terminationError = new Error("taskkill failed")
  let timeoutCallback
  let rejectionCount = 0
  const timedOut = waitForChildClose(timedOutChild, {
    description: "timed-out shard",
    timeoutMs: 456,
    terminate: async () => {
      throw terminationError
    },
    scheduleTimeout: (callback) => {
      timeoutCallback = callback
      return "timer"
    },
    cancelTimeout: () => undefined,
  })
  void timedOut.catch(() => {
    rejectionCount += 1
  })
  timeoutCallback()
  timedOutChild.emit("exit", null, "SIGKILL")
  timedOutChild.emit("close", null, "SIGKILL")
  await assert.rejects(timedOut, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.match(error.errors[0].message, /timed-out shard exceeded 456ms/u)
    assert.equal(error.errors[1], terminationError)
    assert.equal(error.cause, error.errors[0])
    assert.equal(
      error.processQuiesced,
      false,
      "a failed tree terminator cannot prove descendant quiescence even when the parent closed"
    )
    return true
  })
  timedOutChild.emit("close", null, "SIGKILL")
  await Promise.resolve()
  assert.equal(rejectionCount, 1)
  assert.equal(timedOutChild.listenerCount("error"), 0)
  assert.equal(timedOutChild.listenerCount("exit"), 0)
  assert.equal(timedOutChild.listenerCount("close"), 0)
})

test("child timeout has a bounded grace when termination or close hangs", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  const timers = []
  const result = waitForChildClose(child, {
    description: "hung shard",
    timeoutMs: 500,
    terminationGraceMs: 75,
    terminate: async () => new Promise(() => undefined),
    scheduleTimeout: (callback, milliseconds) => {
      const timer = { callback, milliseconds }
      timers.push(timer)
      return timer
    },
    cancelTimeout: () => undefined,
  })

  assert.equal(timers[0].milliseconds, 500)
  timers[0].callback()
  assert.equal(timers[1].milliseconds, 75)
  timers[1].callback()

  await assert.rejects(result, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.match(error.errors[0].message, /hung shard exceeded 500ms/u)
    assert.match(error.errors[1].message, /did not terminate and close within 75ms/u)
    assert.equal(error.processQuiesced, false)
    return true
  })
  assert.equal(child.listenerCount("error"), 0)
  assert.equal(child.listenerCount("exit"), 0)
  assert.equal(child.listenerCount("close"), 0)
})

test("process signals abort before lock acquisition and a second signal cannot bypass cleanup", async () => {
  const { installProcessSignalCancellation, throwIfCancellationRequested } = await import(runnerUrl)
  const processEvents = new EventEmitter()
  const cancellation = installProcessSignalCancellation({ processEvents })
  let abortEvents = 0
  cancellation.signal.addEventListener("abort", () => {
    abortEvents += 1
  })

  processEvents.emit("SIGINT")
  assert.throws(() => throwIfCancellationRequested(cancellation.signal), /interrupted by SIGINT/u)
  processEvents.emit("SIGTERM")

  assert.equal(abortEvents, 1)
  assert.match(cancellation.signal.reason.message, /interrupted by SIGINT/u)
  assert.equal(processEvents.listenerCount("SIGINT"), 1)
  assert.equal(processEvents.listenerCount("SIGTERM"), 1)
  cancellation.dispose()
  assert.equal(processEvents.listenerCount("SIGINT"), 0)
  assert.equal(processEvents.listenerCount("SIGTERM"), 0)
})

test("a process signal terminates every active child, awaits close, and stops shard scheduling", async () => {
  const { installProcessSignalCancellation, runPool, waitForChildClose } = await import(runnerUrl)
  const processEvents = new EventEmitter()
  const cancellation = installProcessSignalCancellation({ processEvents })
  const children = [new EventEmitter(), new EventEmitter()]
  for (const child of children) {
    child.exitCode = null
    child.signalCode = null
  }
  const terminations = []
  const started = []
  const execution = runPool(
    [0, 1, 2, 3],
    2,
    async (index) => {
      started.push(index)
      return waitForChildClose(children[index], {
        description: `signal shard ${index}`,
        timeoutMs: 10_000,
        abortSignal: cancellation.signal,
        terminate: async () =>
          new Promise((resolve) => {
            terminations[index] = resolve
          }),
      })
    },
    { abortSignal: cancellation.signal }
  )
  let settled = false
  void execution.catch(() => {
    settled = true
  })

  await new Promise((resolve) => setImmediate(resolve))
  processEvents.emit("SIGTERM")
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(started, [0, 1])
  assert.equal(terminations.length, 2)

  processEvents.emit("SIGINT")
  children[0].emit("exit", null, "SIGTERM")
  children[0].emit("close", null, "SIGTERM")
  children[1].emit("exit", null, "SIGTERM")
  children[1].emit("close", null, "SIGTERM")
  await Promise.resolve()
  assert.equal(settled, false, "close alone must not bypass awaited tree termination")

  terminations[0](true)
  terminations[1](true)
  await assert.rejects(execution, (error) => {
    assert.match(error.message, /SIGTERM/u)
    assert.notEqual(error.processQuiesced, false)
    return true
  })
  assert.deepEqual(started, [0, 1])
  for (const child of children) {
    assert.equal(child.listenerCount("error"), 0)
    assert.equal(child.listenerCount("exit"), 0)
    assert.equal(child.listenerCount("close"), 0)
  }
  cancellation.dispose()
})

test("a child error that precedes cancellation remains the primary execution failure", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.exitCode = null
  child.signalCode = null
  const controller = new AbortController()
  const childError = new Error("spawn pipe failed")
  const cancellationError = Object.assign(new Error("Stryker execution interrupted by SIGINT"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGINT",
  })
  let finishTermination
  const result = waitForChildClose(child, {
    description: "errored shard",
    timeoutMs: 10_000,
    abortSignal: controller.signal,
    terminate: async () =>
      new Promise((resolve) => {
        finishTermination = resolve
      }),
  })

  child.emit("error", childError)
  controller.abort(cancellationError)
  child.emit("exit", null, "SIGKILL")
  child.emit("close", null, "SIGKILL")
  await new Promise((resolve) => setImmediate(resolve))
  finishTermination(true)

  await assert.rejects(result, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, childError)
    assert.deepEqual(error.errors, [childError, cancellationError])
    assert.equal(error.processQuiesced, true)
    return true
  })
})

test("a child error after cancellation is retained as a fail-closed secondary failure", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.exitCode = null
  child.signalCode = null
  const controller = new AbortController()
  const cancellationError = Object.assign(new Error("Stryker execution interrupted by SIGTERM"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGTERM",
  })
  const lateChildError = new Error("late child process failure")
  let finishTermination
  const result = waitForChildClose(child, {
    description: "late-error shard",
    timeoutMs: 10_000,
    abortSignal: controller.signal,
    terminate: async () =>
      new Promise((resolve) => {
        finishTermination = resolve
      }),
  })

  controller.abort(cancellationError)
  await Promise.resolve()
  child.emit("error", lateChildError)
  child.emit("exit", null, "SIGKILL")
  child.emit("close", null, "SIGKILL")
  finishTermination(true)

  await assert.rejects(result, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, cancellationError)
    assert.deepEqual(error.errors, [cancellationError, lateChildError])
    assert.equal(error.processQuiesced, false)
    return true
  })
})

test("late child failures precede termination failures in cancellation diagnostics", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.exitCode = null
  child.signalCode = null
  const controller = new AbortController()
  const cancellationError = Object.assign(new Error("Stryker execution interrupted by SIGINT"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGINT",
  })
  const lateChildError = new Error("child failed while stopping")
  const terminationError = new Error("tree termination failed")
  const result = waitForChildClose(child, {
    description: "late-error termination shard",
    timeoutMs: 10_000,
    abortSignal: controller.signal,
    terminate: async () => {
      throw terminationError
    },
  })

  controller.abort(cancellationError)
  await Promise.resolve()
  await Promise.resolve()
  child.emit("error", lateChildError)
  child.emit("exit", null, "SIGKILL")
  child.emit("close", null, "SIGKILL")

  await assert.rejects(result, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, cancellationError)
    assert.deepEqual(error.errors, [cancellationError, lateChildError, terminationError])
    assert.equal(error.processQuiesced, false)
    return true
  })
})

test("a signal after exit never targets the dead root and fails closed on Windows", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 12_345
  child.exitCode = null
  child.signalCode = null
  const controller = new AbortController()
  const cancellationError = Object.assign(new Error("Stryker execution interrupted by SIGTERM"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGTERM",
  })
  let terminationCalls = 0
  const result = waitForChildClose(child, {
    description: "exited shard",
    timeoutMs: 10_000,
    abortSignal: controller.signal,
    processTreeOwnership: { kind: "windows-process-tree", rootPid: 12_345 },
    terminate: async () => {
      terminationCalls += 1
      assert.fail("a post-exit cancellation must not taskkill a reusable PID")
    },
  })
  let settled = false
  void result.catch(() => {
    settled = true
  })

  child.emit("exit", 0, null)
  child.exitCode = 0
  controller.abort(cancellationError)
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(settled, false)
  child.emit("close", 0, null)

  await assert.rejects(result, (error) => {
    assert.equal(error, cancellationError)
    assert.equal(error.processQuiesced, false)
    return true
  })
  assert.equal(terminationCalls, 0)
})

test("signal cancellation preserves termination failures and fails closed without close", async () => {
  const { waitForChildClose } = await import(runnerUrl)
  const cancellationError = Object.assign(new Error("Stryker execution interrupted by SIGTERM"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGTERM",
  })

  const failedChild = new EventEmitter()
  failedChild.exitCode = null
  failedChild.signalCode = null
  const failedController = new AbortController()
  const terminationError = new Error("taskkill denied")
  const failed = waitForChildClose(failedChild, {
    description: "termination failure shard",
    timeoutMs: 10_000,
    abortSignal: failedController.signal,
    terminate: async () => {
      throw terminationError
    },
  })
  failedController.abort(cancellationError)
  failedChild.emit("exit", null, "SIGKILL")
  failedChild.emit("close", null, "SIGKILL")
  await assert.rejects(failed, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, cancellationError)
    assert.equal(error.errors[0], cancellationError)
    assert.equal(error.errors[1], terminationError)
    assert.equal(error.processQuiesced, false)
    return true
  })

  const missingCloseChild = new EventEmitter()
  missingCloseChild.exitCode = null
  missingCloseChild.signalCode = null
  const missingCloseController = new AbortController()
  const timers = []
  const missingClose = waitForChildClose(missingCloseChild, {
    description: "missing-close shard",
    timeoutMs: 10_000,
    terminationGraceMs: 75,
    abortSignal: missingCloseController.signal,
    terminate: async () => true,
    scheduleTimeout: (callback, milliseconds) => {
      const timer = { callback, milliseconds }
      timers.push(timer)
      return timer
    },
    cancelTimeout: () => undefined,
  })
  missingCloseController.abort(cancellationError)
  await Promise.resolve()
  assert.equal(timers[1].milliseconds, 75)
  timers[1].callback()
  await assert.rejects(missingClose, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, cancellationError)
    assert.equal(error.errors[0], cancellationError)
    assert.match(error.errors[1].message, /did not terminate and close within 75ms/u)
    assert.equal(error.processQuiesced, false)
    return true
  })
})

test("executable exit codes preserve conventional SIGINT and SIGTERM semantics", async () => {
  const { runnerExitCode } = await import(runnerUrl)
  const sigint = Object.assign(new Error("interrupted"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGINT",
  })
  const sigterm = Object.assign(new Error("interrupted"), {
    code: "STRYKER_INTERRUPTED",
    signalName: "SIGTERM",
  })

  assert.equal(runnerExitCode(sigint), 130)
  assert.equal(
    runnerExitCode(new AggregateError([sigterm], "finalization", { cause: sigterm })),
    143
  )
  const ordinaryPrimary = new Error("spawn failed before cancellation")
  assert.equal(
    runnerExitCode(
      new AggregateError([ordinaryPrimary, sigterm], "spawn failed before cancellation", {
        cause: ordinaryPrimary,
      })
    ),
    1
  )
  assert.equal(runnerExitCode(new Error("ordinary failure")), 1)
})

test("temporary cleanup retries only bounded transient Windows failures", async () => {
  const { removeOwnedTemporaryDirectory } = await import(runnerUrl)
  const runId = "run-id"
  const root = path.join(
    os.tmpdir(),
    "university-ecosystem-stryker-runs",
    "repository",
    "a".repeat(40),
    runId
  )
  const codes = ["EPERM", "EBUSY", "ENOTEMPTY"]
  const delays = []
  let attempts = 0

  await removeOwnedTemporaryDirectory(root, runId, {
    platform: "win32",
    retryDelaysMs: [10, 20, 40],
    remove: async () => {
      const code = codes[attempts]
      attempts += 1
      if (code) throw Object.assign(new Error(code), { code })
    },
    delay: async (milliseconds) => {
      delays.push(milliseconds)
    },
  })
  assert.equal(attempts, 4)
  assert.deepEqual(delays, [10, 20, 40])

  attempts = 0
  await assert.rejects(
    () =>
      removeOwnedTemporaryDirectory(root, runId, {
        platform: "win32",
        retryDelaysMs: [10, 20],
        remove: async () => {
          attempts += 1
          throw Object.assign(new Error("denied"), { code: "EACCES" })
        },
        delay: async () => assert.fail("non-transient cleanup must not retry"),
      }),
    /denied/u
  )
  assert.equal(attempts, 1)
})

test("temporary cleanup retries a resolved removal until ENOENT proves the owned path is absent", async () => {
  const { removeOwnedTemporaryDirectory } = await import(runnerUrl)
  const runId = "verified-removal"
  const root = path.join(
    os.tmpdir(),
    "university-ecosystem-stryker-runs",
    "repository",
    "b".repeat(40),
    runId
  )
  const removedPaths = []
  const inspectedPaths = []
  const delays = []
  let inspections = 0

  await removeOwnedTemporaryDirectory(root, runId, {
    platform: "win32",
    retryDelaysMs: [10, 20],
    remove: async (target) => removedPaths.push(target),
    inspect: async (target) => {
      inspectedPaths.push(target)
      inspections += 1
      if (inspections < 3) return { isDirectory: () => true }
      throw Object.assign(new Error("absent"), { code: "ENOENT" })
    },
    delay: async (milliseconds) => delays.push(milliseconds),
  })

  assert.deepEqual(removedPaths, [root, root, root])
  assert.deepEqual(inspectedPaths, [root, root, root])
  assert.deepEqual(delays, [10, 20])

  await assert.rejects(
    () =>
      removeOwnedTemporaryDirectory(root, runId, {
        platform: "win32",
        retryDelaysMs: [10],
        remove: async () => undefined,
        inspect: async () => ({ isDirectory: () => true }),
        delay: async () => undefined,
      }),
    /still exists after removal/u
  )
})

test("exhausted temporary cleanup reports bounded diagnostic provenance", async () => {
  const { removeOwnedTemporaryDirectory } = await import(runnerUrl)
  const runId = "cleanup-diagnostic"
  const root = path.join(
    os.tmpdir(),
    "university-ecosystem-stryker-runs",
    "repository",
    "c".repeat(40),
    runId
  )
  const terminalError = Object.assign(new Error("directory remains busy"), { code: "EBUSY" })
  let nowCalls = 0

  await assert.rejects(
    () =>
      removeOwnedTemporaryDirectory(root, runId, {
        platform: "win32",
        retryDelaysMs: [10, 20],
        remove: async () => {
          throw terminalError
        },
        delay: async () => undefined,
        now: () => {
          nowCalls += 1
          return nowCalls === 1 ? 1_000 : 1_375
        },
      }),
    (error) => {
      assert.equal(error.cause, terminalError)
      assert.equal(error.code, "EBUSY")
      assert.equal(error.path, root)
      assert.equal(error.attempts, 3)
      assert.equal(error.elapsedMs, 375)
      assert.match(error.message, /3 attempts/u)
      assert.match(error.message, /375ms/u)
      assert.match(error.message, /terminal code EBUSY/u)
      assert.equal(error.message.includes(root), true)
      return true
    }
  )
})

test("post-lock cancellation revokes markers and finalizes the owned temp and lock", async () => {
  const { finalizeMutationRun, installProcessSignalCancellation } = await import(runnerUrl)
  const processEvents = new EventEmitter()
  const cancellation = installProcessSignalCancellation({ processEvents })
  const calls = []

  processEvents.emit("SIGTERM")
  await assert.rejects(
    () =>
      finalizeMutationRun({
        cancellationSignal: cancellation.signal,
        cleanupTemporary: async () => calls.push("cleanup"),
        revokeMarker: async () => calls.push("marker"),
        releaseLock: async (prepareRelease) => {
          const commitRelease = await prepareRelease()
          commitRelease()
          calls.push("release")
        },
      }),
    /interrupted by SIGTERM/u
  )

  assert.deepEqual(calls, ["cleanup", "marker", "release"])
  cancellation.dispose()
})

test("a signal during lock release revokes markers before the release commit", async () => {
  const { finalizeMutationRun, installProcessSignalCancellation } = await import(runnerUrl)
  const processEvents = new EventEmitter()
  const cancellation = installProcessSignalCancellation({ processEvents })
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        cancellationSignal: cancellation.signal,
        cleanupTemporary: async () => calls.push("cleanup"),
        revokeMarker: async () => calls.push("marker"),
        releaseLock: async (beforeRelease) => {
          calls.push("release-start")
          processEvents.emit("SIGTERM")
          const commitRelease = await beforeRelease()
          commitRelease()
          calls.push("release-commit")
        },
      }),
    /interrupted by SIGTERM/u
  )

  assert.deepEqual(calls, ["cleanup", "release-start", "marker", "release-commit"])
  cancellation.dispose()
})

test("a signal after release preparation retains the lock until marker revocation", async () => {
  const { finalizeMutationRun, installProcessSignalCancellation } = await import(runnerUrl)
  const processEvents = new EventEmitter()
  const cancellation = installProcessSignalCancellation({ processEvents })
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        cancellationSignal: cancellation.signal,
        cleanupTemporary: async () => calls.push("cleanup"),
        revokeMarker: async () => calls.push("marker"),
        releaseLock: async (prepareRelease) => {
          calls.push("release-start")
          const commitRelease = await prepareRelease()
          processEvents.emit("SIGINT")
          commitRelease()
          calls.push("release-commit")
        },
      }),
    /interrupted by SIGINT/u
  )

  assert.deepEqual(calls, ["cleanup", "release-start", "marker"])
  cancellation.dispose()
})

test("required marker revocation without a callback retains the run lock", async () => {
  const { finalizeMutationRun } = await import(runnerUrl)
  const primary = new Error("mutation failed")
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        primaryError: primary,
        cleanupTemporary: async () => calls.push("cleanup"),
        releaseLock: async () => calls.push("release"),
      }),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.equal(error.cause, primary)
      assert.equal(error.errors[0], primary)
      assert.match(error.errors[1].message, /marker revocation is required but unavailable/u)
      return true
    }
  )
  assert.deepEqual(calls, ["cleanup"])
})

test("a failure before lock acquisition is surfaced without fictitious marker cleanup", async () => {
  const { finalizeMutationRun } = await import(runnerUrl)
  const primary = new Error("invalid runner arguments")

  await assert.rejects(
    () => finalizeMutationRun({ primaryError: primary }),
    (error) => error === primary
  )
})

test("finalization preserves the primary failure and always releases the lock", async () => {
  const { finalizeMutationRun } = await import(runnerUrl)
  const primary = new Error("test timeout")
  const cleanup = new Error("cleanup failed")
  const release = new Error("release failed")
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        primaryError: primary,
        cleanupTemporary: async () => {
          calls.push("cleanup")
          throw cleanup
        },
        releaseLock: async (prepareRelease) => {
          const commitRelease = await prepareRelease()
          commitRelease()
          calls.push("release")
          throw release
        },
        revokeMarker: async () => calls.push("marker"),
      }),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.equal(error.cause, primary)
      assert.deepEqual(error.errors, [primary, cleanup, release])
      return true
    }
  )
  assert.deepEqual(calls, ["cleanup", "marker", "release"])
})

test("finalization retains lock and temp when child close is unconfirmed", async () => {
  const { finalizeMutationRun } = await import(runnerUrl)
  const primary = Object.assign(new Error("timeout"), { processQuiesced: false })
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        primaryError: primary,
        cleanupTemporary: async () => calls.push("cleanup"),
        releaseLock: async () => calls.push("release"),
        revokeMarker: async () => calls.push("marker"),
      }),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.equal(error.cause, primary)
      assert.equal(error.errors[0], primary)
      assert.match(error.errors[1].message, /run lock were retained/u)
      return true
    }
  )
  assert.deepEqual(calls, ["marker"])
})

test("parallel shard pool waits for every worker before surfacing a failure", async () => {
  const { runPool } = await import(runnerUrl)
  let releaseSecond
  const second = new Promise((resolve) => {
    releaseSecond = resolve
  })
  const firstError = new Error("first shard failed")
  const started = []
  const execution = runPool(["first", "second", "third", "fourth"], 2, async (item) => {
    started.push(item)
    if (item === "first") throw firstError
    await second
    return "completed"
  })
  let settled = false
  void execution.then(
    () => {
      settled = true
    },
    () => {
      settled = true
    }
  )

  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(settled, false)
  releaseSecond()
  await assert.rejects(execution, (error) => error === firstError)
  assert.deepEqual(started, ["first", "second"])
})

test("parallel shard pool preserves the first observed failure rather than worker order", async () => {
  const { runPool } = await import(runnerUrl)
  let releaseEarlierWorker
  const earlierWorkerGate = new Promise((resolve) => {
    releaseEarlierWorker = resolve
  })
  const firstObserved = Object.assign(new Error("second worker failed first"), {
    processQuiesced: true,
  })
  const laterObserved = Object.assign(new Error("first worker failed later"), {
    processQuiesced: false,
  })
  const started = []
  const execution = runPool(
    ["earlier-worker", "later-worker", "must-not-start"],
    2,
    async (item) => {
      started.push(item)
      if (item === "later-worker") throw firstObserved
      await earlierWorkerGate
      throw laterObserved
    }
  )
  const verification = assert.rejects(execution, (error) => {
    assert.equal(error instanceof AggregateError, true)
    assert.equal(error.cause, firstObserved)
    assert.deepEqual(error.errors, [firstObserved, laterObserved])
    assert.match(error.message, /second worker failed first/u)
    assert.equal(error.processQuiesced, false)
    return true
  })

  // Let the rejected worker stop scheduling before releasing its sibling.
  await new Promise((resolve) => setImmediate(resolve))
  releaseEarlierWorker()
  await verification
  assert.deepEqual(started, ["earlier-worker", "later-worker"])
})

test("failed marker revocation retains the owned run lock", async () => {
  const { finalizeMutationRun } = await import(runnerUrl)
  const primary = new Error("test failure")
  const markerError = new Error("marker cleanup failed")
  const calls = []

  await assert.rejects(
    () =>
      finalizeMutationRun({
        primaryError: primary,
        cleanupTemporary: async () => calls.push("cleanup"),
        revokeMarker: async () => {
          calls.push("marker")
          throw markerError
        },
        releaseLock: async () => calls.push("release"),
      }),
    (error) => {
      assert.equal(error instanceof AggregateError, true)
      assert.deepEqual(error.errors, [primary, markerError])
      return true
    }
  )
  assert.deepEqual(calls, ["cleanup", "marker"])
})
