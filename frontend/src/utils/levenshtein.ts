/**
 * Compute the Levenshtein (edit) distance between two strings.
 * Used for fuzzy-matching email domain typos against a known list.
 */
export function levenshtein(a: string, b: string): number {
  const m = a.length
  const n = b.length
  if (!m) return n
  if (!n) return m

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0) as number[])
  for (let i = 0; i <= m; i++) dp[i]![0] = i
  for (let j = 0; j <= n; j++) dp[0]![j] = j

  for (let i = 1; i <= m; i++) {
    const row = dp[i]!
    const prevRow = dp[i - 1]!
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      row[j] = Math.min(prevRow[j]! + 1, row[j - 1]! + 1, prevRow[j - 1]! + cost)
    }
  }
  return dp[m]![n]!
}
