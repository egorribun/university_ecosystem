#!/usr/bin/env node
"use strict"

const fs = require("node:fs")
const path = require("node:path")
const { spawn, spawnSync } = require("node:child_process")

const frontendDir = path.join(__dirname, "..")

const runPlaywright = (args) => {
  const cliPath = (() => {
    try {
      return require.resolve("playwright/cli", { paths: [frontendDir] })
    } catch (error) {
      return null
    }
  })()

  if (!cliPath) {
    return { status: 1 }
  }

  return spawnSync(process.execPath, [cliPath, ...args], {
    cwd: frontendDir,
    stdio: "inherit",
    env: process.env,
  })
}

const resolveChromiumExecutable = () => {
  try {
    const playwrightPath = require.resolve("playwright", { paths: [frontendDir] })
    const { chromium } = require(playwrightPath)
    const executable = chromium.executablePath()

    if (fs.existsSync(executable)) {
      return executable
    }

    let installDeps = runPlaywright(["install-deps", "chromium"])
    if (installDeps.status !== 0) {
      installDeps = spawnSync("npx", ["playwright", "install-deps", "chromium"], {
        cwd: frontendDir,
        stdio: "inherit",
        env: process.env,
      })
    }

    let installResult = runPlaywright(["install", "chromium"])
    if (installResult.status !== 0) {
      installResult = spawnSync("npx", ["playwright", "install", "chromium"], {
        cwd: frontendDir,
        stdio: "inherit",
        env: process.env,
      })

      if (installResult.status !== 0) {
        console.error(
          "Unable to locate the Playwright Chromium binary required for Lighthouse runs."
        )
        console.error(
          "Attempted to install it automatically via `playwright install chromium`, but the command failed."
        )
        process.exit(1)
      }
    }

    if (fs.existsSync(executable)) {
      return executable
    }

    console.error("Playwright installation completed but Chromium executable was still not found.")
    console.error("Please rerun `npx playwright install chromium` manually and try again.")
    process.exit(1)
  } catch (error) {
    const message =
      error && typeof error === "object" && "message" in error ? error.message : String(error)
    console.error("Unable to locate the Playwright Chromium binary required for Lighthouse runs.")
    console.error("Install it locally by running `npx playwright install chromium` and try again.")
    console.error(message)
    process.exit(1)
  }
}

const chromeExecutable = resolveChromiumExecutable()

const child = spawn(chromeExecutable, process.argv.slice(2), {
  stdio: "inherit",
  env: process.env,
})

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
    return
  }
  process.exit(code ?? 0)
})

child.on("error", (error) => {
  const message =
    error && typeof error === "object" && "message" in error ? error.message : String(error)
  console.error("Failed to launch Chromium through Playwright:", message)
  process.exit(1)
})
