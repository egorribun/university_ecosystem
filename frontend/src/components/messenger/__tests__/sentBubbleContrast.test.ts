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
const tailwind = readFileSync(resolve(process.cwd(), "src/styles/tailwind.css"), "utf8")

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

const sentGradientStops = () => {
  const gradient = messenger.match(/--messenger-bubble-sent-bg:\s*([^;]+);/)?.[1] ?? ""
  return [...gradient.matchAll(/var\(--(color-[a-z0-9-]+)\)/g)].map((match) => match[1]!)
}

const parseWhiteOverlayPercent = (value: string) => {
  const normalized = value.trim()
  const prefix = "color-mix(in srgb, white "
  const suffix = "%, transparent)"
  if (!normalized.startsWith(prefix) || !normalized.endsWith(suffix)) {
    throw new Error("value is not a supported white alpha veil")
  }

  const percent = normalized.slice(prefix.length, normalized.length - suffix.length)
  const [whole, fraction, ...extra] = percent.split(".")
  const isDigits = (part: string | undefined) =>
    part !== undefined &&
    part.length > 0 &&
    [...part].every((digit) => digit >= "0" && digit <= "9")
  if (!isDigits(whole) || (fraction !== undefined && !isDigits(fraction)) || extra.length > 0) {
    throw new Error("value is not a supported white alpha veil")
  }

  const numericPercent = Number(percent)
  if (!Number.isFinite(numericPercent) || numericPercent < 0 || numericPercent > 100) {
    throw new Error("white alpha veil percent must be finite and between 0 and 100")
  }
  return numericPercent / 100
}

const whiteOverlayPercent = (tokenName: string) => {
  const declaration = messenger.split("\n").find((line) => line.trim().startsWith(tokenName + ":"))
  if (!declaration) throw new Error(tokenName + " is missing")
  let value = declaration.slice(declaration.indexOf(":") + 1).trim()
  if (value.endsWith(";")) value = value.slice(0, -1).trim()
  return parseWhiteOverlayPercent(value)
}

const primitiveNumber = (tokenName: string) => {
  const declaration = primitives
    .split("\n")
    .find((line) => line.trim().startsWith("--" + tokenName + ":"))
  const value = declaration?.split(":")[1]?.replace(";", "").trim()
  const number = Number(value)
  if (!Number.isFinite(number)) throw new Error(tokenName + " is not a numeric primitive")
  return number
}

const mixWithWhite = (hex: string, alpha: number) => {
  const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16))
  const blended = channels.map((channel) => Math.round(channel + (255 - channel) * alpha))
  return "#" + blended.map((channel) => channel.toString(16).padStart(2, "0")).join("")
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

  it("uses the AA-safe bubble gradient for white-labeled send buttons", () => {
    const buttonRule = messenger.match(/\.messenger-send-btn\s*\{([^}]*)\}/)?.[1] ?? ""
    const sendBackground = buttonRule.match(/background:\s*([^;]+);/)?.[1]?.trim() ?? ""
    expect(sendBackground).toBe("var(--messenger-bubble-sent-bg)")
    const sharedSendBackground =
      messenger
        .match(/--messenger-send-bg:\s*([^;]+);/)?.[1]
        ?.replace(/\s+/g, " ")
        .trim() ?? ""
    const expectedSharedSendBackground = [
      "linear-gradient(",
      "135deg,",
      "var(--color-violet-500) 0%,",
      "var(--color-violet-400) 50%,",
      "var(--color-pink-400) 100%",
      ")",
    ].join(" ")
    expect(sharedSendBackground).toBe(expectedSharedSendBackground)
    expect(buttonRule).toMatch(/color:\s*var\(--color-white\)/)

    for (const stop of sentGradientStops()) {
      expect(contrast(primitiveHex("color-white"), primitiveHex(stop))).toBeGreaterThanOrEqual(4.5)
    }
  })

  it("rejects malformed and out-of-range white overlay declarations", () => {
    expect(() => parseWhiteOverlayPercent("color-mix(in srgb, #ffffff 94%, white 6% )")).toThrow()
    expect(() => parseWhiteOverlayPercent("color-mix(in srgb, white 101%, transparent)")).toThrow()

    const overflowPercent = "9".repeat(400)
    expect(() =>
      parseWhiteOverlayPercent(`color-mix(in srgb, white ${overflowPercent}%, transparent)`)
    ).toThrow()
  })

  it("keeps white sent text at AA over the reply and attachment veils", () => {
    const stops = sentGradientStops()
    expect(stops.length).toBeGreaterThanOrEqual(2)
    const veils = [
      whiteOverlayPercent("--messenger-attachment-bg"),
      whiteOverlayPercent("--messenger-attachment-bg-hover"),
      primitiveNumber("opacity-faint"),
    ]

    for (const stop of stops) {
      const base = primitiveHex(stop)
      for (const veil of veils) {
        expect(
          contrast(primitiveHex("color-white"), mixWithWhite(base, veil))
        ).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it("keeps sent text and action glyphs above their contrast floors after opacity", () => {
    expect(tailwind).toMatch(/@utility opacity-hover\s*\{\s*opacity:\s*var\(--opacity-hover\);/)
    const white = primitiveHex("color-white")
    const iconOpacity = primitiveNumber("opacity-hover")
    const stops = sentGradientStops()
    expect(stops.length).toBeGreaterThanOrEqual(2)

    for (const stop of stops) {
      const background = primitiveHex(stop)
      expect(contrast(white, background)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(mixWithWhite(background, iconOpacity), background)).toBeGreaterThanOrEqual(3)
    }
  })

  it("pins the sent bubble text token to white in both themes", () => {
    expect(messenger).toMatch(
      /\.messenger-bubble-sent\s*\{[^}]*--text-inverse:\s*var\(--color-white\)/
    )
  })
})
