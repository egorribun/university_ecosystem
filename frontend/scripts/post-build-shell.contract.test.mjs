import assert from "node:assert/strict"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { spawnSync } from "node:child_process"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const scriptPath = fileURLToPath(new URL("./post-build-shell.mjs", import.meta.url))
const shellHtml = "<html><head></head><body><main>test shell</main></body></html>"

async function writeShell(root, relativePath) {
  const shellPath = path.join(root, relativePath)
  await mkdir(path.dirname(shellPath), { recursive: true })
  await writeFile(shellPath, shellHtml, "utf8")
  return shellPath
}

function runPostBuildShell(cwd) {
  const result = spawnSync(process.execPath, [scriptPath], {
    cwd,
    encoding: "utf8",
    env: { ...process.env, VITE_LHCI: "false" },
  })
  assert.equal(result.error, undefined, result.error?.message)
  assert.equal(result.status, 0, result.stderr)
  return result.stdout
}

test("post-build processes the current dist/client shell ahead of stale Nitro output", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "post-build-shell-precedence-"))
  try {
    const staleShell = await writeShell(temporaryRoot, ".output/public/_shell.html")
    const currentShell = await writeShell(temporaryRoot, "dist/client/_shell.html")

    const output = runPostBuildShell(temporaryRoot)

    assert.match(output, /dist[\\/]client[\\/]_shell\.html/u)
    assert.match(await readFile(currentShell, "utf8"), /data-render-mode="static-spa"/u)
    assert.equal(await readFile(staleShell, "utf8"), shellHtml)
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true })
  }
})

test("post-build retains the Nitro shell fallback when no current Vite shell exists", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "post-build-shell-fallback-"))
  try {
    const fallbackShell = await writeShell(temporaryRoot, ".output/public/_shell.html")

    const output = runPostBuildShell(temporaryRoot)

    assert.match(output, /\.output[\\/]public[\\/]_shell\.html/u)
    assert.match(await readFile(fallbackShell, "utf8"), /data-render-mode="static-spa"/u)
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true })
  }
})
