import { useEffect, useState, type RefObject } from "react"

interface UseIntersectionObserverOptions extends IntersectionObserverInit {
  freezeOnceVisible?: boolean
}

/**
 * A hook that detects when an element is visible in the viewport.
 *
 * @param elementRef The ref of the element to observe
 * @param options IntersectionObserver options
 * @returns An IntersectionObserverEntry or undefined
 */
export function useIntersectionObserver(
  elementRef: RefObject<Element | null>,
  {
    threshold = 0,
    root = null,
    rootMargin = "0%",
    freezeOnceVisible = false,
  }: UseIntersectionObserverOptions = {}
): IntersectionObserverEntry | undefined {
  const [entry, setEntry] = useState<IntersectionObserverEntry>()

  const frozen = entry?.isIntersecting && freezeOnceVisible

  const updateEntry = ([newEntry]: IntersectionObserverEntry[]): void => {
    setEntry(newEntry)
  }

  useEffect(() => {
    const node = elementRef?.current
    const hasIOSupport = !!window.IntersectionObserver

    if (!hasIOSupport || frozen || !node) return

    const observerParams = { threshold, root, rootMargin }
    const observer = new IntersectionObserver(updateEntry, observerParams)

    observer.observe(node)

    return () => {
      observer.disconnect()
    }
  }, [elementRef, threshold, root, rootMargin, frozen])

  return entry
}

export function useIsVisible(
  elementRef: RefObject<Element | null>,
  options?: UseIntersectionObserverOptions
): boolean {
  const entry = useIntersectionObserver(elementRef, options)
  return !!entry?.isIntersecting
}




