/**
 * Compute the Levenshtein (edit) distance between two strings.
 * Used for fuzzy-matching email domain typos against a known list.
 */
export function levenshtein(a: string, b: string): number {
  // One DP row over b's characters. Iterating characters instead of index
  // counters leaves no loop a mutation could make endless, and empty inputs
  // fall out of the table itself.
  const bChars = [...b]
  let previous = bChars.map((_, j) => j + 1)
  previous.unshift(0)
  for (const [i, charA] of [...a].entries()) {
    const current = [i + 1]
    for (const [j, charB] of bChars.entries()) {
      const cost = charA === charB ? 0 : 1
      current.push(Math.min(previous[j + 1]! + 1, current[j]! + 1, previous[j]! + cost))
    }
    previous = current
  }
  return previous[bChars.length]!
}
