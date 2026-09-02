import { useCallback } from "react"
import { useNavigate, useSearch } from "@tanstack/react-router"

/**
 * useURLState — type-safe URL search-param sync for TanStack Router routes.
 *
 * Reads parsed search params (validated upstream by route's `validateSearch`)
 * and exposes setters that follow the project conventions established by
 * EventsFeature in Wave 76+ and FIX-77-03:
 *
 *   - `viewTransition: false` on every change — filter/sort/tab updates must
 *     not trigger CSS view transitions (which cause page-bounce in Wave 77).
 *   - `replace: true` — filter changes don't pollute browser history.
 *   - Empty / undefined / null values are *removed* from the URL — keeps it
 *     clean and aligns with the "absent param = default" convention.
 *
 * @example
 *   // Inside a route component (route declared params via validateSearch):
 *   type Search = { tab?: string; q?: string; cat?: string }
 *   const { params, setParam, setParams } = useURLState<Search>()
 *   const tab = params.tab ?? "active"
 *   setParam("tab", "archive")           // ?tab=archive
 *   setParam("tab", "active")            // ?tab=active (or pass "" to remove)
 *   setParams({ q: "math", cat: "all" }) // batch update
 *
 * Wave 112 (foundation): extracted from EventsFeature so News/Schedule/
 * Activity (SW3) can adopt the same pattern without copy-pasting handlers.
 */
export function useURLState<T extends Record<string, unknown>>(): {
  params: T
  setParam: <K extends keyof T>(key: K, value: T[K] | "" | undefined | null) => void
  setParams: (updates: Partial<T>) => void
} {
  // useSearch returns a strictly-typed value tied to a route. We use
  // `strict: false` to make this hook usable from any route (each route
  // already validates via its own `validateSearch`). The cast through
  // `unknown` keeps the consumer's caller-supplied `T` as the source of truth.
  const params = useSearch({ strict: false }) as unknown as T
  const navigate = useNavigate()

  const setParam = useCallback(
    <K extends keyof T>(key: K, value: T[K] | "" | undefined | null) => {
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => {
          const next = { ...prev }
          if (value === "" || value === undefined || value === null) {
            delete next[key as string]
          } else {
            next[key as string] = value as unknown
          }
          return next
        },
        replace: true,
        resetScroll: false,
        viewTransition: false,
      })
    },
    [navigate]
  )

  const setParams = useCallback(
    (updates: Partial<T>) => {
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => {
          const next = { ...prev }
          for (const [key, value] of Object.entries(updates)) {
            if (value === "" || value === undefined || value === null) {
              delete next[key]
            } else {
              next[key] = value
            }
          }
          return next
        },
        replace: true,
        resetScroll: false,
        viewTransition: false,
      })
    },
    [navigate]
  )

  return { params, setParam, setParams }
}
