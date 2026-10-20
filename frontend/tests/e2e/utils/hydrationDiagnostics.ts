export function isHydrationDiagnostic(message: string, includeMismatch = false): boolean {
  const normalized = message.toLowerCase()
  return (
    normalized.includes("hydration") ||
    (includeMismatch && normalized.includes("did not match"))
  )
}
