
import { useEffect, useRef, useState } from "react"

interface UseIntersectionObserverArgs {
  threshold?: number
  root?: Element | null
  rootMargin?: string
  freezeOnceVisible?: boolean
}

export function useIntersectionObserver({
  threshold = 0,
  root = null,
  rootMargin = "0%",
  freezeOnceVisible = false,
}: UseIntersectionObserverArgs): [React.RefObject<HTMLDivElement | null>, boolean] {
  const [entry, setEntry] = useState<IntersectionObserverEntry>()
  const frozen = entry?.isIntersecting && freezeOnceVisible
  const ref = useRef<HTMLDivElement>(null)

  const updateEntry = ([entry]: IntersectionObserverEntry[]): void => {
    setEntry(entry)
  }

  useEffect(() => {
    const node = ref?.current // DOM Ref
    const hasIOSupport = !!window.IntersectionObserver

    if (!hasIOSupport || frozen || !node) return

    const observerParams = { threshold, root, rootMargin }
    const observer = new IntersectionObserver(updateEntry, observerParams)

    observer.observe(node)

    return () => observer.disconnect()
  }, [ref?.current, JSON.stringify(threshold), root, rootMargin, frozen])

  return [ref, !!entry?.isIntersecting]
}
