import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * AUD-073 contrast contract: the sent bubble's white text must reach WCAG AA
 * (4.5:1) on every colour stop of its gradient. Values are read from the real
 * token files so a palette or gradient change cannot silently regress it.
 */
const primitives = readFileSync(resolve(process.cwd(), "src/styles/tokens/primitives.css"), "utf8")
const messenger = readFileSync(resolve(process.cwd(), "src/styles/tokens/messenger.css"), "utf8")

const toLinear = (channel: number) => {
  const value = channel / 255
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

const luminance = (hex: string) => {
  const [r = 0, g = 0, b = 0] = [1, 3, 5].map((offset) =>
    parseInt(hex.slice(offset, offset + 2), 16)
  )
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}

const contrast = (foreground: string, background: string) => {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a) as [
    number,
    number,
  ]
  return (light + 0.05) / (dark + 0.05)
}

const primitiveHex = (name: string) => {
  const declaration = primitives.split("\n").find((line) => line.trim().startsWith(`--${name}:`))
  const hex = declaration?.match(/#[0-9a-fA-F]{6}\b/)?.[0]
  if (!hex) throw new Error(`primitive ${name} is not a 6-digit hex colour`)
  return hex
}

describe("sent message bubble contrast", () => {
  it("keeps white text at WCAG AA on every colour stop of the sent gradient", () => {
    const gradient = messenger.match(/--messenger-bubble-sent-bg:\s*([^;]+);/)?.[1] ?? ""
    const stops = [...gradient.matchAll(/var\(--(color-[a-z0-9-]+)\)/g)].map((match) => match[1]!)
    expect(stops.length).toBeGreaterThanOrEqual(2)

    for (const stop of stops) {
      expect(contrast(primitiveHex("color-white"), primitiveHex(stop))).toBeGreaterThanOrEqual(4.5)
    }
  })

  it("pins the sent bubble text token to white in both themes", () => {
    expect(messenger).toMatch(
      /\.messenger-bubble-sent\s*\{[^}]*--text-inverse:\s*var\(--color-white\)/
    )
  })
})
