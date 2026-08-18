import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import type { StoryItem } from "@/types/Story"
import useMediaQuery from "@/hooks/useMediaQuery"
import { StoryList } from "./StoryList"
import { StoryViewer } from "./StoryViewer"

const STORY_AUTO_ADVANCE_MS = 6500

type DashboardStoriesProps = {
  stories: StoryItem[]
  loading?: boolean
  onPrefetch?: () => void
  onStoryOpen?: (story: StoryItem) => void
  maxVisibleStories?: number
}

export default function DashboardStories({
  stories,
  loading = false,
  onPrefetch,
  onStoryOpen,
  maxVisibleStories = 12,
}: DashboardStoriesProps) {
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const displayStories = useMemo(() => {
    const filtered = Array.isArray(stories) ? stories.filter(Boolean) : []
    return filtered.slice(0, Math.max(1, maxVisibleStories))
  }, [stories, maxVisibleStories])

  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [progress, setProgress] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const rafRef = useRef<number | null>(null)
  const autoStartRef = useRef<number>(0)
  /** Wave 54: Track elapsed time when pausing to avoid timer drift on resume (FIX-54-08) */
  const pausedElapsedRef = useRef<number>(0)

  useEffect(() => {
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  const closeViewer = useCallback(() => {
    setOpenIndex(null)
    setProgress(0)
    setIsPaused(false)
    pausedElapsedRef.current = 0
  }, [])

  const goToIndex = useCallback(
    (nextIndex: number) => {
      const next = Math.max(0, Math.min(displayStories.length - 1, nextIndex))
      const story = displayStories[next]
      if (!story) {
        closeViewer()
        return
      }
      setProgress(0)
      setOpenIndex(next)
      onStoryOpen?.(story)
    },
    [closeViewer, displayStories, onStoryOpen]
  )

  const goNext = useCallback(() => {
    if (openIndex === null) return
    if (openIndex >= displayStories.length - 1) {
      closeViewer()
      return
    }
    goToIndex(openIndex + 1)
  }, [openIndex, displayStories.length, goToIndex, closeViewer])

  const goPrev = useCallback(() => {
    if (openIndex === null) return
    if (openIndex <= 0) {
      setProgress(0)
      return
    }
    goToIndex(openIndex - 1)
  }, [openIndex, goToIndex])

  useEffect(() => {
    if (openIndex === null) {
      setProgress(0)
      return
    }
    setProgress(0)
    autoStartRef.current = performance.now()
  }, [openIndex])

  useEffect(() => {
    if (openIndex === null || prefersReducedMotion || isPaused) {
      return
    }

    const step = (timestamp: number) => {
      const elapsed = timestamp - autoStartRef.current
      const ratio = Math.min(1, elapsed / STORY_AUTO_ADVANCE_MS)
      setProgress(ratio * 100)
      if (ratio >= 1) {
        rafRef.current = null
        goNext()
        return
      }
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [openIndex, goNext, prefersReducedMotion, isPaused])

  useEffect(() => {
    if (openIndex === null) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        closeViewer()
      }
      if (event.key === "ArrowRight") {
        event.preventDefault()
        goNext()
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault()
        goPrev()
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [openIndex, closeViewer, goNext, goPrev])

  const openStory = useCallback(
    (story: StoryItem, index: number) => {
      autoStartRef.current = performance.now()
      setProgress(0)
      setOpenIndex(index)
      onStoryOpen?.(story)
    },
    [onStoryOpen]
  )

  const handlePause = useCallback(() => {
    // Wave 54: Save elapsed time so resume can continue from the right point (FIX-54-08)
    pausedElapsedRef.current = performance.now() - autoStartRef.current
    setIsPaused(true)
  }, [])
  const handleResume = useCallback(() => {
    // Wave 54: Restore start ref so progress continues from where it paused (FIX-54-08)
    autoStartRef.current = performance.now() - pausedElapsedRef.current
    setIsPaused(false)
  }, [])

  return (
    <>
      <StoryList
        stories={displayStories}
        loading={loading}
        onPrefetch={onPrefetch}
        onOpenStory={openStory}
        activeStoryId={openIndex !== null ? displayStories[openIndex]?.id : undefined}
      />
      <StoryViewer
        stories={displayStories}
        activeStoryIndex={openIndex}
        progress={progress}
        onClose={closeViewer}
        onNext={goNext}
        onPrev={goPrev}
        onPause={handlePause}
        onResume={handleResume}
      />
    </>
  )
}
