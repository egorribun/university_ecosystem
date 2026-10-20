import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import path from "node:path"
import test, { after } from "node:test"
import { fileURLToPath } from "node:url"

import { ESLint } from "eslint"
import { format, resolveConfig } from "prettier"

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
  assert.equal(
    messages.some(({ ruleId }) => ruleId === "no-restricted-imports"),
    true
  )
})

test("UI barrel imports are rejected while exact leaf imports remain allowed", async () => {
  const barrelMessages = await lintMessages(
    'import "@/components/ui"\n',
    "src/components/__architecture_fixture__.ts"
  )
  const explicitIndexMessages = await lintMessages(
    'import "@/components/ui/index"\n',
    "src/components/__architecture_fixture__.ts"
  )
  const leafMessages = await lintMessages(
    'import "@/components/ui/Button"\n',
    "src/components/__architecture_fixture__.ts"
  )

  assert.equal(
    barrelMessages.some(({ ruleId }) => ruleId === "no-restricted-imports"),
    true
  )
  assert.equal(
    explicitIndexMessages.some(({ ruleId }) => ruleId === "no-restricted-imports"),
    true
  )
  assert.equal(
    leafMessages.some(({ ruleId }) => ruleId === "no-restricted-imports"),
    false
  )
})

test("alias resolution rejects a lexical in-root path whose realpath escapes", () => {
  const target = path.join(frontendRoot, "src")
  const lexicalPath = path.join(target, "features", "index.ts")
  const escapedRealPath = path.join(frontendRoot, "package.json")
  const resolve = aliasResolver.createResolver({
    realpathSync(candidate) {
      if (path.resolve(candidate) === path.resolve(target)) {
        return target
      }

      assert.equal(path.resolve(candidate), path.resolve(lexicalPath))
      return escapedRealPath
    },
  })

  const result = resolve("@/features/index", import.meta.filename, {
    alias: "@",
    target,
  })

  assert.deepEqual(result, { found: false })
})

for (const componentPath of [
  "src/components/layout/Footer.tsx",
  "src/components/layout/MobileBottomNav.tsx",
  "src/components/navbar/Navbar.tsx",
]) {
  test(`${componentPath} warns about untranslated JSX text`, async () => {
    const messages = await lintMessages(
      "export function Fixture() { return <span>Untranslated navigation</span> }\n",
      componentPath
    )

    const warnings = messages.filter(({ ruleId }) => ruleId === "i18next/no-literal-string")
    assert.equal(
      messages.some(({ fatal }) => fatal),
      false
    )
    assert.deepEqual(
      warnings.map(({ severity }) => severity),
      [1]
    )
  })

  test(`${componentPath} preserves translated text and existing exemptions`, async () => {
    const messages = await lintMessages(
      [
        'import { Trans } from "react-i18next"',
        "export function Fixture({ t }: { t: (key: string) => string }) {",
        "  return <>",
        '    <span>{t("navigation.home")}</span>',
        '    <Trans i18nKey="navigation.home">Navigation home</Trans>',
        '    <span className="navigation" data-testid="navigation" aria-label="Navigation" />',
        "  </>",
        "}",
        "",
      ].join("\n"),
      componentPath
    )

    const warnings = messages.filter(({ ruleId }) => ruleId === "i18next/no-literal-string")
    assert.equal(
      messages.some(({ fatal }) => fatal),
      false
    )
    assert.deepEqual(warnings, [])
  })

  test(`${componentPath} keeps test fixtures exempt from translation warnings`, async () => {
    const messages = await lintMessages(
      "export function Fixture() { return <span>Untranslated test fixture</span> }\n",
      componentPath.replace(/\.tsx$/, ".test.tsx")
    )

    const warnings = messages.filter(({ ruleId }) => ruleId === "i18next/no-literal-string")
    assert.equal(
      messages.some(({ fatal }) => fatal),
      false
    )
    assert.deepEqual(warnings, [])
  })
}

test("temporary news fixture formatter diagnostic", { timeout: 10_000 }, async (t) => {
  const fixture = "src/components/news/__tests__/NewsDetailEditDialog.mutation-contract.test.tsx"
  const filepath = fileURLToPath(new URL("../" + fixture, import.meta.url))
  let source
  let formatted

  try {
    source = await readFile(filepath, "utf8")
    const options = await resolveConfig(filepath, { editorconfig: true })
    assert.ok(options)
    formatted = await format(source, { ...options, filepath })
  } catch {
    assert.fail("Unable to prepare the fixed news fixture formatting diagnostic")
  }

  if (source !== formatted) {
    const diagnostic = JSON.stringify({
      fixture: "frontend/" + fixture,
      formatted,
    })
    assert.ok(
      new TextEncoder().encode(diagnostic).byteLength < 65_536,
      "Fixed news fixture formatting diagnostic exceeds its output limit"
    )
    t.diagnostic(diagnostic)
    assert.fail("News fixture differs from installed Prettier output")
  }
})
