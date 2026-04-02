/**
 * News category inference system.
 * Since the API has no `category` field, we derive categories
 * from title + content keywords on the frontend.
 */

export type NewsCategory = "education" | "sport" | "science" | "events" | "campus" | "general"

type CategoryRule = {
  id: NewsCategory
  /** i18n key for display label */
  labelKey: string
  /** CSS color token (maps to Tailwind) */
  color: string
  /** Keyword patterns (case-insensitive) */
  patterns: RegExp
}

const RULES: CategoryRule[] = [
  {
    id: "education",
    labelKey: "news:categories.education",
    color: "blue",
    patterns:
      /учеб|лекци|семинар|экзамен|зачёт|зачет|сессия|диплом|курсов|расписан|education|lecture|exam|semester|diploma|schedule|стипенди|scholarship/i,
  },
  {
    id: "sport",
    labelKey: "news:categories.sport",
    color: "emerald",
    patterns:
      /спорт|футбол|баскетбол|волейбол|плавани|шахмат|турнир|соревнован|sport|football|basketball|swimming|tournament|competition|секци/i,
  },
  {
    id: "science",
    labelKey: "news:categories.science",
    color: "purple",
    patterns:
      /наук|исследован|конференц|публикаци|science|research|conference|publication|лаборатор|laboratory|диссертац|thesis/i,
  },
  {
    id: "events",
    labelKey: "news:categories.events",
    color: "amber",
    patterns:
      /мероприят|событи|праздник|концерт|фестивал|выставк|event|festival|exhibition|concert|хакатон|hackathon|форум|forum|день открыт|open.?day/i,
  },
  {
    id: "campus",
    labelKey: "news:categories.campus",
    color: "sky",
    patterns:
      /кампус|общежити|столов|библиотек|campus|dormitor|library|canteen|ремонт|renovation|wi.?fi|инфраструктур/i,
  },
]

const FALLBACK: CategoryRule = {
  id: "general",
  labelKey: "news:categories.general",
  color: "slate",
  patterns: /./,
}

/** Infer category from news title + content */
export function inferCategory(title: string, content: string): NewsCategory {
  const text = `${title} ${content}`.toLowerCase()
  for (const rule of RULES) {
    if (rule.patterns.test(text)) return rule.id
  }
  return FALLBACK.id
}

/** Get display metadata for a category */
export function getCategoryMeta(category: NewsCategory) {
  const rule = RULES.find((r) => r.id === category) ?? FALLBACK
  return { labelKey: rule.labelKey, color: rule.color }
}

/** All available categories for filter UI */
export const ALL_CATEGORIES: { id: NewsCategory; labelKey: string; color: string }[] = [
  ...RULES.map((r) => ({ id: r.id, labelKey: r.labelKey, color: r.color })),
  { id: FALLBACK.id, labelKey: FALLBACK.labelKey, color: FALLBACK.color },
]
