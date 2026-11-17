import { useMemo } from "react"
import { useCachedRelatedLists } from "./useCachedRelatedLists"
import { isCurrentBrowserSession } from "@/stores/sessionEpoch"
import type { Event } from "@/types/Event"
import { inferEventCategory, type EventCategory } from "@/features/events/categories"

/**
 * Returns related events from the cached query data.
 * Filters by matching event category (inferred from event_type),
 * excluding current event. Falls back to recent events if not enough
 * same-category matches.
 *
 * Pattern source: hooks/useRelatedNews.ts
 */
export function useRelatedEvents(currentId: string, category: EventCategory, limit = 3): Event[] {
  const queries = useCachedRelatedLists<Event>("events")
  const sessionIsCurrent = typeof window === "undefined" || isCurrentBrowserSession()

  return useMemo(() => {
    if (!sessionIsCurrent) return []
    const allItems: Event[] = []
    for (const [, data] of queries) {
      if (data?.pages) {
        for (const page of data.pages) {
          if (page.items) allItems.push(...page.items)
        }
      }
    }

    // Deduplicate, excluding current event
    const seen = new Set<string>()
    const unique: Event[] = []
    for (const item of allItems) {
      if (!seen.has(item.id) && item.id !== currentId) {
        seen.add(item.id)
        unique.push(item)
      }
    }

    // Filter by same category
    const sameCategory = unique.filter(
      (e) => inferEventCategory(e.event_type ?? e.event_type_en) === category
    )

    // If not enough same-category, fill with recent from other categories
    if (sameCategory.length >= limit) return sameCategory.slice(0, limit)

    const remaining = unique
      .filter((e) => inferEventCategory(e.event_type ?? e.event_type_en) !== category)
      .slice(0, limit - sameCategory.length)

    return [...sameCategory, ...remaining].slice(0, limit)
  }, [queries, currentId, category, limit, sessionIsCurrent])
}
