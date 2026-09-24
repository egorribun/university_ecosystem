import { useEffect, useState, type RefObject } from "react"

/**
 * Keep a filtered list from collapsing while it refills after a filter change.
 *
 * A client-side filter first renders only the matches among the pages loaded
 * so far (or nothing while a refetch runs) and then fills in the rest. That
 * short intermediate list can make the document shorter than the viewport,
 * and the browser clamps the scroll position to the top before the remaining
 * matches arrive (MVP spec §4). The returned minimum height keeps the
 * previous list height while `settling` is true; afterwards the browser
 * clamps, at most, to the final list's own maximum.
 *
 * The floor is derived during render, so it lands in the same commit as the
 * short list: any layout read in that commit (a child's layout effect, for
 * example) already sees the held height and never clamps the scroll.
 */
export function useStableListHeight(
  containerRef: RefObject<HTMLElement | null>,
  resetKey: string,
  settling: boolean
): number | undefined {
  const [lastHeight, setLastHeight] = useState(0)
  const [heldKey, setHeldKey] = useState(resetKey)
  const [floor, setFloor] = useState<number | undefined>(undefined)

  if (heldKey !== resetKey) {
    setHeldKey(resetKey)
    setFloor(settling ? lastHeight : undefined)
  } else if (!settling && floor !== undefined) {
    setFloor(undefined)
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container || settling) return
    // Track the settled height only; a held floor must not become the next one.
    const observer = new ResizeObserver(() => {
      setLastHeight(Math.round(container.getBoundingClientRect().height))
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [containerRef, settling])

  return floor
}
