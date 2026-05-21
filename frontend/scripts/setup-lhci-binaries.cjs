#!/usr/bin/env node
"use strict"

const fs = require("node:fs/promises")
const path = require("node:path")

const frontendDir = path.join(__dirname, "..")
const binDir = path.join(frontendDir, "node_modules", ".bin")
const lhciUtilsDir = path.join(frontendDir, "node_modules", "@lhci", "utils")
const lhciNamespaceDir = path.join(frontendDir, "node_modules", "@lhci")
const rootConfig = path.join(frontendDir, "..", ".lighthouserc.js")
const workspaceConfig = path.join(frontendDir, "..", "..", ".lighthouserc.js")
const wrapper = path.join(__dirname, "google-chrome-stable.cjs")
const localCandidates = ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"]
const globalCandidates = [
  "/usr/bin/google-chrome-stable",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
]

async function ensureLocalSymlink(targetName) {
  const destination = path.join(binDir, targetName)
  try {
    const existing = await fs.readlink(destination)
    if (existing === wrapper) {
      return
    }
    await fs.unlink(destination)
  } catch (error) {
    if (error && error.code !== "ENOENT") {
      throw error
    }
  }

  await fs.symlink(wrapper, destination)
}

async function ensureGlobalSymlink(targetPath) {
  // Skip global symlinks on Windows - these are Unix-specific paths
  if (process.platform === "win32") {
    return
  }

  try {
    const stats = await fs.lstat(targetPath)
    if (!stats.isSymbolicLink()) {
      return
    }

    const existing = await fs.readlink(targetPath)
    if (existing === wrapper) {
      return
    }

    return
  } catch (error) {
    if (!error || error.code !== "ENOENT") {
      return
    }
  }

  try {
    await fs.symlink(wrapper, targetPath)
  } catch (error) {
    if (!error) {
      return
    }

    if (error.code === "EEXIST" || error.code === "EACCES" || error.code === "EPERM") {
      return
    }

    throw error
  }
}

async function ensureConfigSymlink(sourcePath, destinationDir) {
  if (!sourcePath) {
    return
  }

  try {
    await fs.access(sourcePath)
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return
    }
    throw error
  }

  await fs.mkdir(destinationDir, { recursive: true })
  const destination = path.join(destinationDir, ".lighthouserc.js")
  const relative = path.relative(destinationDir, sourcePath)

  try {
    const current = await fs.readlink(destination)
    if (current === relative) {
      return
    }
    await fs.unlink(destination)
  } catch (error) {
    if (error && error.code !== "EINVAL" && error.code !== "ENOENT") {
      throw error
    }
    if (error && error.code === "EINVAL") {
      // A regular file already exists; avoid overwriting user-provided configs.
      return
    }
  }

  await fs.symlink(relative, destination)
}

async function ensureWrapperExecutable() {
  // Ensure the wrapper script itself is executable on Unix systems
  if (process.platform !== "win32") {
    try {
      await fs.chmod(wrapper, 0o755)
    } catch (error) {
      // Ignore errors if we can't set permissions (e.g. read-only filesystem)
      console.warn(`Warning: Could not set executable permissions on ${wrapper}:`, error.message)
    }
  }
}

async function main() {
  await ensureWrapperExecutable()
  await fs.mkdir(binDir, { recursive: true })
  await Promise.all(localCandidates.map(ensureLocalSymlink))
  await Promise.all(globalCandidates.map(ensureGlobalSymlink))
  await ensureConfigSymlink(rootConfig, lhciUtilsDir)
  await ensureConfigSymlink(workspaceConfig, lhciNamespaceDir)
}

main().catch((error) => {
  const message =
    error && typeof error === "object" && "message" in error ? error.message : String(error)
  console.error("Failed to set up Lighthouse Chromium wrapper binaries:", message)
  process.exit(1)
})
