import assert from "node:assert/strict"
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { spawnSync } from "node:child_process"
import test from "node:test"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const validatorPath = path.join(__dirname, "validate-css-token-closure.mjs")

function runValidator(root) {
  return spawnSync(process.execPath, [validatorPath, "--root", root], {
    cwd: path.join(__dirname, ".."),
    encoding: "utf8",
  })
}

function withFixture(files, callback) {
  const root = mkdtempSync(path.join(tmpdir(), "css-token-closure-"))
  try {
    for (const [relativePath, content] of Object.entries(files)) {
      const filePath = path.join(root, relativePath)
      mkdirSync(path.dirname(filePath), { recursive: true })
      writeFileSync(filePath, content, "utf8")
    }
    callback(root)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

test("rejects unresolved CSS and Tailwind arbitrary custom-property references", () => {
  withFixture(
    {
      "styles.css": [
        ":root { --known: #fff; }",
        ".card { color: var(--missing-css); background: var(--optional, var(--missing-nested)); }",
      ].join("\n"),
      "Component.tsx": 'export const x = <div className="bg-(--missing-class)" />',
    },
    (root) => {
      const result = runValidator(root)
      assert.notEqual(result.status, 0)
      assert.match(`${result.stdout}\n${result.stderr}`, /--missing-css/)
      assert.match(`${result.stdout}\n${result.stderr}`, /--missing-class/)
      assert.match(`${result.stdout}\n${result.stderr}`, /--missing-nested/)
    }
  )
})

test("accepts global definitions, safe fallbacks, inline definitions, and private local tokens", () => {
  withFixture(
    {
      "styles.css": [
        ":root { --known: #fff; }",
        ".card { color: var(--known); background: var(--optional, var(--known)); }",
        ".pin { --_pin-color: #fff; color: var(--_pin-color); }",
      ].join("\n"),
      "Component.tsx": [
        'const style = { "--component-accent": "#fff" } as React.CSSProperties',
        'export const x = <div style={style} className="text-(--component-accent)" />',
      ].join("\n"),
    },
    (root) => {
      const result = runValidator(root)
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
    }
  )
})

test("the frontend source custom-property graph is closed", () => {
  const result = runValidator(path.join(__dirname, "../src"))
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
})
