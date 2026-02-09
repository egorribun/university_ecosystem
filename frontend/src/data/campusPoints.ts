export type CampusPointId = "main" | "library" | "sports" | "dormitory" | "cafeteria"
export type CampusPointTag = "services" | "study" | "events" | "sports" | "housing" | "food"

export type CampusPointEntry = {
  id: CampusPointId
  title: string
  description: string
  address: string
  tags: CampusPointTag[]
}

const FALLBACK_LOCALE = "en"

const localeDataModules = import.meta.glob<{ default: CampusPointEntry[] }>(
  "../i18n/locales/*/campus-points.json",
  {
    eager: true,
  }
)

const localePattern = /locales\/([^/]+)\/campus-points\.json$/

const campusPointsByLocale = Object.entries(localeDataModules).reduce(
  (acc, [path, module]) => {
    const match = path.match(localePattern)
    if (!match) {
      return acc
    }

    acc[match[1]] = module.default
    return acc
  },
  {} as Record<string, CampusPointEntry[]>
)

export const availableCampusPointLocales = Object.freeze(
  Object.keys(campusPointsByLocale)
) as readonly string[]

const getCandidateLocales = (locale?: string) => {
  const candidates: string[] = []
  if (locale) {
    const normalized = locale.toLowerCase()
    candidates.push(normalized)

    const short = normalized.split("-")[0]
    if (short && short !== normalized) {
      candidates.push(short)
    }
  }

  candidates.push(FALLBACK_LOCALE)
  return candidates
}

export function getCampusPointsForLocale(locale?: string) {
  for (const candidate of getCandidateLocales(locale)) {
    const dataset = campusPointsByLocale[candidate]
    if (dataset) {
      return dataset
    }
  }

  return []
}




