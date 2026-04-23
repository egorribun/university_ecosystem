/**
 * Shared localization utility for bilingual fields (RU primary, EN optional).
 * Eliminates duplicated pattern in NewsCard, NewsDetail, RelatedCard, etc.
 */
export function localizeField(
  primary: string,
  english: string | null | undefined,
  language: string
): string {
  const en = english ?? ""
  if (language === "en" && en.trim()) return en
  return primary || en
}
