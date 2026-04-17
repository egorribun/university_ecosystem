const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

const toHex = (value: number) => value.toString(16).padStart(2, "0")

const expandHex = (hex: string) =>
  hex.length === 3
    ? hex
        .split("")
        .map((char) => char + char)
        .join("")
    : hex

const mixChannelWithWhite = (channel: number, coefficient: number) =>
  Math.round(channel + (255 - channel) * coefficient)

const fromHex = (hex: string) => Number.parseInt(hex, 16)

const tryMixHexWithWhite = (color: string, coefficient: number): string | null => {
  const hexMatch = /^#?([\da-f]{3}|[\da-f]{6})$/i.exec(color)
  if (!hexMatch) return null
  const normalized = expandHex(hexMatch[1]!)
  const r = mixChannelWithWhite(fromHex(normalized.slice(0, 2)), coefficient)
  const g = mixChannelWithWhite(fromHex(normalized.slice(2, 4)), coefficient)
  const b = mixChannelWithWhite(fromHex(normalized.slice(4, 6)), coefficient)
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

const buildColorMixExpression = (color: string, coefficient: number) => {
  const percentage = Math.round(coefficient * 1000) / 10
  const base = Math.max(0, 100 - percentage)
  return `color-mix(in srgb, ${color} ${base}%, white ${percentage}%)`
}

export const mixColorWithWhite = (color: string, coefficient: number) => {
  const clamped = clamp(coefficient, 0, 1)
  const trimmed = color.trim()

  if (typeof CSS !== "undefined" && typeof CSS.supports === "function") {
    const expression = buildColorMixExpression(trimmed, clamped)
    if (CSS.supports("color", expression)) {
      return expression
    }
  }

  return tryMixHexWithWhite(trimmed, clamped) ?? trimmed
}

export const lightenColor = mixColorWithWhite
