import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises"
import path from "node:path"
import { tmpdir } from "node:os"
import test from "node:test"
import { fileURLToPath } from "node:url"

const frontend = fileURLToPath(new URL("../", import.meta.url))
const expected = [
  "--experimental-test-coverage",
  "--test-coverage-include=scripts/aud375-evidence.mjs",
  "--test-coverage-lines=100",
  "--test-coverage-branches=100",
  "--test-coverage-functions=100",
  "--test",
  "scripts/aud375-evidence.test.mjs",
]

test("the actual PR-wide command rejects an uncovered helper branch and a missing include", async (t) => {
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url)))
  const [coverageCommand, ...rest] = packageJson.scripts["test:wasm"].split(" && ")
  assert.deepEqual(coverageCommand.split(" "), ["node", ...expected])
  assert.match(rest.join(" && "), /^node --test scripts\/aud375-coverage\.contract\.test\.mjs /u)
  const root = await mkdtemp(path.join(tmpdir(), "aud375-coverage-mutation-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const target = path.join(root, "frontend")
  await mkdir(path.join(target, "scripts"), { recursive: true })
  await mkdir(path.join(root, ".github/workflows"), { recursive: true })
  for (const file of [
    "package.json",
    "scripts/aud375-evidence.mjs",
    "scripts/aud375-evidence.test.mjs",
  ]) {
    await writeFile(path.join(target, file), await readFile(path.join(frontend, file)))
  }
  for (const workflow of ["reusable-e2e-tests.yml", "nightly-full-gate.yml"]) {
    await writeFile(
      path.join(root, ".github/workflows", workflow),
      await readFile(new URL(`../../.github/workflows/${workflow}`, import.meta.url))
    )
  }
  await symlink(path.join(frontend, "node_modules"), path.join(target, "node_modules"), "junction")
  const run = (args) =>
    spawnSync(process.execPath, args, {
      cwd: target,
      env: { PATH: process.env.PATH, HOME: root, CI: "true" },
      encoding: "utf8",
      timeout: 120_000,
      maxBuffer: 4 * 1024 * 1024,
    })
  // A byte-identical positive mirror establishes that the negative is caused
  // by the added branch, not broken fixture setup. Production coverage itself
  // is measured separately against the real helper by the preceding command.
  const positive = run(expected)
  assert.equal(positive.status, 0, positive.stderr + positive.stdout)
  const helper = path.join(target, "scripts/aud375-evidence.mjs")
  const original = await readFile(helper, "utf8")
  await writeFile(
    helper,
    original +
      "\nexport function uncoveredBranchForNegativeControl(value) {\n  if (value) return 1\n  return 0\n}\n"
  )
  const negative = run(expected)
  assert.equal(negative.status, 1, negative.stderr + negative.stdout)
  assert.match(negative.stdout + negative.stderr, /does not meet threshold of 100/u)
  assert.match(negative.stdout + negative.stderr, /fail 0/u)
  await writeFile(helper, original)
  const missing = run(
    expected.map((arg) =>
      arg.startsWith("--test-coverage-include=")
        ? "--test-coverage-include=scripts/nonexistent.mjs"
        : arg
    )
  )
  assert.equal(missing.status, 1, "an empty coverage denominator must not pass")
  assert.match(missing.stdout + missing.stderr, /coverage gate includes these exact helper bytes/u)
})
