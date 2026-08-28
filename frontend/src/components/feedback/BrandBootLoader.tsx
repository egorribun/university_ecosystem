import { useCallback, useEffect, useState, type TransitionEvent } from "react"

import { APP_HYDRATED_EVENT, BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS } from "@/app/hydration"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"

export { BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS } from "@/app/hydration"

type BrandBootLoaderPhase = "active" | "exiting" | "hidden"

const BODY_PATH =
  "M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z"
const OUTER_ACCENT_PATH = "M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0"
const INNER_ACCENT_PATH = "M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0"

export function BrandBootLoader() {
  const [phase, setPhase] = useState<BrandBootLoaderPhase>("active")
  const [paused, setPaused] = useState(false)

  const beginExit = useCallback(() => {
    setPhase((current) => (current === "active" ? "exiting" : current))
  }, [])

  useIsomorphicLayoutEffect(() => {
    window.addEventListener(APP_HYDRATED_EVENT, beginExit)
    if (window.__APP_HYDRATED) {
      beginExit()
    }

    return () => window.removeEventListener(APP_HYDRATED_EVENT, beginExit)
  }, [beginExit])

  useEffect(() => {
    if (phase !== "exiting") {
      return
    }

    const timeoutId = window.setTimeout(() => setPhase("hidden"), BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    return () => window.clearTimeout(timeoutId)
  }, [phase])

  useEffect(() => {
    const updateVisibility = () => setPaused(document.hidden)
    updateVisibility()
    document.addEventListener("visibilitychange", updateVisibility)
    return () => document.removeEventListener("visibilitychange", updateVisibility)
  }, [])

  const handleTransitionEnd = useCallback(
    (event: TransitionEvent<HTMLDivElement>) => {
      if (
        phase === "exiting" &&
        event.target === event.currentTarget &&
        event.propertyName === "opacity"
      ) {
        setPhase("hidden")
      }
    },
    [phase]
  )

  if (phase === "hidden") {
    return null
  }

  return (
    <div
      className="brand-boot-loader"
      data-brand-boot-loader=""
      data-state={phase}
      data-paused={paused ? "true" : undefined}
      role="status"
      aria-label="Загрузка"
      aria-live="polite"
      aria-atomic="true"
      aria-busy={phase === "active"}
      onTransitionEnd={handleTransitionEnd}
    >
      <div className="brand-boot-loader__content">
        <div className="brand-boot-loader__mark-holder">
          <svg
            viewBox="65 65 960 960"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            focusable="false"
          >
            <g className="brand-boot-loader__mark">
              <g className="brand-boot-loader__navy-group">
                <path
                  className="brand-boot-loader__navy brand-boot-loader__body-path"
                  pathLength="1000"
                  d={BODY_PATH}
                />
                <path
                  className="brand-boot-loader__navy brand-boot-loader__accent-path brand-boot-loader__accent-outer"
                  pathLength="1000"
                  d={OUTER_ACCENT_PATH}
                />
                <path
                  className="brand-boot-loader__navy brand-boot-loader__accent-path brand-boot-loader__accent-inner"
                  pathLength="1000"
                  d={INNER_ACCENT_PATH}
                />
              </g>
              <g className="brand-boot-loader__red-group" transform="rotate(180 540.6 544.9)">
                <path
                  className="brand-boot-loader__red brand-boot-loader__body-path"
                  pathLength="1000"
                  d={BODY_PATH}
                />
                <path
                  className="brand-boot-loader__red brand-boot-loader__accent-path brand-boot-loader__accent-outer"
                  pathLength="1000"
                  d={OUTER_ACCENT_PATH}
                />
                <path
                  className="brand-boot-loader__red brand-boot-loader__accent-path brand-boot-loader__accent-inner"
                  pathLength="1000"
                  d={INNER_ACCENT_PATH}
                />
              </g>
            </g>
          </svg>
        </div>
        <div className="brand-boot-loader__status">
          <span>Загрузка</span>
          <span className="brand-boot-loader__dots" aria-hidden="true">
            <span>.</span>
            <span>.</span>
            <span>.</span>
          </span>
        </div>
      </div>
    </div>
  )
}
