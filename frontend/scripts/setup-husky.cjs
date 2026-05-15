#!/usr/bin/env node
// W156 SW4 Tier 2 — set git's core.hooksPath to repo-root .husky directory.
//
// Replaces the broken `husky ../.husky` invocation in package.json's `prepare`
// script (husky v9+ safety check rejects parent-directory paths, returning
// `.. not allowed` and exiting nonzero — silently disabled all pre-commit
// hooks pre-W156, contributing to anti-pattern #15 prettier-drift recurrence
// across W149+W150+W153+W154+W155).
//
// This script computes the absolute path to `<repo>/.husky/` (from this
// file's location at `frontend/scripts/setup-husky.cjs`) and runs
// `git config --local core.hooksPath` so the hooks fire on commit + push.
//
// Safe to call from any cwd: child_process spawns git with explicit cwd.
// Idempotent: re-running with same path is a no-op for git.
// Skips gracefully if not in a git repo OR git binary unavailable (logs
// warning to stderr but exits zero — `npm install` should not fail just
// because hooks couldn't be configured).

const { execSync } = require("node:child_process")
const path = require("node:path")
const fs = require("node:fs")

const repoRoot = path.resolve(__dirname, "..", "..")
const huskyDir = path.join(repoRoot, ".husky")
const gitDir = path.join(repoRoot, ".git")

if (!fs.existsSync(gitDir)) {
  // Not a git repo — likely npm pack / npm publish / Docker build context where
  // .git/ was excluded. Silent skip.
  process.exit(0)
}

if (!fs.existsSync(huskyDir)) {
  console.warn(
    `[setup-husky] Skipping: ${huskyDir} does not exist. Run after .husky/ is provisioned.`
  )
  process.exit(0)
}

try {
  execSync(`git config --local core.hooksPath ".husky"`, {
    cwd: repoRoot,
    stdio: "inherit",
  })
} catch (error) {
  // Git not available OR config write failed — log but don't fail npm install.
  console.warn(
    `[setup-husky] Failed to set core.hooksPath. Run manually from repo root: ` +
      `git config --local core.hooksPath .husky\n${error.message ?? error}`
  )
  process.exit(0)
}
