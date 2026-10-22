export function isHydrationDiagnostic(message: string, includeMismatch = false): boolean {
  const normalized = message.toLowerCase()
  if (normalized.includes("hydration")) return true
  if (includeMismatch && normalized.includes("did not match")) return true
  return /\bminified react error #(418|423|425)\b/u.test(normalized)
}
