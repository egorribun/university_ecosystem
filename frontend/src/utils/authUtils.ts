import { levenshtein } from "./levenshtein"

export const COMMON_EMAIL_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "icloud.com",
  "mail.ru",
  "bk.ru",
  "list.ru",
  "inbox.ru",
  "yandex.ru",
  "yandex.com",
  "rambler.ru",
  "proton.me",
] as const

export function suggestEmailDomain(email: string) {
  const atIndex = email.indexOf("@")
  if (atIndex < 0) return null

  const localPart = email.slice(0, atIndex).trim()
  const domain = email
    .slice(atIndex + 1)
    .trim()
    .toLowerCase()

  if (!localPart || !domain) return null
  if ((COMMON_EMAIL_DOMAINS as ReadonlyArray<string>).includes(domain)) return null

  let bestMatch: { domain: string; distance: number } | null = null
  for (const candidate of COMMON_EMAIL_DOMAINS) {
    const distance = levenshtein(domain, candidate)
    if (distance <= 2 && (!bestMatch || distance < bestMatch.distance)) {
      bestMatch = { domain: candidate, distance }
    }
  }
  return bestMatch ? `${localPart}@${bestMatch.domain}` : null
}
