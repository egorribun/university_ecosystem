import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { execFileSync, spawnSync } from "node:child_process"
import { lstat, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const subjectUrl = new URL("./final-html-root-inventory.mjs", import.meta.url)
const themeUrl = new URL("../public/theme-init.js", import.meta.url)
const i18nUrl = new URL("../public/static-shell-i18n.js", import.meta.url)
const privateCanary = "PRIVATE_FINAL_HTML_CANARY"
const entry = 'export const label = "Привет";\n'
const basicHtml =
  '<!doctype html><html><head><script type="module" src="/assets/index-A.js"></script>' +
  "</head><body>Привет</body></html>"
const kinds = new Set([
  "inline-classic",
  "inline-module",
  "inline-data",
  "inline-importmap",
  "external-classic",
  "external-module",
  "modulepreload",
  "script-preload",
])
const issueNames = [
  "baseElements",
  "computedImports",
  "foreignReferences",
  "importMaps",
  "parseErrors",
  "unknownScriptTypes",
  "unsafeReferences",
]

function digest(value) {
  return createHash("sha256").update(value).digest("hex")
}

async function fixture(html = basicHtml) {
  const root = await mkdtemp(path.join(os.tmpdir(), "final-html-inventory-"))
  const clientDir = path.join(root, "client")
  await mkdir(path.join(clientDir, "assets"), { recursive: true })
  await writeFile(path.join(clientDir, "assets/index-A.js"), entry)
  await writeFile(path.join(clientDir, "_shell.html"), html)
  await writeFile(path.join(clientDir, "index.html"), html)
  return { root, clientDir }
}

async function setHtml(item, html) {
  await writeFile(path.join(item.clientDir, "_shell.html"), html)
  await writeFile(path.join(item.clientDir, "index.html"), html)
}

function inspect(item) {
  // Isolated child bounds a regression that accidentally executes an inline loop.
  // Transport sentinels stop accidental network loading and make it observable.
  const program = [
    'import http from "node:http"',
    'import https from "node:https"',
    "let networkAttempts = 0",
    "const blocked = () => { networkAttempts += 1; throw new Error('NETWORK_DISABLED') }",
    "http.request = blocked",
    "http.get = blocked",
    "https.request = blocked",
    "https.get = blocked",
    "globalThis.fetch = blocked",
    "globalThis.WebSocket = blocked",
    "try {",
    "  const { inspectFinalHtml } = await import(" + JSON.stringify(subjectUrl.href) + ")",
    "  const value = await inspectFinalHtml(" + JSON.stringify(item.clientDir) + ")",
    "  if (networkAttempts !== 0) throw new Error('NETWORK_ATTEMPT')",
    "  process.stdout.write(JSON.stringify(value) + '\\n')",
    "} catch {",
    "  process.stderr.write('FINAL_HTML_TEST_CHILD_REJECTED\\n')",
    "  process.exitCode = 1",
    "}",
  ].join("\n")
  const result = spawnSync(process.execPath, ["--input-type=module"], {
    input: program,
    encoding: "utf8",
    timeout: 10_000,
    maxBuffer: 32_769,
    env: { ...process.env, FINAL_HTML_PRIVATE_CANARY: privateCanary },
  })
  assert.equal(Boolean(result.error), false, "inventory child must finish within its bound")
  assert.equal(result.status, 0, "inventory API must return a closed result")
  assert.equal(result.stderr === "", true, "inventory must not print parser or input details")
  assert.ok(Buffer.byteLength(result.stdout) <= 32_768)
  assert.equal(result.stdout.trimEnd().split("\n").length, 1)
  assert.equal(result.stdout.includes(item.root), false)
  assert.equal(result.stdout.includes(privateCanary), false)
  return JSON.parse(result.stdout)
}

function safePath(value) {
  assert.equal(typeof value, "string")
  assert.match(
    value,
    /^(?:assets\/[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:js|mjs)|(?:theme-init|static-shell-i18n|not-found-i18n|sw)\.js)$/u
  )
  assert.equal(value.includes(".."), false)
}

function receipt(value) {
  assert.notEqual(value, null, "valid final HTML must produce a diagnostic inventory")
  assert.deepEqual(Object.keys(value).sort(), [
    "documents",
    "documentsMatch",
    "kind",
    "schemaVersion",
  ])
  assert.equal(value.schemaVersion, 1)
  assert.equal(value.kind, "final-html-root-inventory-not-budget-proof")
  assert.equal(typeof value.documentsMatch, "boolean")
  assert.equal(value.documents.length, 2)
  assert.deepEqual(
    value.documents.map((document) => document.fileName),
    ["_shell.html", "index.html"]
  )
  for (const document of value.documents) {
    assert.deepEqual(Object.keys(document).sort(), [
      "complete",
      "fileName",
      "issues",
      "rawBytes",
      "roots",
      "sha256",
    ])
    assert.equal(typeof document.complete, "boolean")
    assert.ok(Number.isSafeInteger(document.rawBytes) && document.rawBytes > 0)
    assert.match(document.sha256, /^[0-9a-f]{64}$/u)
    assert.deepEqual(Object.keys(document.issues).sort(), issueNames)
    for (const count of Object.values(document.issues)) {
      assert.ok(Number.isSafeInteger(count) && count >= 0)
    }
    assert.ok(document.roots.length <= 128)
    for (const root of document.roots) {
      assert.deepEqual(Object.keys(root).sort(), [
        "assetPath",
        "computedImports",
        "imports",
        "kind",
        "parseErrors",
        "rawBytes",
        "sha256",
      ])
      assert.ok(kinds.has(root.kind))
      if (root.assetPath !== null) safePath(root.assetPath)
      assert.ok(Number.isSafeInteger(root.rawBytes) && root.rawBytes >= 0)
      assert.match(root.sha256, /^[0-9a-f]{64}$/u)
      assert.ok(Number.isSafeInteger(root.computedImports) && root.computedImports >= 0)
      assert.ok(Number.isSafeInteger(root.parseErrors) && root.parseErrors >= 0)
      assert.ok(root.imports.length <= 256)
      for (const edge of root.imports) {
        assert.deepEqual(Object.keys(edge).sort(), ["assetPath", "kind"])
        assert.ok(["static", "dynamic"].includes(edge.kind))
        safePath(edge.assetPath)
      }
    }
  }
  return value
}

async function withFixture(run, html = basicHtml) {
  const item = await fixture(html)
  try {
    await run(item)
  } finally {
    await rm(item.root, { recursive: true, force: true })
  }
}

test("final inventory hashes both final documents and actual UTF-8 root bytes", async () => {
  await withFixture(async (item) => {
    const value = receipt(inspect(item))
    assert.equal(value.documentsMatch, true)
    for (const document of value.documents) {
      assert.equal(document.rawBytes, Buffer.byteLength(basicHtml))
      assert.equal(document.sha256, digest(basicHtml))
      assert.equal(document.complete, true)
      assert.deepEqual(Object.values(document.issues), Array(7).fill(0))
      assert.deepEqual(document.roots, [
        {
          kind: "external-module",
          assetPath: "assets/index-A.js",
          rawBytes: Buffer.byteLength(entry),
          sha256: digest(entry),
          imports: [],
          computedImports: 0,
          parseErrors: 0,
        },
      ])
    }
    const changed = basicHtml.replace("Привет</body>", "Другой</body>")
    await writeFile(path.join(item.clientDir, "index.html"), changed)
    const different = receipt(inspect(item))
    assert.equal(different.documentsMatch, false)
    assert.equal(different.documents[0].sha256, digest(basicHtml))
    assert.equal(different.documents[1].sha256, digest(changed))
  })
})

test("actual public theme root exposes its local dynamic edge without execution", async () => {
  await withFixture(async (item) => {
    const theme = await readFile(themeUrl)
    const translations = await readFile(i18nUrl)
    await writeFile(path.join(item.clientDir, "theme-init.js"), theme)
    await writeFile(path.join(item.clientDir, "static-shell-i18n.js"), translations)
    await setHtml(
      item,
      '<script id="theme-init-script" src="/theme-init.js"></script>' +
        '<script type="module" src="/assets/index-A.js"></script>'
    )
    const value = receipt(inspect(item))
    for (const document of value.documents) {
      assert.equal(document.complete, true)
      assert.deepEqual(document.roots[0], {
        kind: "external-classic",
        assetPath: "theme-init.js",
        rawBytes: theme.length,
        sha256: digest(theme),
        imports: [{ kind: "dynamic", assetPath: "static-shell-i18n.js" }],
        computedImports: 0,
        parseErrors: 0,
      })
    }
  })
})

test("HTML root classification does not execute inline JavaScript", async () => {
  const inlineClassic = "while (true) {} // " + privateCanary
  const inlineModule =
    'export { label } from "/assets/index-A.js"; import("./static-shell-i18n.js");'
  const inlineData = JSON.stringify({ private: privateCanary })
  const importMap = '{"imports":{"hidden":"https://example.invalid/private"}}'
  const html = [
    "<SCRIPT>" + inlineClassic + "</SCRIPT>",
    '<script type="module">' + inlineModule + "</script>",
    '<script type="application/json">' + inlineData + "</script>",
    '<script type="importmap">' + importMap + "</script>",
    '<SCRIPT SRC="&#47;theme-init.js"></SCRIPT>',
    '<script TYPE="module" SRC="/assets/index-A.js"></script>',
    '<LINK REL="modulepreload" HREF="/assets/index-A.js">',
    '<link rel="preload" as="script" href="/theme-init.js">',
  ].join("")
  await withFixture(async (item) => {
    await writeFile(path.join(item.clientDir, "theme-init.js"), "void 0;")
    const value = receipt(inspect(item))
    for (const document of value.documents) {
      assert.equal(document.complete, false)
      assert.equal(document.issues.importMaps, 1)
      assert.deepEqual(
        document.roots.map((root) => root.kind),
        [
          "inline-classic",
          "inline-module",
          "inline-data",
          "inline-importmap",
          "external-classic",
          "external-module",
          "modulepreload",
          "script-preload",
        ]
      )
      assert.equal(document.roots[0].sha256, digest(inlineClassic))
      assert.equal(document.roots[0].rawBytes, Buffer.byteLength(inlineClassic))
      assert.equal(document.roots[2].sha256, digest(inlineData))
      assert.deepEqual(document.roots[1].imports, [
        { kind: "static", assetPath: "assets/index-A.js" },
        { kind: "dynamic", assetPath: "static-shell-i18n.js" },
      ])
      assert.equal(document.roots[4].assetPath, "theme-init.js")
    }
  }, html)
})

test("AST edges exclude strings and comments while computed imports stay incomplete", async () => {
  const source = [
    'const text = "import(\\"https://example.invalid/' + privateCanary + '\\")";',
    '// import("/assets/fake-A.js")',
    'import("/assets/index-A.js");',
    "import(globalThis.hiddenPath);",
  ].join("\n")
  await withFixture(
    async (item) => {
      const value = receipt(inspect(item))
      for (const document of value.documents) {
        assert.equal(document.complete, false)
        assert.equal(document.issues.computedImports, 1)
        assert.equal(document.issues.foreignReferences, 0)
        assert.deepEqual(document.roots[0].imports, [
          { kind: "dynamic", assetPath: "assets/index-A.js" },
        ])
        assert.equal(document.roots[0].computedImports, 1)
        assert.equal(document.roots[0].parseErrors, 0)
      }
    },
    '<script type="module">' + source + "</script>"
  )
})

const incompleteCases = [
  [
    "foreign-script",
    '<script src="https://example.invalid/' + privateCanary + '"></script>',
    "foreignReferences",
  ],
  [
    "protocol-relative",
    '<script src="//example.invalid/' + privateCanary + '"></script>',
    "foreignReferences",
  ],
  [
    "data-script",
    '<script src="data:text/javascript,' + privateCanary + '"></script>',
    "unsafeReferences",
  ],
  ["traversal", '<script src="../' + privateCanary + '.js"></script>', "unsafeReferences"],
  [
    "encoded-traversal",
    '<script src="/assets/%2e%2e/' + privateCanary + '.js"></script>',
    "unsafeReferences",
  ],
  ["query", '<script src="/assets/index-A.js?' + privateCanary + '"></script>', "unsafeReferences"],
  [
    "foreign-import",
    '<script type="module">import("https://example.invalid/' + privateCanary + '")</script>',
    "foreignReferences",
  ],
  [
    "bare-import",
    '<script type="module">import("' + privateCanary + '")</script>',
    "unsafeReferences",
  ],
  ["base", '<base href="https://example.invalid/' + privateCanary + '">', "baseElements"],
  [
    "unknown-type",
    '<script type="private/' + privateCanary + '">hidden</script>',
    "unknownScriptTypes",
  ],
  ["invalid-js", '<script type="module">const = ' + privateCanary + "</script>", "parseErrors"],
]
for (const [name, extra, issue] of incompleteCases) {
  test("unknown final HTML form stays bounded and incomplete: " + name, async () => {
    await withFixture(async (item) => {
      receipt(inspect(item))
      await setHtml(item, basicHtml.replace("</head>", extra + "</head>"))
      const value = receipt(inspect(item))
      for (const document of value.documents) {
        assert.equal(document.complete, false)
        assert.equal(document.issues[issue], 1)
      }
      assert.equal(JSON.stringify(value).includes("example.invalid"), false)
    })
  })
}

const rejectedCases = [
  ["missing-shell", (item) => rm(path.join(item.clientDir, "_shell.html"))],
  ["missing-index", (item) => rm(path.join(item.clientDir, "index.html"))],
  ["missing-root-asset", (item) => rm(path.join(item.clientDir, "assets/index-A.js"))],
  [
    "html-symlink",
    async (item) => {
      const target = path.join(item.root, privateCanary + ".html")
      await writeFile(target, basicHtml)
      await rm(path.join(item.clientDir, "index.html"))
      await symlink(target, path.join(item.clientDir, "index.html"))
    },
  ],
  [
    "asset-symlink",
    async (item) => {
      const target = path.join(item.root, privateCanary + ".js")
      await writeFile(target, entry)
      await rm(path.join(item.clientDir, "assets/index-A.js"))
      await symlink(target, path.join(item.clientDir, "assets/index-A.js"))
    },
  ],
  [
    "asset-parent-symlink",
    async (item) => {
      const target = path.join(item.root, privateCanary)
      await mkdir(target)
      await writeFile(path.join(target, "index-A.js"), entry)
      await rm(path.join(item.clientDir, "assets"), { recursive: true })
      await symlink(target, path.join(item.clientDir, "assets"))
    },
  ],
  [
    "html-oversized",
    (item) => writeFile(path.join(item.clientDir, "index.html"), Buffer.alloc(1024 * 1024 + 1, 32)),
  ],
  [
    "asset-oversized",
    async (item) => {
      const source = "/*" + "x".repeat(4 * 1024 * 1024 - 4) + "*/"
      const asset = path.join(item.clientDir, "assets/index-A.js")
      await writeFile(asset, source)
      const control = receipt(inspect(item))
      assert.equal(control.documents[0].complete, true)
      assert.equal(control.documents[0].roots[0].rawBytes, 4 * 1024 * 1024)
      await writeFile(asset, source + " ")
    },
  ],
  [
    "html-invalid-utf8",
    (item) => writeFile(path.join(item.clientDir, "index.html"), Buffer.from([255])),
  ],
  [
    "asset-invalid-utf8",
    (item) => writeFile(path.join(item.clientDir, "assets/index-A.js"), Buffer.from([255])),
  ],
  [
    "too-many-roots",
    async (item) => {
      const tag = '<script type="module" src="/assets/index-A.js"></script>'
      const document = path.join(item.clientDir, "index.html")
      await writeFile(document, tag.repeat(128))
      const control = receipt(inspect(item))
      assert.equal(control.documents[0].roots.length, 1)
      assert.equal(control.documents[1].roots.length, 128)
      assert.equal(control.documents[1].complete, true)
      await writeFile(document, tag.repeat(129))
    },
  ],
  ["ast-node-cap", (item) => setHtml(item, "<script>" + "0;".repeat(60_000) + "</script>")],
  [
    "import-edge-cap",
    (item) =>
      setHtml(
        item,
        '<script type="module">' +
          Array.from(
            { length: 257 },
            (_, index) => 'import("/assets/probe-' + index + '.js");'
          ).join("") +
          "</script>"
      ),
  ],
  [
    "serialized-output-cap",
    async (item) => {
      const tags = []
      for (let index = 0; index < 128; index += 1) {
        const name = "probe-" + index + "-" + "x".repeat(180) + ".js"
        await writeFile(path.join(item.clientDir, "assets", name), "void 0;")
        tags.push('<script src="/assets/' + name + '"></script>')
      }
      await setHtml(item, tags.join(""))
    },
  ],
  [
    "total-asset-byte-cap",
    async (item) => {
      const source = "/*" + "x".repeat(4 * 1024 * 1024 - 4) + "*/"
      const tags = []
      for (let index = 0; index < 5; index += 1) {
        const name = "large-" + index + ".js"
        await writeFile(path.join(item.clientDir, "assets", name), source)
        tags.push('<script src="/assets/' + name + '"></script>')
        if (index === 3) {
          await setHtml(item, tags.join(""))
          const control = receipt(inspect(item))
          assert.equal(control.documentsMatch, true)
          for (const document of control.documents) {
            assert.equal(document.complete, true)
            assert.equal(document.roots.length, 4)
            assert.equal(
              document.roots.reduce((total, root) => total + root.rawBytes, 0),
              16 * 1024 * 1024
            )
          }
        }
      }
      await setHtml(item, tags.join(""))
    },
  ],
]
for (const [name, mutate] of rejectedCases) {
  test("invalid or excessive final HTML input returns only null: " + name, async () => {
    await withFixture(async (item) => {
      // The same real API must accept the control before a rejecting assertion.
      receipt(inspect(item))
      await mutate(item)
      assert.equal(inspect(item), null)
    })
  })
}

const captureWorkflowUrl = new URL(
  "../../.github/workflows/reusable-frontend-tests.yml",
  import.meta.url
)
const captureRepositoryUrl = new URL("../../", import.meta.url)
const captureStepName = "      - name: Capture bounded final HTML inventory\n"
const captureUploadName = "      - name: Upload final HTML inventory\n"
const capturePrefix = "FINAL_HTML_INVENTORY_CAPTURE "
const captureFailure = "FINAL_HTML_INVENTORY_CAPTURE_REJECTED\n"
const captureSourcePaths = [
  ".github/workflows/reusable-frontend-tests.yml",
  "frontend/package.json",
  "frontend/package-lock.json",
  "frontend/vite.config.mts",
  "frontend/scripts/final-html-root-inventory.mjs",
  "frontend/scripts/build-orchestrated.mjs",
  "frontend/scripts/post-build-shell.mjs",
]

function captureStep(workflow, name) {
  assert.equal(workflow.split(name).length, 2, "capture step must be uniquely wired")
  const start = workflow.indexOf(name)
  const end = workflow.indexOf("\n      - name:", start + name.length)
  assert.ok(end > start)
  return workflow.slice(start, end)
}

async function captureProgram() {
  const workflow = await readFile(captureWorkflowUrl, "utf8")
  const step = captureStep(workflow, captureStepName)
  const opening = "          node --input-type=module <<'FINAL_HTML_INVENTORY'\n"
  const closing = "          FINAL_HTML_INVENTORY"
  const start = step.indexOf(opening)
  const end = step.indexOf(closing, start + opening.length)
  assert.ok(start >= 0 && end > start)
  return step
    .slice(start + opening.length, end)
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => {
      assert.ok(line.startsWith("          "))
      return line.slice(10)
    })
    .join("\n")
}

async function captureFixture() {
  // Stay under frontend only so Node resolves the already-installed dependencies.
  // This owned temporary Git repository is always removed; no checkout is reused.
  const root = await mkdtemp(fileURLToPath(new URL("../.final-html-capture-", import.meta.url)))
  try {
    const frontend = path.join(root, "frontend")
    const clientDir = path.join(frontend, "dist", "client")
    const runnerTemp = path.join(root, "runner-temp")
    await mkdir(path.join(clientDir, "assets"), { recursive: true })
    await mkdir(runnerTemp)
    const fixtureEnv = {
      PATH: process.env.PATH ?? "",
      HOME: root,
      TMPDIR: runnerTemp,
      GIT_CONFIG_NOSYSTEM: "1",
      GIT_CONFIG_GLOBAL: "/dev/null",
      GIT_TERMINAL_PROMPT: "0",
    }
    for (const relative of captureSourcePaths) {
      const target = path.join(root, relative)
      await mkdir(path.dirname(target), { recursive: true })
      await writeFile(target, await readFile(new URL(relative, captureRepositoryUrl)))
    }
    const html = basicHtml.replace(
      "</head>",
      '<script type="application/json">' +
        JSON.stringify({ private: privateCanary }) +
        "</script></head>"
    )
    const asset = entry + "// " + privateCanary + "\n"
    await writeFile(path.join(clientDir, "assets/index-A.js"), asset)
    await writeFile(path.join(clientDir, "_shell.html"), html)
    await writeFile(path.join(clientDir, "index.html"), html)
    const git = (...args) =>
      execFileSync(
        "git",
        [
          "-c",
          "user.name=Inventory Fixture",
          "-c",
          "user.email=inventory@example.invalid",
          "-c",
          "commit.gpgsign=false",
          ...args,
        ],
        {
          cwd: root,
          env: fixtureEnv,
          encoding: "utf8",
          timeout: 5_000,
          maxBuffer: 4096,
          stdio: ["ignore", "pipe", "pipe"],
        }
      ).trim()
    git("init", "--quiet", "--initial-branch=egorribun")
    git("add", "--", ...captureSourcePaths)
    git("commit", "--quiet", "-m", "owned base")
    const baseSha = git("rev-parse", "HEAD")
    await writeFile(path.join(root, "fixture-head.txt"), "owned head\n")
    git("add", "--", "fixture-head.txt")
    git("commit", "--quiet", "-m", "owned head")
    const headSha = git("rev-parse", "HEAD")
    const treeSha = git("rev-parse", "HEAD^{tree}")
    const checkoutSha = git(
      "commit-tree",
      treeSha,
      "-p",
      baseSha,
      "-p",
      headSha,
      "-m",
      "owned merge"
    )
    git("update-ref", "HEAD", checkoutSha)
    const unrelatedSha = git("commit-tree", treeSha, "-m", "owned non-parent")
    const checkedSourceFiles = {}
    for (const relative of captureSourcePaths) {
      checkedSourceFiles[relative] = digest(await readFile(path.join(root, relative)))
    }
    const reportName = "final-html-inventory-1234-1-" + checkoutSha + ".json"
    return {
      root,
      frontend,
      clientDir,
      runnerTemp,
      reportName,
      reportPath: path.join(runnerTemp, reportName),
      checkoutSha,
      treeSha,
      baseSha,
      headSha,
      unrelatedSha,
      checkedSourceFiles,
      html,
      indexHtml: html,
      asset,
      env: {
        ...fixtureEnv,
        GITHUB_WORKSPACE: root,
        GITHUB_OUTPUT: path.join(root, "github-output"),
        GITHUB_SHA: checkoutSha,
        GITHUB_RUN_ID: "1234",
        GITHUB_RUN_ATTEMPT: "1",
        GITHUB_EVENT_NAME: "pull_request",
        FINAL_HTML_PR_HEAD_SHA: headSha,
        FINAL_HTML_PR_BASE_SHA: baseSha,
        RUNNER_TEMP: runnerTemp,
        VITE_LHCI: "",
        NODE_OPTIONS: "--max-old-space-size=512 --max-semi-space-size=16",
        FINAL_HTML_PRIVATE_CANARY: privateCanary,
      },
    }
  } catch (error) {
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

async function withCaptureFixture(run) {
  const item = await captureFixture()
  try {
    await run(item)
  } finally {
    await rm(item.root, { recursive: true, force: true })
  }
}

function runCapture(program, item) {
  // Covers ordinary Node/undici TCP paths, not a universal network sandbox.
  const guard = [
    'import net from "node:net"',
    'import tls from "node:tls"',
    "let captureNetworkAttempts = 0",
    "const blockCaptureNetwork = () => {",
    "  captureNetworkAttempts += 1",
    "  throw new Error('CAPTURE_NETWORK_DISABLED')",
    "}",
    "net.Socket.prototype.connect = blockCaptureNetwork",
    "tls.connect = blockCaptureNetwork",
    "globalThis.fetch = blockCaptureNetwork",
    "globalThis.WebSocket = blockCaptureNetwork",
  ].join("\n")
  const result = spawnSync(process.execPath, ["--input-type=module"], {
    cwd: item.frontend,
    input: guard + "\n" + program + "\nif (captureNetworkAttempts !== 0) process.exitCode = 97\n",
    env: item.env,
    encoding: "utf8",
    timeout: 10_000,
    maxBuffer: 65_537,
  })
  assert.equal(Boolean(result.error), false, "capture child must finish within its bound")
  for (const output of [result.stdout, result.stderr]) {
    assert.equal(output.includes(item.root), false, "capture must not disclose fixture paths")
    assert.equal(output.includes(privateCanary), false, "capture must not disclose input data")
    assert.equal(output.includes("<script"), false, "capture must not disclose HTML bodies")
  }
  assert.ok(Buffer.byteLength(result.stdout) <= 65_536)
  const heapMatch = /^FINAL_HTML_INVENTORY_HEAP_BYTES ([1-9][0-9]{0,15})\n/u.exec(result.stdout)
  assert.ok(heapMatch, "capture must emit a bounded heap integer before its guard")
  const heapBytes = Number(heapMatch[1])
  assert.ok(Number.isSafeInteger(heapBytes) && heapBytes > 0)
  const oversizedHeap =
    item.env.NODE_OPTIONS === "--max-old-space-size=1024 --max-semi-space-size=16"
  assert.equal(heapBytes > 640 * 1024 * 1024, oversizedHeap)
  return { ...result, stdout: result.stdout.slice(heapMatch[0].length) }
}

async function capturedReport(program, item) {
  const result = runCapture(program, item)
  assert.equal(result.status, 0, "valid owned capture must succeed")
  assert.equal(result.stderr === "", true, "capture must not print private failure details")
  assert.ok(result.stdout.startsWith(capturePrefix))
  assert.equal(result.stdout.trimEnd().split("\n").length, 1)
  assert.ok(Buffer.byteLength(result.stdout) <= 65_536)
  const logged = JSON.parse(result.stdout.slice(capturePrefix.length))
  assert.deepEqual(Object.keys(logged).sort(), ["report", "reportSha256"])
  const raw = await readFile(item.reportPath)
  assert.ok(raw.length <= 65_536)
  assert.equal(logged.reportSha256, digest(raw))
  assert.equal(raw.toString("utf8"), JSON.stringify(logged.report) + "\n")
  assert.equal((await lstat(item.reportPath)).mode & 0o777, 0o600)
  assert.deepEqual(await readdir(item.runnerTemp), [item.reportName])
  const report = logged.report
  assert.deepEqual(Object.keys(report).sort(), [
    "checkedSourceFiles",
    "checkout",
    "eventContext",
    "inventory",
    "kind",
    "profile",
    "relationship",
    "runContext",
    "schemaVersion",
    "toolchain",
  ])
  assert.equal(report.schemaVersion, 1)
  assert.equal(report.kind, "final-html-capture-diagnostic-not-admission")
  assert.equal(report.profile, "production-final-client")
  assert.deepEqual(report.checkout, {
    commitSha: item.checkoutSha,
    treeSha: item.treeSha,
    parentShas: [item.baseSha, item.headSha],
  })
  const isPr = item.env.GITHUB_EVENT_NAME === "pull_request"
  assert.deepEqual(report.eventContext, {
    eventName: item.env.GITHUB_EVENT_NAME,
    githubSha: item.checkoutSha,
    prHeadSha: isPr ? item.headSha : null,
    prBaseSha: isPr ? item.baseSha : null,
  })
  assert.equal(report.relationship, isPr ? "merge-parents-match-event-context" : "checkout-only")
  assert.deepEqual(report.runContext, { runId: "1234", runAttempt: "1" })
  assert.deepEqual(report.checkedSourceFiles, item.checkedSourceFiles)
  assert.deepEqual(report.toolchain, { jsdom: "30.1.3", babelParser: "8.0.7" })
  const inventory = receipt(report.inventory)
  assert.ok(Buffer.byteLength(JSON.stringify(inventory)) <= 32_767)
  assert.equal(inventory.documentsMatch, item.html === item.indexHtml)
  for (const document of inventory.documents) {
    const html = document.fileName === "_shell.html" ? item.html : item.indexHtml
    assert.equal(document.sha256, digest(html))
    assert.equal(document.rawBytes, Buffer.byteLength(html))
    assert.equal(document.roots[0].sha256, digest(item.asset))
    assert.equal(document.roots[0].rawBytes, Buffer.byteLength(item.asset))
  }
  assert.equal(await readFile(path.join(item.clientDir, "_shell.html"), "utf8"), item.html)
  assert.equal(await readFile(path.join(item.clientDir, "index.html"), "utf8"), item.indexHtml)
  return report
}

test("final HTML capture preserves production ordering and separate artifacts", async () => {
  const workflow = await readFile(captureWorkflowUrl, "utf8")
  const step = captureStep(workflow, captureStepName)
  const upload = captureStep(workflow, captureUploadName)
  const build = workflow.indexOf("  build:\n")
  const buildApp = workflow.indexOf("      - name: Build app\n", build)
  const map = workflow.indexOf("      - name: Report bounded MapLibre build inventory\n", build)
  const capture = workflow.indexOf(captureStepName)
  const diagnostic = workflow.indexOf(captureUploadName)
  const production = workflow.indexOf("      - name: Upload production bundle\n", build)
  const lighthouse = workflow.indexOf("      - name: Build Lighthouse bundle\n", build)
  assert.ok(build >= 0 && buildApp > build && map > buildApp)
  assert.ok(capture > map && diagnostic > capture)
  assert.ok(production > diagnostic && lighthouse > production)
  assert.match(step, /^\s+id: capture-final-html-inventory$/mu)
  assert.match(step, /^\s+timeout-minutes: 1$/mu)
  assert.match(
    step,
    /^\s+NODE_OPTIONS: "--max-old-space-size=512 --max-semi-space-size=16"$/mu
  )
  assert.doesNotMatch(step + upload, /continue-on-error|permissions:|^\s+if:/mu)
  const expression = (value) => "$" + "{{ " + value + " }}"
  assert.ok(
    step.includes(
      "FINAL_HTML_PR_HEAD_SHA: " + expression("github.event.pull_request.head.sha || ''")
    )
  )
  assert.ok(
    step.includes(
      "FINAL_HTML_PR_BASE_SHA: " + expression("github.event.pull_request.base.sha || ''")
    )
  )
  assert.match(upload, /^\s+id: upload-final-html-inventory$/mu)
  const suffix =
    expression("github.run_id") +
    "-" +
    expression("github.run_attempt") +
    "-" +
    expression("github.sha")
  assert.ok(upload.includes("name: frontend-final-html-inventory-" + suffix + "\n"))
  assert.ok(
    upload.includes(
      "path: " + expression("runner.temp") + "/final-html-inventory-" + suffix + ".json\n"
    )
  )
  assert.match(upload, /^\s+if-no-files-found: error$/mu)
  assert.match(upload, /^\s+retention-days: 1$/mu)
  assert.doesNotMatch(upload, /include-hidden-files|overwrite:|frontend-dist|\/dist/u)
  const bundleUpload = workflow.slice(production, lighthouse)
  const actionPin = /^\s+uses: (actions\/upload-artifact@[a-f0-9]{40})(?: #.*)?$/mu
  const productionAction = actionPin.exec(bundleUpload)?.[1]
  assert.ok(productionAction, "existing producer must retain its policy-validated full action pin")
  assert.equal(actionPin.exec(upload)?.[1], productionAction)
  assert.ok(bundleUpload.includes("name: frontend-dist\n"))
  assert.ok(bundleUpload.includes("path: " + expression("inputs.working-directory") + "/dist\n"))
  const selector = "run: node --test scripts/final-html-root-inventory.test.mjs"
  assert.equal(workflow.split(selector).length, 2)
  const selectorAt = workflow.indexOf(selector)
  assert.ok(selectorAt > workflow.indexOf("      - name: Run quick audit regressions\n"))
  assert.ok(selectorAt < workflow.indexOf("  unit-tests-shard:\n"))
})

test("capture wrapper binds owned source context and keeps failures closed", async () => {
  const program = await captureProgram()
  // These controls must all pass before any rejecting assertion is reachable.
  await withCaptureFixture(async (item) => {
    const report = await capturedReport(program, item)
    assert.equal(
      report.inventory.documents.every((document) => document.complete),
      true
    )
  })
  await withCaptureFixture(async (item) => {
    item.html = item.html.replace(
      "</head>",
      '<script src="https://example.invalid/' + privateCanary + '"></script></head>'
    )
    await writeFile(path.join(item.clientDir, "_shell.html"), item.html)
    const report = await capturedReport(program, item)
    assert.equal(report.inventory.documentsMatch, false)
    assert.equal(report.inventory.documents[0].complete, false)
    assert.equal(report.inventory.documents[0].issues.foreignReferences, 1)
    assert.equal(report.inventory.documents[1].complete, true)
    assert.equal(report.inventory.documents[1].issues.foreignReferences, 0)
  })
  await withCaptureFixture(async (item) => {
    item.env.GITHUB_EVENT_NAME = "push"
    item.env.FINAL_HTML_PR_HEAD_SHA = ""
    item.env.FINAL_HTML_PR_BASE_SHA = ""
    await capturedReport(program, item)
  })
  const cases = [
    [
      "wrong-checkout",
      (item) => {
        item.env.GITHUB_SHA = "0".repeat(40)
      },
    ],
    [
      "wrong-pr-head",
      (item) => {
        item.env.FINAL_HTML_PR_HEAD_SHA = item.unrelatedSha
      },
    ],
    [
      "wrong-pr-base",
      (item) => {
        item.env.FINAL_HTML_PR_BASE_SHA = item.unrelatedSha
      },
    ],
    [
      "bad-run-id",
      (item) => {
        item.env.GITHUB_RUN_ID = "0"
      },
    ],
    [
      "bad-attempt",
      (item) => {
        item.env.GITHUB_RUN_ATTEMPT = "01"
      },
    ],
    [
      "unknown-event",
      (item) => {
        item.env.GITHUB_EVENT_NAME = privateCanary
      },
    ],
    [
      "lighthouse-profile",
      (item) => {
        item.env.VITE_LHCI = "true"
      },
    ],
    [
      "changed-inspector",
      async (item) => {
        const file = path.join(item.frontend, "scripts", "final-html-root-inventory.mjs")
        await writeFile(file, (await readFile(file, "utf8")) + "// " + privateCanary + "\n")
      },
    ],
    ["missing-final-index", (item) => rm(path.join(item.clientDir, "index.html"))],
    [
      "temporary-output-inside-dist",
      async (item) => {
        item.env.RUNNER_TEMP = path.join(item.clientDir, "private-temp")
        await mkdir(item.env.RUNNER_TEMP)
      },
    ],
    [
      "temporary-output-symlink",
      async (item) => {
        const alias = path.join(item.root, "private-temp-alias")
        await symlink(item.runnerTemp, alias)
        item.env.RUNNER_TEMP = alias
      },
    ],
    ["existing-output", (item) => writeFile(item.reportPath, privateCanary)],
    [
      "symlink-output",
      async (item) => {
        const target = path.join(item.root, "private-output")
        await writeFile(target, privateCanary)
        await symlink(target, item.reportPath)
      },
    ],
    [
      "oversized-heap",
      (item) => {
        item.env.NODE_OPTIONS = "--max-old-space-size=1024 --max-semi-space-size=16"
      },
    ],
  ]
  for (const [name, mutate] of cases) {
    await withCaptureFixture(async (item) => {
      await mutate(item)
      const before = await readdir(item.runnerTemp)
      const oldOutput = before.length ? await readFile(item.reportPath) : null
      const oldStat = before.length ? await lstat(item.reportPath) : null
      const result = runCapture(program, item)
      assert.equal(result.status, 1, "invalid capture must fail closed: " + name)
      assert.equal(result.stdout, "")
      assert.equal(result.stderr === captureFailure, true, "capture uses one fixed failure token")
      assert.deepEqual(await readdir(item.runnerTemp), before)
      if (oldOutput !== null) {
        assert.equal((await readFile(item.reportPath)).equals(oldOutput), true)
        const nextStat = await lstat(item.reportPath)
        for (const key of ["dev", "ino", "mode", "size", "mtimeMs", "ctimeMs"]) {
          assert.equal(nextStat[key], oldStat[key])
        }
      }
      if (name === "temporary-output-inside-dist") {
        assert.deepEqual(await readdir(item.env.RUNNER_TEMP), [])
      }
    })
  }
})
