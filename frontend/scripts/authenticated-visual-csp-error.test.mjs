import test from "node:test"
import assert from "node:assert/strict"
import {
  emitAuthenticatedVisualRuntimeDiagnostics,
  summarizeAuthenticatedVisualDiagnostics,
} from "./authenticated-visual-audit.mjs"

const cases = [
  ["inline_script", "Executing inline script"],
  ["script_resource", "Loading the script"],
  ["inline_style", "Applying inline style"],
  ["style_resource", "Loading the stylesheet"],
  ["eval", "Evaluating a string as JavaScript"],
  ["trusted_type_policy", "Creating a TrustedTypePolicy"],
  ["trusted_type_sink", "This document requires 'TrustedHTML' assignment"],
  ["connection", "Connecting to a resource"],
  ["other", "Unknown operation"],
]
const privateMarker = "private-marker https://private.invalid/?nonce=private-nonce"
function summary(messages) {
  return summarizeAuthenticatedVisualDiagnostics({ consoleMessages: messages })
}
function emit(diagnostics) {
  const lines = []
  emitAuthenticatedVisualRuntimeDiagnostics(
    "/dashboard",
    { locale: "en", theme: "dark", width: 390 },
    diagnostics,
    (line) => lines.push(line)
  )
  return lines
}
for (const [kind, message] of cases) {
  test(`closed CSP error category: ${kind}`, () => {
    const diagnostics = summary([
      { type: "error", text: `${message}: Content Security Policy ${privateMarker}` },
    ])
    assert.equal(diagnostics.cspErrorKindCounts[kind], 1)
    assert.equal(diagnostics.consoleErrorClassCounts.content_security_policy, 1)
    const lines = emit(diagnostics)
    assert.equal(lines.length, 1)
    assert.ok(lines[0].length <= 4096)
    for (const forbidden of ["private-marker", "private.invalid", "private-nonce"]) {
      assert.equal(lines[0].includes(forbidden), false)
    }
  })
}
test("only error/pageerror CSP messages enter the new counts", () => {
  const text = "Executing inline script: Content Security Policy"
  const diagnostics = summary([
    { type: "info", text },
    { type: "warning", text },
    { type: "error", text: "Executing inline script unrelated" },
    { type: "pageerror", text },
  ])
  assert.equal(diagnostics.cspErrorKindCounts.inline_script, 1)
  assert.equal(diagnostics.consoleErrorClassCounts.content_security_policy, 1)
})
test("closed count projection stays bounded and rejects invalid counts", () => {
  const diagnostics = summary(
    Array(10001).fill({ type: "error", text: "Executing inline script Content Security Policy" })
  )
  assert.equal(diagnostics.capped, true)
  assert.equal(diagnostics.cspErrorKindCounts.inline_script, 9999)
  diagnostics.cspErrorKindCounts.private = privateMarker
  assert.equal(emit(diagnostics)[0].includes(privateMarker), false)
  for (const invalid of [-1, 10000, Infinity, NaN, "1"]) {
    diagnostics.cspErrorKindCounts.inline_script = invalid
    assert.equal(emit(diagnostics).length, 0)
  }
})
test("throwing output sink is contained without exposing the error", () => {
  assert.doesNotThrow(() => {
    emitAuthenticatedVisualRuntimeDiagnostics("/dashboard", {}, summary([]), () => {
      throw new Error(privateMarker)
    })
  })
})
