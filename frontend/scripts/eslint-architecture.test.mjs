import assert from "node:assert/strict"
import { createRequire } from "node:module"
import path from "node:path"
import test, { after } from "node:test"
import { fileURLToPath } from "node:url"

import { ESLint } from "eslint"

const frontendRoot = fileURLToPath(new URL("..", import.meta.url))
const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url))
const originalCwd = process.cwd()
const require = createRequire(import.meta.url)
const aliasResolver = require("./eslint-import-resolver-alias.cjs")

process.chdir(repositoryRoot)
after(() => process.chdir(originalCwd))

async function lintMessages(source, virtualPath) {
  const eslint = new ESLint({ cwd: frontendRoot })
  const [result] = await eslint.lintText(source, {
    filePath: fileURLToPath(new URL(virtualPath, new URL("../", import.meta.url))),
  })

  return result.messages
}

async function boundaryMessages(source, virtualPath) {
  return (await lintMessages(source, virtualPath)).filter(
    ({ ruleId }) => ruleId === "boundaries/dependencies"
  )
}

test("shared alias imports cannot cross into feature or app layers", async () => {
  const featureMessages = await boundaryMessages(
    'import "@/features/index"\n',
    "src/components/__architecture_fixture__.ts"
  )
  const appMessages = await boundaryMessages(
    'import "@/app/telemetry"\n',
    "src/components/__architecture_fixture__.ts"
  )

  assert.equal(featureMessages.length, 1)
  assert.equal(appMessages.length, 1)
})

test("feature alias imports cannot cross into page or app layers", async () => {
  const pageMessages = await boundaryMessages(
    'import "@/pages/Dashboard"\n',
    "src/features/__architecture_fixture__.ts"
  )
  const appMessages = await boundaryMessages(
    'import "@/app/telemetry"\n',
    "src/features/__architecture_fixture__.ts"
  )

  assert.equal(pageMessages.length, 1)
  assert.equal(appMessages.length, 1)
})

test("shared alias imports remain allowed within the shared layer", async () => {
  const messages = await boundaryMessages(
    'import "@/components/Button"\n',
    "src/components/__architecture_fixture__.ts"
  )

  assert.deepEqual(messages, [])
})

test("cross-cutting platform APIs remain available below the app composition layer", async () => {
  const sharedMessages = await boundaryMessages(
    'import "@/app/logger"\n',
    "src/components/__architecture_fixture__.ts"
  )
  const featureMessages = await boundaryMessages(
    'import "@/app/logger"\n',
    "src/features/__architecture_fixture__.ts"
  )

  assert.deepEqual(sharedMessages, [])
  assert.deepEqual(featureMessages, [])
})

test("feature UI cannot cross into page or app composition layers", async () => {
  const pageMessages = await boundaryMessages(
    'import "@/pages/Dashboard"\n',
    "src/components/events/__architecture_fixture__.ts"
  )
  const appMessages = await boundaryMessages(
    'import "@/app/telemetry"\n',
    "src/components/events/__architecture_fixture__.ts"
  )
  const platformMessages = await boundaryMessages(
    'import "@/app/logger"\n',
    "src/components/events/__architecture_fixture__.ts"
  )

  assert.equal(pageMessages.length, 1)
  assert.equal(appMessages.length, 1)
  assert.deepEqual(platformMessages, [])
})

test("alias resolution is independent of the process working directory", () => {
  const result = aliasResolver.resolve("@/features/index", import.meta.filename, {
    alias: "@",
    target: path.join(frontendRoot, "src"),
  })

  assert.equal(path.resolve(process.cwd()), path.resolve(repositoryRoot))
  assert.equal(result.found, true)
  assert.equal(result.path, path.join(frontendRoot, "src", "features", "index.ts"))
})

test("alias traversal is unresolved and remains a lint violation", async () => {
  const result = aliasResolver.resolve("@/../package.json", import.meta.filename, {
    alias: "@",
    target: path.join(frontendRoot, "src"),
  })
  const messages = await lintMessages(
    'import "@/../package.json"\n',
    "src/components/events/__architecture_fixture__.ts"
  )

  assert.deepEqual(result, { found: false })
  assert.equal(messages.some(({ ruleId }) => ruleId === "no-restricted-imports"), true)
})
