import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import {
  createRandom,
  generateText,
  runFuzzCampaign,
  sanitizedMarkupViolation,
  wasmArtifactProblem,
} from "../../../scripts/wasm-fuzzer.mjs"

/**
 * AUD-416: the WASM fuzzer must never report success for artifacts it did not
 * exercise. These checks run the shipped script without the compiled modules.
 */
describe("wasm fuzzer artifact gate", () => {
  let dir: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "wasm-fuzz-"))
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it("classifies an absent artifact as missing", () => {
    expect(wasmArtifactProblem(join(dir, "absent.wasm"))).toBe("missing")
  })

  it("rejects a placeholder-sized artifact", () => {
    const path = join(dir, "placeholder.wasm")
    writeFileSync(path, Buffer.alloc(64))
    expect(wasmArtifactProblem(path)).toBe("placeholder-sized")
  })

  it("rejects a large file that does not start with the WebAssembly header", () => {
    const path = join(dir, "text.wasm")
    writeFileSync(path, Buffer.alloc(2048, 0x41))
    expect(wasmArtifactProblem(path)).toBe("invalid-magic")
  })

  it("accepts a module-sized file with the WebAssembly header", () => {
    const path = join(dir, "module.wasm")
    writeFileSync(path, Buffer.concat([Buffer.from([0x00, 0x61, 0x73, 0x6d]), Buffer.alloc(2000)]))
    expect(wasmArtifactProblem(path)).toBeNull()
  })

  it("fails closed instead of passing when the artifacts are placeholders", async () => {
    const path = join(dir, "placeholder.wasm")
    writeFileSync(path, Buffer.alloc(64))

    const result = await runFuzzCampaign({ sanitizerPath: path, cryptoPath: path, iterations: 1 })

    expect(result.ok).toBe(false)
    expect(result.executed).toBe(0)
    expect(result.failures).toHaveLength(2)
  })

  it("fails closed when an artifact is missing", async () => {
    const result = await runFuzzCampaign({
      sanitizerPath: join(dir, "absent.wasm"),
      cryptoPath: join(dir, "absent.wasm"),
      iterations: 1,
    })

    expect(result.ok).toBe(false)
    expect(result.failures[0]).toContain("missing")
  })
})

describe("wasm fuzzer oracles and generators", () => {
  it("flags script elements and event-handler attributes left in sanitizer output", () => {
    expect(sanitizedMarkupViolation("<p>safe</p>")).toBeNull()
    expect(sanitizedMarkupViolation("<script>alert(1)</script>")).toBe("kept a script element")
    expect(sanitizedMarkupViolation('<img src="x" onerror=alert(1)>')).toBe(
      "kept an event-handler attribute"
    )
    expect(sanitizedMarkupViolation(42)).toBe("returned number")
  })

  it("replays the same text from the same seed and keeps every string valid UTF-16", () => {
    const first = generateText(createRandom(7))
    expect(generateText(createRandom(7))).toBe(first)
    expect(Buffer.from(first, "utf8").toString("utf8")).toBe(first)
  })

  it("produces different text for different seeds", () => {
    expect(generateText(createRandom(7))).not.toBe(generateText(createRandom(8)))
  })
})
