import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"

import { ESLint } from "eslint"

const frontendRoot = fileURLToPath(new URL("..", import.meta.url))

async function boundaryMessages(source, virtualPath) {
  const eslint = new ESLint({ cwd: frontendRoot })
  const [result] = await eslint.lintText(source, {
    filePath: fileURLToPath(new URL(virtualPath, new URL("../", import.meta.url))),
  })

  return result.messages.filter(({ ruleId }) => ruleId === "boundaries/dependencies")
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
