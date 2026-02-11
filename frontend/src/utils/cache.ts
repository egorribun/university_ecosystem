/**
 * Parses a cache version from a number or string input.
 * Handles numeric timestamps and string dates.
 */
export function parseCacheVersion(input: unknown): number | undefined {
  if (typeof input === "number" && Number.isFinite(input)) return input
  if (typeof input === "string") {
    const numeric = Number(input)
    if (!Number.isNaN(numeric)) return numeric
    const parsed = Date.parse(input)
    if (!Number.isNaN(parsed)) return parsed
  }
  return undefined
}
