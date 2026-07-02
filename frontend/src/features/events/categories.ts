/**
 * Event type category system.
 * Unlike News (which infers from text), Events uses the explicit
 * `event_type` / `event_type_en` field from the API.
 * We map those values to color-coded categories.
 */

export type EventCategory =
  "lecture" | "seminar" | "conference" | "workshop" | "social" | "sport" | "other"

type CategoryRule = {
  id: EventCategory
  /** i18n key for display label */
  labelKey: string
  /** CSS color token name (maps to --cat-{color}-bg / --cat-{color}-text) */
  color: string
  /** Keyword patterns to match event_type field (case-insensitive) */
  patterns: RegExp
}

const RULES: CategoryRule[] = [
  {
    id: "lecture",
    labelKey: "events:categories.lecture",
    color: "blue",
    patterns: /лекци|lecture|занят|class|lesson/i,
  },
  {
    id: "seminar",
    labelKey: "events:categories.seminar",
    color: "purple",
    patterns: /семинар|seminar|коллоквиум|colloquium|круглый.?стол|round.?table/i,
  },
  {
    id: "conference",
    labelKey: "events:categories.conference",
    color: "amber",
    patterns: /конференц|conference|форум|forum|саммит|summit|симпозиум|symposium/i,
  },
  {
    id: "workshop",
    labelKey: "events:categories.workshop",
    color: "emerald",
    patterns: /мастер.?класс|workshop|тренинг|training|воркшоп|практикум|practicum/i,
  },
  {
    id: "social",
    labelKey: "events:categories.social",
    color: "sky",
    patterns:
      /встреча|meetup|вечер|party|концерт|concert|фестиваль|festival|выставка|exhibition|праздник|celebration/i,
  },
  {
    id: "sport",
    labelKey: "events:categories.sport",
    color: "rose",
    patterns:
      /спорт|sport|футбол|football|баскетбол|basketball|турнир|tournament|соревнован|competition|забег|race/i,
  },
]

const FALLBACK: CategoryRule = {
  id: "other",
  labelKey: "events:categories.other",
  color: "slate",
  patterns: /./,
}

/** Infer category from event_type string */
export function inferEventCategory(eventType: string | null | undefined): EventCategory {
  if (!eventType) return FALLBACK.id
  const text = eventType.toLowerCase()
  for (const rule of RULES) {
    if (rule.patterns.test(text)) return rule.id
  }
  return FALLBACK.id
}

/** Get display metadata for a category */
export function getCategoryMeta(category: EventCategory) {
  const rule = RULES.find((r) => r.id === category) ?? FALLBACK
  return { labelKey: rule.labelKey, color: rule.color }
}

/** All available categories for filter UI */
export const ALL_EVENT_CATEGORIES: { id: EventCategory; labelKey: string; color: string }[] = [
  ...RULES.map((r) => ({ id: r.id, labelKey: r.labelKey, color: r.color })),
  { id: FALLBACK.id, labelKey: FALLBACK.labelKey, color: FALLBACK.color },
]
