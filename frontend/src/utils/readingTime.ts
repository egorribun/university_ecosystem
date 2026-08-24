/**
 * Estimate reading time in minutes from text content.
 * Strips HTML tags before counting words. Returns null for empty content.
 * Average reading speed: 220 words/min (accommodates multilingual text).
 */
export function estimateReadingTime(content: string): number | null {
  const text = content
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
  if (!text) return null
  const words = text.split(/\s+/).filter(Boolean).length
  return Math.max(1, Math.round(words / 220))
}
