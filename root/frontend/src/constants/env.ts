const sanitize = (value: unknown): string | null => {
  if (typeof value !== "string") return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

export const getMapConstructorId = (): string | null =>
  sanitize(import.meta.env.VITE_MAP_CONSTRUCTOR_ID)
