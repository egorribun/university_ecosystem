import { describe, expect, it } from "vitest"
import { getStrictConsoleDiagnostics, withExpectedConsole } from "./strictConsole"

describe("strict console integrity", () => {
  it("does not silently discard an unexpected React-like warning", () => {
    expect(() => console.error("Warning: unexpected diagnostic")).toThrow(
      /Unexpected console\.error call/
    )
  })

  it("scopes intentional diagnostics and removes the expectation afterwards", async () => {
    const before = getStrictConsoleDiagnostics().length
    await withExpectedConsole("warn", "intentional diagnostic", () => {
      console.warn("intentional diagnostic", { owner: "strict-console-test" })
    })

    const diagnostics = getStrictConsoleDiagnostics()
    expect(diagnostics).toHaveLength(before + 1)
    expect(diagnostics.at(-1)).toMatchObject({
      method: "warn",
      args: ["intentional diagnostic", { owner: "strict-console-test" }],
    })
    expect(() => console.warn("unexpected after scope")).toThrow(/Unexpected console\.warn call/)
  })
})
