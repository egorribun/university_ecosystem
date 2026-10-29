import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { spawnSync } from "node:child_process"
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

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
