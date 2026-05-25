import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { createPortal } from "react-dom"

type LiveRegionPoliteness = "polite" | "assertive"

interface AnnouncerContextValue {
  announce: (message: string, politeness?: LiveRegionPoliteness) => void
}

const AnnouncerContext = createContext<AnnouncerContextValue | null>(null)

/**
 * Hook to access the live region announcer.
 * Returns a function to announce messages to screen readers.
 *
 * @example
 * const { announce } = useAnnouncer()
 * announce("Form submitted successfully", "polite")
 */
export function useAnnouncer(): AnnouncerContextValue {
  const context = useContext(AnnouncerContext)
  if (!context) {
    // Return a no-op if used outside provider (graceful degradation)
    return { announce: () => {} }
  }
  return context
}

interface LiveRegionProviderProps {
  children: ReactNode
}

/**
 * Provider component that creates ARIA live regions for screen reader announcements.
 * Wrap your app with this provider to enable accessible announcements.
 *
 * @example
 * <LiveRegionProvider>
 *   <App />
 * </LiveRegionProvider>
 */
export function LiveRegionProvider({ children }: LiveRegionProviderProps) {
  const [politeMessage, setPoliteMessage] = useState("")
  const [assertiveMessage, setAssertiveMessage] = useState("")
  const politeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const assertiveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // W156 SW3 — defer portal rendering until after mount to avoid SSR vs client
  // hydration mismatch. Pre-W156 SW3 the portal was gated on
  // `typeof document !== "undefined"` which produced different output on
  // server (null) vs client (live region divs), triggering React #418
  // hydration mismatch + subtree re-render that defeats SSR perf gains.
  //
  // Standard pattern: render NULL on both server initial render AND client
  // initial render (matches), then a useEffect sets `mounted` after hydration
  // completes, triggering a re-render with the live regions. Screen-reader
  // announcements are non-critical at first paint — defer by one tick is
  // acceptable.
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  const announce = useCallback((message: string, politeness: LiveRegionPoliteness = "polite") => {
    // Clear any pending timeouts
    const timeoutRef = politeness === "polite" ? politeTimeoutRef : assertiveTimeoutRef
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }

    // Set the message
    if (politeness === "polite") {
      setPoliteMessage(message)
      politeTimeoutRef.current = setTimeout(() => setPoliteMessage(""), 3000)
    } else {
      setAssertiveMessage(message)
      assertiveTimeoutRef.current = setTimeout(() => setAssertiveMessage(""), 3000)
    }
  }, [])

  const contextValue: AnnouncerContextValue = { announce }

  const liveRegions =
    mounted && typeof document !== "undefined"
      ? createPortal(
          <>
            {/* Polite live region - for non-urgent updates */}
            <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
              {politeMessage}
            </div>
            {/* Assertive live region - for urgent/critical updates */}
            <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only">
              {assertiveMessage}
            </div>
          </>,
          document.body
        )
      : null

  return (
    <AnnouncerContext.Provider value={contextValue}>
      {children}
      {liveRegions}
    </AnnouncerContext.Provider>
  )
}

export default LiveRegionProvider
