import assert from "node:assert/strict"
import { fileURLToPath } from "node:url"
import test from "node:test"

import { JSDOM, VirtualConsole } from "jsdom"
import { createServer } from "vite"

const frontendRoot = fileURLToPath(new URL("../", import.meta.url))

test("the test CSS pipeline compiles Tailwind into a stylesheet JSDOM can parse", async () => {
  const previousEnvironment = process.env.NODE_ENV
  const previousDirectory = process.cwd()
  let server
  let dom
  try {
    // Match npm's frontend working directory: Tailwind's default candidate
    // scanner uses process.cwd(), not Vite's configured root.
    process.chdir(frontendRoot)
    process.env.NODE_ENV = "test"
    server = await createServer({
      root: frontendRoot,
      configFile: fileURLToPath(new URL("../vitest.config.ts", import.meta.url)),
      configLoader: "runner",
      server: { middlewareMode: true },
      optimizeDeps: { noDiscovery: true },
    })
    const transformed = await server.transformRequest("/src/styles/tailwind.css")
    const payload = transformed?.code.match(/const __vite__css = ("(?:[^"\\]|\\.)*")/u)
    assert.ok(payload, "Vite must expose the compiled stylesheet, not an empty CSS mock")
    const css = JSON.parse(payload[1])
    assert.doesNotMatch(css, /@(?:theme|apply)\b/u, "Tailwind directives must be compiled")

    const diagnostics = []
    const virtualConsole = new VirtualConsole()
    virtualConsole.on("jsdomError", (error) => {
      diagnostics.push({
        type: error.type,
        message: error.message,
        cause: error.cause?.formattedMessage ?? error.cause?.message,
      })
    })
    dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", {
      virtualConsole,
    })
    const style = dom.window.document.createElement("style")
    style.textContent = css
    dom.window.document.head.append(style)
    assert.deepEqual(diagnostics, [], "The real compiled stylesheet must parse without errors")
    assert.ok(style.sheet?.cssRules.length > 0, "The CSS pipeline must retain real style rules")
  } finally {
    try {
      dom?.window.close()
    } finally {
      try {
        await server?.close()
      } finally {
        if (previousEnvironment === undefined) delete process.env.NODE_ENV
        else process.env.NODE_ENV = previousEnvironment
        process.chdir(previousDirectory)
      }
    }
  }
})
