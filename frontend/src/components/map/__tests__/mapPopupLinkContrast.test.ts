import { readFileSync } from "node:fs"
import postcss, { type Root } from "postcss"
import { describe, expect, it } from "vitest"

function readTokens(file: string) {
  return postcss.parse(readFileSync(`src/styles/tokens/${file}.css`, "utf8"))
}

function declarations(sheet: Root, selector: string | RegExp) {
  const values = new Map<string, string>()
  sheet.walkRules(selector, (rule) => {
    rule.walkDecls((declaration) => {
      values.set(declaration.prop, declaration.value)
    })
  })
  return values
}

type Rgb = [number, number, number]

function mix(first: Rgb, second: Rgb, fraction: number): Rgb {
  const channel = (index: 0 | 1 | 2) => first[index] * fraction + second[index] * (1 - fraction)
  return [channel(0), channel(1), channel(2)]
}

function resolveColor(value: string, tokens: ReadonlyMap<string, string>): Rgb {
  if (/^#[0-9a-f]{6}$/i.test(value)) {
    const channel = (offset: number) => Number.parseInt(value.slice(offset, offset + 2), 16)
    return [channel(1), channel(3), channel(5)]
  }
  if (value.startsWith("var(") && value.endsWith(")")) {
    const inner = value.slice(4, -1)
    const comma = inner.indexOf(",")
    const name = (comma === -1 ? inner : inner.slice(0, comma)).trim()
    const fallback = comma === -1 ? "" : inner.slice(comma + 1).trim()
    return resolveColor(tokens.get(name) ?? fallback, tokens)
  }

  const blend = /^color-mix\(in srgb, (var\(--[\w-]+\)) (\d+)%, (var\(--[\w-]+\)) (\d+)%\)$/.exec(
    value
  )
  const [, first, firstPercent, second, secondPercent] = blend ?? []
  if (first && second && Number(firstPercent) + Number(secondPercent) === 100) {
    return mix(
      resolveColor(first, tokens),
      resolveColor(second, tokens),
      Number(firstPercent) / 100
    )
  }
  throw new Error(`Unsupported opaque CSS color: "${value}"`)
}

function luminance([red, green, blue]: Rgb): number {
  const linear = (channel: number) => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
}

const primitives = readTokens("primitives")
const semantics = readTokens("semantics")
const map = readTokens("map")
const link = declarations(map, ".map-popup-link")
const hover = declarations(map, ".map-popup-link:hover")
const content = declarations(map, /^\.(?:map-theme|map-popup-premium) \.maplibregl-popup-content$/)

const tailwind = postcss.parse(readFileSync("src/styles/tailwind.css", "utf8"))
const aliases = new Map<string, string>()
tailwind.walkAtRules("theme", (theme) => {
  theme.walkDecls((declaration) => {
    aliases.set(declaration.prop, declaration.value)
  })
})

function contrast(foreground: Rgb, background: Rgb, opacity = 1): number {
  const text = luminance(mix(foreground, background, opacity))
  const surface = luminance(background)
  return (Math.max(text, surface) + 0.05) / (Math.min(text, surface) + 0.05)
}

describe.each(["light", "dark"])("map popup contrast in %s mode", (theme) => {
  const tokens = new Map([
    ...declarations(primitives, ":root"),
    ...declarations(semantics, ":root"),
    ...(theme === "dark" ? declarations(semantics, ".dark") : []),
    ...declarations(map, ".map-theme"),
    ...(theme === "dark" ? declarations(map, ".dark .map-theme") : []),
    ...aliases,
  ])
  const background = resolveColor(content.get("background") ?? "", tokens)

  it.each(["resting", "hovered"])("keeps links at least 4.5:1 when %s", (state) => {
    const style = new Map([...link, ...(state === "hovered" ? hover : [])])
    const foreground = resolveColor(style.get("color") ?? "", tokens)
    const opacity = Number(style.get("opacity") ?? "1")
    expect(contrast(foreground, background, opacity)).toBeGreaterThanOrEqual(4.5)
  })

  it("keeps secondary metadata at least 4.5:1", () => {
    const foreground = resolveColor("var(--color-text-secondary)", tokens)
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5)
  })
})
