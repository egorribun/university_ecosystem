# Application Logo Loader Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved Clean Signature logo loader to the application's SSR bootstrap shell, keep `Загрузка` continuously visible between logo cycles, and remove the complete overlay immediately and safely after React hydration.

**Architecture:** Render a deterministic `BrandBootLoader` inside the TanStack Router `RootShell` so the first server paint and client hydration tree match. Publish hydration through one idempotent application event, keep the six-second logo animation in critical shell CSS, and let React own the final exiting/hidden states. Update the standalone reference to the same persistent-status behavior and verify unit, shell, build, CSP, responsive, reduced-motion, and real-browser contracts.

**Tech Stack:** React 19, TypeScript, TanStack Router/Start SSR shell, inline SVG, critical CSS animations, Vitest + Testing Library, Playwright, Vite/Rolldown, Prettier, ESLint.

---

## File map

- Create: `frontend/src/app/hydration.ts` — canonical idempotent hydration sentinel and completion event.
- Modify: `frontend/src/AppProviders.tsx:1-108` — publish hydration through the canonical helper.
- Modify: `frontend/src/__tests__/AppProviders.closure.test.tsx` — verify the existing sentinel and the new one-shot event.
- Create: `frontend/src/components/feedback/BrandBootLoader.tsx` — SSR-safe markup and React-owned lifecycle.
- Create: `frontend/src/components/feedback/brandBootLoaderCss.ts` — first-paint critical CSS, exact timeline, responsive rules, reduced-motion path, and no-JS failsafe.
- Create: `frontend/src/components/feedback/__tests__/BrandBootLoader.test.tsx` — lifecycle, race, StrictMode, visibility, and accessibility tests.
- Create: `frontend/src/components/feedback/__tests__/brandBootLoaderCss.test.ts` — static animation and persistent-status contracts.
- Modify: `frontend/src/routes/__root.tsx:1-15,74-131,255-319` — emit critical loader CSS and markup before `#root`.
- Modify: `frontend/src/routes/__tests__/__root.test.tsx` — assert shell ordering and critical CSS.
- Create: `frontend/tests/e2e/brand-boot-loader.spec.ts` — block application scripts to inspect the real SSR first paint, then release hydration and verify exit.
- Modify: `C:\Users\egorribun\Documents\logo-loader.html` — keep the visible loading label outside the logo cycle fade.
- Preserve untouched: `.github/workflows/reusable-frontend-tests.yml` and `tests/test_quality_workflow_contract.py` — unrelated pre-existing worktree changes.

## Stable contracts

~~~ts
export const APP_HYDRATED_EVENT = "ue:app-hydrated"

export function markAppHydrated(): void
~~~

~~~ts
type BrandBootLoaderPhase = "active" | "exiting" | "hidden"

export const BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS = 600
export function BrandBootLoader(): JSX.Element | null
export const BRAND_BOOT_LOADER_CSS: string
~~~

DOM selectors used by shell and browser tests:

~~~text
[data-brand-boot-loader]
[data-brand-boot-loader][data-state="active"]
[data-brand-boot-loader][data-state="exiting"]
.brand-boot-loader__mark
.brand-boot-loader__status
~~~

### Task 1: Publish one canonical hydration-completion event

**Files:**
- Create: `frontend/src/app/hydration.ts`
- Modify: `frontend/src/AppProviders.tsx:1-3,104-108`
- Modify: `frontend/src/__tests__/AppProviders.closure.test.tsx:1-4,59-103`

- [ ] **Step 1: Extend the provider test with the RED event contract**

Add the event import and assert that normal rendering publishes exactly one event while retaining the existing boolean sentinel:

~~~tsx
import { StrictMode, type ReactNode } from "react"
import { APP_HYDRATED_EVENT } from "@/app/hydration"

it("publishes hydration exactly once, including under StrictMode effects", async () => {
  const AppProviders = await loadProviders("false")
  const onHydrated = vi.fn()
  window.addEventListener(APP_HYDRATED_EVENT, onHydrated)

  render(
    <StrictMode>
      <AppProviders>
        <span>strict application child</span>
      </AppProviders>
    </StrictMode>
  )

  await waitFor(() => expect(window.__APP_HYDRATED).toBe(true))
  expect(onHydrated).toHaveBeenCalledTimes(1)
  window.removeEventListener(APP_HYDRATED_EVENT, onHydrated)
})
~~~

- [ ] **Step 2: Run the focused test and verify RED**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/__tests__/AppProviders.closure.test.tsx --silent=true
~~~

Expected: FAIL because `@/app/hydration` and `APP_HYDRATED_EVENT` do not exist.

- [ ] **Step 3: Add the idempotent hydration helper**

Create `frontend/src/app/hydration.ts`:

~~~ts
export const APP_HYDRATED_EVENT = "ue:app-hydrated"

export function markAppHydrated(): void {
  if (typeof window === "undefined" || window.__APP_HYDRATED) {
    return
  }

  window.__APP_HYDRATED = true
  window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
}
~~~

- [ ] **Step 4: Route AppProviders through the helper**

Add:

~~~ts
import { markAppHydrated } from "@/app/hydration"
~~~

Replace the current effect body with:

~~~tsx
useEffect(() => {
  markAppHydrated()
}, [])
~~~

Keep the sentinel at the current top-level post-commit timing and update its surrounding comment to state that the helper also publishes the idempotent bootstrap-loader event.

- [ ] **Step 5: Run GREEN tests and commit only Task 1 files**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/__tests__/AppProviders.closure.test.tsx --silent=true
npx eslint --max-warnings=0 src/app/hydration.ts src/AppProviders.tsx src/__tests__/AppProviders.closure.test.tsx
npx tsc --noEmit
cd ..
git add -- frontend/src/app/hydration.ts frontend/src/AppProviders.tsx frontend/src/__tests__/AppProviders.closure.test.tsx
git diff --cached --check
git commit -m "feat: publish app hydration completion"
~~~

Expected: tests, ESLint, typecheck, and staged diff check pass; unrelated workflow files remain unstaged.

### Task 2: Build the SSR-safe loader lifecycle and exact SVG

**Files:**
- Create: `frontend/src/components/feedback/BrandBootLoader.tsx`
- Create: `frontend/src/components/feedback/__tests__/BrandBootLoader.test.tsx`

- [ ] **Step 1: Write RED lifecycle and accessibility tests**

Create `frontend/src/components/feedback/__tests__/BrandBootLoader.test.tsx`:

~~~tsx
import { StrictMode } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { APP_HYDRATED_EVENT } from "@/app/hydration"
import {
  BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS,
  BrandBootLoader,
} from "../BrandBootLoader"

describe("BrandBootLoader", () => {
  let hidden = false

  beforeEach(() => {
    vi.useFakeTimers()
    delete window.__APP_HYDRATED
    hidden = false
    vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("renders one accessible persistent status and decorative mark", () => {
    render(<BrandBootLoader />)

    const loader = screen.getByRole("status", { name: "Загрузка" })
    expect(loader).toHaveAttribute("data-state", "active")
    expect(loader).toHaveAttribute("aria-live", "polite")
    expect(loader).toHaveAttribute("aria-atomic", "true")
    expect(loader).toHaveAttribute("aria-busy", "true")
    expect(screen.getByText("Загрузка")).toBeVisible()
    expect(loader.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(loader.querySelector(".brand-boot-loader__dots")).toHaveAttribute(
      "aria-hidden",
      "true"
    )
    expect(loader.querySelectorAll('path[pathLength="1000"]')).toHaveLength(6)
  })

  it("starts one shared exit on the hydration event and unmounts on opacity transition", () => {
    render(<BrandBootLoader />)
    const loader = screen.getByRole("status", { name: "Загрузка" })

    act(() => window.dispatchEvent(new Event(APP_HYDRATED_EVENT)))
    expect(loader).toHaveAttribute("data-state", "exiting")
    expect(loader).toHaveAttribute("aria-busy", "false")

    fireEvent.transitionEnd(loader, { propertyName: "opacity" })
    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("uses the timeout fallback when transitionend is unavailable", () => {
    render(<BrandBootLoader />)
    act(() => window.dispatchEvent(new Event(APP_HYDRATED_EVENT)))

    act(() => vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS))
    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("does not miss hydration that completed before its effect subscribed", () => {
    window.__APP_HYDRATED = true
    render(<BrandBootLoader />)

    expect(screen.getByRole("status", { name: "Загрузка" })).toHaveAttribute(
      "data-state",
      "exiting"
    )
  })

  it("remains idempotent under StrictMode and duplicate completion events", () => {
    render(
      <StrictMode>
        <BrandBootLoader />
      </StrictMode>
    )

    act(() => {
      window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
      window.dispatchEvent(new Event(APP_HYDRATED_EVENT))
      vi.advanceTimersByTime(BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
    })

    expect(screen.queryByRole("status", { name: "Загрузка" })).not.toBeInTheDocument()
  })

  it("pauses and resumes the logo timeline with document visibility", () => {
    render(<BrandBootLoader />)
    const loader = screen.getByRole("status", { name: "Загрузка" })

    hidden = true
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(loader).toHaveAttribute("data-paused", "true")

    hidden = false
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(loader).not.toHaveAttribute("data-paused")
  })
})
~~~

- [ ] **Step 2: Run the component test and verify RED**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/components/feedback/__tests__/BrandBootLoader.test.tsx --silent=true
~~~

Expected: FAIL because `BrandBootLoader` does not exist.

- [ ] **Step 3: Implement the deterministic React lifecycle**

Create `frontend/src/components/feedback/BrandBootLoader.tsx` with this lifecycle and exact paths:

~~~tsx
import {
  useCallback,
  useEffect,
  useState,
  type TransitionEvent,
} from "react"

import { APP_HYDRATED_EVENT } from "@/app/hydration"

type BrandBootLoaderPhase = "active" | "exiting" | "hidden"

export const BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS = 600

const BODY_PATH =
  "M 432.53,279.03 A 102.77 102.77 0 0 0 356.91,313.10 L 184.73,504.69 A 20.43 20.43 0 0 0 215.20,532.06 L 384.10,343.81 A 68.71 68.71 0 0 1 434.70,320.99 L 813.00,318.00 A 46.0 46.0 0 0 1 823.00,405.00 L 458.17,405.16 A 23.73 23.73 0 0 0 440.53,413.02 L 358.13,504.69 A 22.39 22.39 0 0 0 374.96,542.05 L 761.598,539.011 A 2 2 0 0 0 763.069,538.349 L 870.501,419.037 A 85.7985 85.7985 0 0 0 806.844,276.072 Z"
const OUTER_ACCENT_PATH =
  "M 260.0,528.7 L 392.6,373.0 Q 413.0,349.0 444.5,349.2 L 804.0,351.0"
const INNER_ACCENT_PATH =
  "M 312.9,515.8 L 409.8,400.1 Q 427.5,379.0 455.0,379.1 L 804.0,381.0"

export function BrandBootLoader() {
  const [phase, setPhase] = useState<BrandBootLoaderPhase>("active")
  const [paused, setPaused] = useState(false)

  const beginExit = useCallback(() => {
    setPhase((current) => (current === "active" ? "exiting" : current))
  }, [])

  useEffect(() => {
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

    const timeoutId = window.setTimeout(
      () => setPhase("hidden"),
      BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS
    )
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
              <g
                className="brand-boot-loader__red-group"
                transform="rotate(180 540.6 544.9)"
              >
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
~~~

- [ ] **Step 4: Run GREEN component tests**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/components/feedback/__tests__/BrandBootLoader.test.tsx --silent=true
npx eslint --max-warnings=0 src/components/feedback/BrandBootLoader.tsx src/components/feedback/__tests__/BrandBootLoader.test.tsx
~~~

Expected: all six component tests pass with no warnings.

- [ ] **Step 5: Commit Task 2 files**

~~~powershell
cd ..
git add -- frontend/src/components/feedback/BrandBootLoader.tsx frontend/src/components/feedback/__tests__/BrandBootLoader.test.tsx
git diff --cached --check
git commit -m "feat: add SSR brand boot loader"
~~~

### Task 3: Add the critical Clean Signature animation contract

**Files:**
- Create: `frontend/src/components/feedback/brandBootLoaderCss.ts`
- Create: `frontend/src/components/feedback/__tests__/brandBootLoaderCss.test.ts`

- [ ] **Step 1: Write RED CSS contract tests**

Create `frontend/src/components/feedback/__tests__/brandBootLoaderCss.test.ts`:

~~~ts
import { describe, expect, it } from "vitest"

import { BRAND_BOOT_LOADER_CSS } from "../brandBootLoaderCss"

const ruleBody = (selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return BRAND_BOOT_LOADER_CSS.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "s"))?.[1] ?? ""
}

describe("BRAND_BOOT_LOADER_CSS", () => {
  it("preserves exact brand colors and the six-second master timing", () => {
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-navy: #033167")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-red: #e40137")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-cycle: 6s")
    expect(BRAND_BOOT_LOADER_CSS).toContain("--brand-boot-loader-hold: 2500ms")
    expect(BRAND_BOOT_LOADER_CSS).toContain("43.5%,")
    expect(BRAND_BOOT_LOADER_CSS).toContain("85.1667%")
    expect(BRAND_BOOT_LOADER_CSS).toContain("92.6667%")
  })

  it("fades both colors through the common mark and never cycles the status opacity", () => {
    expect(ruleBody(".brand-boot-loader__mark")).toContain(
      "animation: brand-boot-loader-mark-exit"
    )
    expect(ruleBody(".brand-boot-loader__status")).not.toMatch(/\banimation\s*:/)
    expect(BRAND_BOOT_LOADER_CSS).not.toContain("status-exit")
  })

  it("contains no animated transform, rocking, pulse, glow, or halo", () => {
    const keyframes = BRAND_BOOT_LOADER_CSS.split("@keyframes").slice(1).join("@keyframes")
    expect(keyframes).not.toMatch(/\btransform\s*:/)
    expect(BRAND_BOOT_LOADER_CSS).not.toMatch(/rock|pulse|glow|halo/i)
  })

  it("provides final exit, no-JS failsafe, reduced motion, and hidden-tab pause", () => {
    expect(ruleBody('.brand-boot-loader[data-state="exiting"]')).toContain("opacity: 0")
    expect(BRAND_BOOT_LOADER_CSS).toContain("12s")
    expect(BRAND_BOOT_LOADER_CSS).toContain("@media (prefers-reduced-motion: reduce)")
    expect(BRAND_BOOT_LOADER_CSS).toContain('[data-paused="true"]')
    expect(BRAND_BOOT_LOADER_CSS).toContain(".lhci-mode .brand-boot-loader")
  })
})
~~~

- [ ] **Step 2: Run the CSS test and verify RED**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/components/feedback/__tests__/brandBootLoaderCss.test.ts --silent=true
~~~

Expected: FAIL because `brandBootLoaderCss.ts` does not exist.

- [ ] **Step 3: Create the complete critical CSS export**

Create `frontend/src/components/feedback/brandBootLoaderCss.ts`. Copy the verified standalone keyframe percentages exactly, namespace every selector/keyframe, remove the cycle-level status fade, and use an independent dot loop:

~~~ts
export const BRAND_BOOT_LOADER_CSS = String.raw`
:root {
  --brand-boot-loader-navy: #033167;
  --brand-boot-loader-red: #e40137;
  --brand-boot-loader-cycle: 6s;
  --brand-boot-loader-hold: 2500ms;
  --brand-boot-loader-exit: 450ms;
  --brand-boot-loader-size: clamp(9rem, 22vmin, 18rem);
  --brand-boot-loader-gap: clamp(1.125rem, 3vmin, 1.75rem);
  --brand-boot-loader-status-size: clamp(0.6875rem, 1.4vmin, 0.8125rem);
  --brand-boot-loader-status-color: #8490a2;
  --brand-boot-loader-draw-ease: cubic-bezier(0.61, 0.06, 0.35, 1);
  --brand-boot-loader-exit-ease: cubic-bezier(0.4, 0, 0.2, 1);
  --z-boot-loader: 999998;
}

.dark {
  --brand-boot-loader-status-color: #aeb8c7;
}

.brand-boot-loader {
  position: fixed;
  z-index: var(--z-boot-loader);
  inset: 0;
  display: grid;
  min-width: 100%;
  min-height: 100vh;
  min-height: 100svh;
  min-height: 100dvh;
  box-sizing: border-box;
  place-items: center;
  overflow: clip;
  padding:
    max(1rem, env(safe-area-inset-top))
    max(1rem, env(safe-area-inset-right))
    max(1rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  color: var(--brand-boot-loader-status-color);
  background: var(--initial-bg, #f8fafc);
  isolation: isolate;
  opacity: 1;
  pointer-events: auto;
  contain: layout paint style;
  font-family: "Avenir Next", "Segoe UI", sans-serif;
  animation: brand-boot-loader-failsafe 1ms linear 12s forwards;
  will-change: opacity;
}

.brand-boot-loader *,
.brand-boot-loader *::before,
.brand-boot-loader *::after {
  box-sizing: border-box;
}

.brand-boot-loader[data-state="exiting"] {
  opacity: 0;
  pointer-events: none;
  animation: none;
  transition: opacity var(--brand-boot-loader-exit)
    var(--brand-boot-loader-exit-ease);
}

.lhci-mode .brand-boot-loader {
  display: none;
}

.brand-boot-loader__content {
  display: flex;
  width: min(100%, 36rem);
  max-height: calc(100dvh - 2rem);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--brand-boot-loader-gap);
}

.brand-boot-loader__mark-holder {
  width: min(100%, var(--brand-boot-loader-size));
  flex: 0 1 auto;
  transform: translate(0.45%, 0.15%);
}

.brand-boot-loader__mark-holder svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  shape-rendering: geometricPrecision;
}

.brand-boot-loader__navy {
  fill: var(--brand-boot-loader-navy);
  stroke: var(--brand-boot-loader-navy);
}

.brand-boot-loader__red {
  fill: var(--brand-boot-loader-red);
  stroke: var(--brand-boot-loader-red);
}

.brand-boot-loader__body-path,
.brand-boot-loader__accent-path {
  opacity: 0;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1000;
  stroke-dashoffset: 1000;
  will-change: opacity, stroke-dashoffset, fill-opacity, stroke-opacity;
}

.brand-boot-loader__body-path {
  fill-opacity: 0;
  stroke-width: 8;
  stroke-opacity: 1;
}

.brand-boot-loader__accent-path {
  fill: none;
  stroke-width: 6;
}

.brand-boot-loader__mark {
  animation: brand-boot-loader-mark-exit var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-exit-ease) infinite;
  will-change: opacity;
}

.brand-boot-loader__navy-group .brand-boot-loader__body-path {
  animation: brand-boot-loader-navy-body var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__body-path {
  animation: brand-boot-loader-red-body var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__navy-group .brand-boot-loader__accent-outer {
  animation: brand-boot-loader-navy-accent-outer var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__navy-group .brand-boot-loader__accent-inner {
  animation: brand-boot-loader-navy-accent-inner var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__accent-outer {
  animation: brand-boot-loader-red-accent-outer var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__accent-inner {
  animation: brand-boot-loader-red-accent-inner var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__status {
  display: flex;
  min-height: 1.5em;
  align-items: baseline;
  justify-content: center;
  gap: 0.125rem;
  color: var(--brand-boot-loader-status-color);
  font-size: var(--brand-boot-loader-status-size);
  font-weight: 650;
  letter-spacing: 0.16em;
  line-height: 1.35;
  text-align: center;
  text-transform: uppercase;
}

.brand-boot-loader__dots {
  display: inline-flex;
  min-width: 1.1em;
  letter-spacing: 0.08em;
}

.brand-boot-loader__dots span {
  opacity: 0.25;
  animation: brand-boot-loader-dot 1.2s ease-in-out infinite;
}

.brand-boot-loader__dots span:nth-child(2) {
  animation-delay: 150ms;
}

.brand-boot-loader__dots span:nth-child(3) {
  animation-delay: 300ms;
}

@keyframes brand-boot-loader-mark-exit {
  0%,
  85.1667% { opacity: 1; }
  92.6667%,
  100% { opacity: 0; }
}

@keyframes brand-boot-loader-navy-body {
  0% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  4.2% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  26.4% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 0;
  }
  36%,
  92.6667% {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-red-body {
  0%,
  7.5% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  11.7% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  33.9% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 0;
  }
  43.5%,
  92.6667% {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-navy-accent-outer {
  0%,
  5.3667% { opacity: 0; stroke-dashoffset: 1000; }
  27.5667%,
  92.6667% { opacity: 1; stroke-dashoffset: 0; }
  100% { opacity: 0; stroke-dashoffset: 1000; }
}

@keyframes brand-boot-loader-navy-accent-inner {
  0%,
  6.5333% { opacity: 0; stroke-dashoffset: 1000; }
  28.7333%,
  92.6667% { opacity: 1; stroke-dashoffset: 0; }
  100% { opacity: 0; stroke-dashoffset: 1000; }
}

@keyframes brand-boot-loader-red-accent-outer {
  0%,
  12.8667% { opacity: 0; stroke-dashoffset: 1000; }
  35.0667%,
  92.6667% { opacity: 1; stroke-dashoffset: 0; }
  100% { opacity: 0; stroke-dashoffset: 1000; }
}

@keyframes brand-boot-loader-red-accent-inner {
  0%,
  14.0333% { opacity: 0; stroke-dashoffset: 1000; }
  36.2333%,
  92.6667% { opacity: 1; stroke-dashoffset: 0; }
  100% { opacity: 0; stroke-dashoffset: 1000; }
}

@keyframes brand-boot-loader-dot {
  0%,
  20%,
  100% { opacity: 0.25; }
  50% { opacity: 1; }
}

@keyframes brand-boot-loader-failsafe {
  to {
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
  }
}

.brand-boot-loader[data-paused="true"] .brand-boot-loader__mark,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__body-path,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__accent-path,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__dots span {
  animation-play-state: paused;
}

@media (max-height: 22.5rem) and (orientation: landscape) {
  :root {
    --brand-boot-loader-size: clamp(9rem, 38vmin, 9.5rem);
    --brand-boot-loader-gap: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .brand-boot-loader__mark,
  .brand-boot-loader__body-path,
  .brand-boot-loader__accent-path,
  .brand-boot-loader__dots span {
    animation: none;
  }

  .brand-boot-loader__mark,
  .brand-boot-loader__accent-path,
  .brand-boot-loader__dots span {
    opacity: 1;
  }

  .brand-boot-loader__body-path {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }

  .brand-boot-loader__accent-path {
    stroke-dashoffset: 0;
  }

  .brand-boot-loader[data-state="exiting"] {
    transition: none;
  }
}

@media (forced-colors: active) {
  .brand-boot-loader__status {
    color: CanvasText;
  }
}
`
~~~

- [ ] **Step 4: Run GREEN CSS tests, format, and commit**

Run:

~~~powershell
cd frontend
npx prettier --write src/components/feedback/brandBootLoaderCss.ts src/components/feedback/__tests__/brandBootLoaderCss.test.ts
npx vitest run --configLoader runner src/components/feedback/__tests__/brandBootLoaderCss.test.ts --silent=true
npx eslint --max-warnings=0 src/components/feedback/brandBootLoaderCss.ts src/components/feedback/__tests__/brandBootLoaderCss.test.ts
cd ..
git add -- frontend/src/components/feedback/brandBootLoaderCss.ts frontend/src/components/feedback/__tests__/brandBootLoaderCss.test.ts
git diff --cached --check
git commit -m "feat: add critical brand loader animation"
~~~

### Task 4: Mount the loader in the hydration-safe SSR shell

**Files:**
- Modify: `frontend/src/routes/__root.tsx:1-15,74-131,255-319`
- Modify: `frontend/src/routes/__tests__/__root.test.tsx:1-92`

- [ ] **Step 1: Add RED shell ordering and critical-style assertions**

In the first `RootShell` test, add:

~~~tsx
const loader = document.querySelector("[data-brand-boot-loader]")
const root = document.getElementById("root")
expect(loader).toBeInTheDocument()
expect(root).toBeInTheDocument()
expect(
  loader?.compareDocumentPosition(root as Node) & Node.DOCUMENT_POSITION_FOLLOWING
).toBeTruthy()
expect(document.head.textContent).toContain("@keyframes brand-boot-loader-mark-exit")
expect(document.head.textContent).not.toContain("@keyframes status-exit")
~~~

Add a focused assertion that the visible status is not nested in the cycle-faded mark:

~~~tsx
it("keeps the loading label outside the cycling logo mark", () => {
  const Shell = (Route.options as any).shellComponent
  render(
    <Shell>
      <div>Test Child</div>
    </Shell>
  )

  const status = screen.getByText("Загрузка").closest(".brand-boot-loader__status")
  const mark = document.querySelector(".brand-boot-loader__mark")
  expect(status).toBeInTheDocument()
  expect(mark).toBeInTheDocument()
  expect(mark?.contains(status)).toBe(false)
})
~~~

- [ ] **Step 2: Run the root test and verify RED**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/routes/__tests__/__root.test.tsx --silent=true
~~~

Expected: FAIL because the shell does not yet contain the loader.

- [ ] **Step 3: Integrate markup and critical CSS**

Add imports:

~~~tsx
import { BrandBootLoader } from "@/components/feedback/BrandBootLoader"
import { BRAND_BOOT_LOADER_CSS } from "@/components/feedback/brandBootLoaderCss"
~~~

Create the combined constant after `INITIAL_PAINT_CSS`:

~~~ts
const CRITICAL_SHELL_CSS = `${INITIAL_PAINT_CSS}\n${BRAND_BOOT_LOADER_CSS}`
~~~

Replace the shell style content:

~~~tsx
<style dangerouslySetInnerHTML={{ __html: CRITICAL_SHELL_CSS }} />
~~~

Render the loader before the application root:

~~~tsx
<BrandBootLoader />
<div id="root" className="ready">
  {children}
</div>
~~~

Do not change `hydrateRoot(document)`, the provider tree, router fallbacks, `#root.ready`, `HeadContent`, `Scripts`, or LHCI marker order.

- [ ] **Step 4: Run shell and lifecycle regression tests**

Run:

~~~powershell
cd frontend
npx vitest run --configLoader runner src/routes/__tests__/__root.test.tsx src/components/feedback/__tests__/BrandBootLoader.test.tsx src/components/feedback/__tests__/brandBootLoaderCss.test.ts src/__tests__/AppProviders.closure.test.tsx --silent=true
npx eslint --max-warnings=0 src/routes/__root.tsx src/routes/__tests__/__root.test.tsx
npx tsc --noEmit
~~~

Expected: all targeted tests, lint, and typecheck pass without hydration-related warnings.

- [ ] **Step 5: Commit only shell integration files**

~~~powershell
cd ..
git add -- frontend/src/routes/__root.tsx frontend/src/routes/__tests__/__root.test.tsx
git diff --cached --check
git commit -m "feat: mount logo loader in app shell"
~~~

### Task 5: Keep the standalone loading label persistent

**Files:**
- Modify: `C:\Users\egorribun\Documents\logo-loader.html:165-179,352-361`
- Test: `C:\Temp\logo-loader-verification\verify-contract.cjs`
- Test: `C:\Temp\logo-loader-verification\verify-browser.cjs`

- [ ] **Step 1: Strengthen the standalone contract before editing**

Add these checks to `verify-contract.cjs`:

~~~js
const statusRule = html.match(/\.status\s*\{([^}]*)\}/s)?.[1] ?? ""
assert.doesNotMatch(statusRule, /\banimation\s*:/)
assert.doesNotMatch(html, /@keyframes\s+status-exit/i)
assert.match(html, /\.logo-loader\.is-finishing\s+\.status/)
~~~

Run:

~~~powershell
node C:\Temp\logo-loader-verification\verify-contract.cjs
~~~

Expected: FAIL because the current status still uses `status-exit`.

- [ ] **Step 2: Remove only the cycle-level status fade**

In `logo-loader.html`:

1. Remove `animation: status-exit var(--cycle-duration) var(--exit-ease) infinite;` from `.status`.
2. Remove the complete `@keyframes status-exit` block.
3. Keep `.logo-loader.is-finishing .status` so explicit final completion still removes the whole loader.
4. Keep dot animations and their fixed-width container; the text `Загрузка` itself remains at opacity one throughout every automatic cycle.

- [ ] **Step 3: Verify static and real-browser persistence**

Add a browser assertion after moving mark animations to 5700 ms:

~~~js
await page.locator(".mark").evaluate((mark) => {
  for (const animation of mark.getAnimations({ subtree: true })) {
    animation.currentTime = 5700
  }
})
assert.equal(await page.locator(".mark").evaluate((node) => getComputedStyle(node).opacity), "0")
assert.equal(await page.locator(".status").evaluate((node) => getComputedStyle(node).opacity), "1")
~~~

Run:

~~~powershell
npx prettier --write C:\Users\egorribun\Documents\logo-loader.html
node C:\Temp\logo-loader-verification\verify-contract.cjs
node C:\Temp\logo-loader-verification\verify-browser.cjs
~~~

Expected: contract and browser verifiers print `contract: ok` and `browser: ok`.

### Task 6: Verify the real SSR first paint, hydration exit, and responsive matrix

**Files:**
- Create: `frontend/tests/e2e/brand-boot-loader.spec.ts`
- Test: generated `frontend/.output/public/_shell.html` or `frontend/dist/client/_shell.html`

- [ ] **Step 1: Create a Playwright first-paint and lifecycle spec**

Create `frontend/tests/e2e/brand-boot-loader.spec.ts`:

~~~ts
import { expect, test, type Page } from "@playwright/test"

async function holdApplicationScripts(page: Page) {
  let releaseGate = () => {}
  const gate = new Promise<void>((resolve) => {
    releaseGate = resolve
  })

  await page.route("**/*", async (route) => {
    if (route.request().resourceType() === "script") {
      await gate
    }
    await route.continue()
  })

  return async () => {
    releaseGate()
    await page.unrouteAll({ behavior: "wait" })
  }
}

test("renders the SSR loader before JavaScript and keeps status through mark reset", async ({
  page,
}) => {
  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })

  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()
  await expect(loader).toHaveAttribute("data-state", "active")
  await expect(loader.getByText("Загрузка")).toBeVisible()

  await page.locator(".brand-boot-loader__mark").evaluate((mark) => {
    for (const animation of mark.getAnimations({ subtree: true })) {
      animation.currentTime = 5700
    }
  })

  await expect
    .poll(() =>
      page
        .locator(".brand-boot-loader__mark")
        .evaluate((element) => getComputedStyle(element).opacity)
    )
    .toBe("0")
  await expect
    .poll(() =>
      page
        .locator(".brand-boot-loader__status")
        .evaluate((element) => getComputedStyle(element).opacity)
    )
    .toBe("1")

  const fitsViewport = await loader.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth
  )
  expect(fitsViewport).toBe(true)
  await releaseScripts()
})

test("exits after hydration without a mismatch or lingering hit target", async ({ page }) => {
  const hydrationMessages: string[] = []
  page.on("console", (message) => {
    if (/hydration|react error #418|didn't match/i.test(message.text())) {
      hydrationMessages.push(message.text())
    }
  })

  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })
  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()

  await releaseScripts()
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(loader).toHaveCount(0, { timeout: 2_000 })
  expect(hydrationMessages).toEqual([])
})

test("uses a complete static mark for reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" })
  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })

  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()
  await expect(page.locator(".brand-boot-loader__body-path").first()).toHaveCSS(
    "fill-opacity",
    "1"
  )
  expect(
    await page
      .locator(".brand-boot-loader__mark")
      .evaluate((element) => element.getAnimations({ subtree: true }).length)
  ).toBe(0)

  await releaseScripts()
})

test("reveals the SSR application after the CSS-only failsafe", async ({ page }) => {
  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })

  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()
  await loader.evaluate((element) => {
    const failsafe = element
      .getAnimations()
      .find(
        (animation) =>
          animation instanceof CSSAnimation &&
          animation.animationName === "brand-boot-loader-failsafe"
      )
    if (!failsafe) {
      throw new Error("Brand loader failsafe animation is missing")
    }
    failsafe.currentTime = 12_001
  })

  await expect(loader).toHaveCSS("visibility", "hidden")
  await expect(loader).toHaveCSS("pointer-events", "none")
  await releaseScripts()
})
~~~

- [ ] **Step 2: Run the focused browser spec**

Run:

~~~powershell
cd frontend
npx playwright test tests/e2e/brand-boot-loader.spec.ts --project=chromium --workers=1
~~~

Expected: all first-paint, persistent-status, hydration-exit, reduced-motion, and CSS-only failsafe scenarios pass.

- [ ] **Step 3: Add the viewport and theme visual matrix**

Extend the first test before releasing scripts:

~~~ts
for (const viewport of [
  { width: 320, height: 568 },
  { width: 568, height: 320 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
  { width: 3840, height: 2160 },
]) {
  await page.setViewportSize(viewport)
  const box = await loader.boundingBox()
  expect(box).not.toBeNull()
  expect(box?.x).toBeGreaterThanOrEqual(0)
  expect(box?.y).toBeGreaterThanOrEqual(0)
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(viewport.width)
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(viewport.height)
}
~~~

Add this focused dark-theme check and store review screenshots under `C:\Temp\logo-loader-integration-verification\`, not in the repository:

~~~ts
test("matches the pre-paint dark theme without a background flash", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("ue-mode", "dark"))
  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })

  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()
  const colors = await loader.evaluate((element) => ({
    loader: getComputedStyle(element).backgroundColor,
    initial: getComputedStyle(document.documentElement)
      .getPropertyValue("--initial-bg")
      .trim(),
  }))
  expect(colors.loader).toBe("rgb(2, 6, 23)")
  expect(colors.initial).toBe("#020617")
  await releaseScripts()
})
~~~

- [ ] **Step 4: Run the complete focused verification set**

Run:

~~~powershell
cd frontend
npx prettier --write src/app/hydration.ts src/AppProviders.tsx src/__tests__/AppProviders.closure.test.tsx src/components/feedback/BrandBootLoader.tsx src/components/feedback/brandBootLoaderCss.ts src/components/feedback/__tests__/BrandBootLoader.test.tsx src/components/feedback/__tests__/brandBootLoaderCss.test.ts src/routes/__root.tsx src/routes/__tests__/__root.test.tsx tests/e2e/brand-boot-loader.spec.ts
npx vitest run --configLoader runner src/__tests__/AppProviders.closure.test.tsx src/components/feedback/__tests__/BrandBootLoader.test.tsx src/components/feedback/__tests__/brandBootLoaderCss.test.ts src/routes/__tests__/__root.test.tsx --silent=true
npx eslint --max-warnings=0 src/app/hydration.ts src/AppProviders.tsx src/__tests__/AppProviders.closure.test.tsx src/components/feedback/BrandBootLoader.tsx src/components/feedback/brandBootLoaderCss.ts src/components/feedback/__tests__/BrandBootLoader.test.tsx src/components/feedback/__tests__/brandBootLoaderCss.test.ts src/routes/__root.tsx src/routes/__tests__/__root.test.tsx tests/e2e/brand-boot-loader.spec.ts
npx tsc --noEmit
npm run build
npx playwright test tests/e2e/brand-boot-loader.spec.ts --project=chromium --workers=1
cd ..
git diff --check
~~~

Expected: all targeted unit tests, formatting, lint, typecheck, production build, and Chromium browser checks pass.

- [ ] **Step 5: Inspect the generated shell and animation contract**

Run:

~~~powershell
cd frontend
$shell = @(
  '.output/public/_shell.html',
  '.output/public/index.html',
  'dist/client/_shell.html',
  'dist/client/index.html'
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $shell) { throw 'Generated shell HTML not found' }
rg -n 'data-brand-boot-loader|brand-boot-loader-mark-exit|__CSP_NONCE__|<script' $shell
cd ..
~~~

Expected: loader markup and critical keyframes occur inline; generated scripts retain CSP nonce placeholders; no logo image, iframe, external loader stylesheet, or loader script request exists.

- [ ] **Step 6: Commit the browser regression test, verify scope, and publish**

~~~powershell
git add -- frontend/tests/e2e/brand-boot-loader.spec.ts
git diff --cached --check
git commit -m "test: cover application logo loader"
git status --short
git log -5 --oneline
git push origin egorribun
$local = (git rev-parse HEAD).Trim()
$remote = (git ls-remote origin refs/heads/egorribun).Split("`t")[0]
if ($local -ne $remote) { throw "Remote egorribun does not match local HEAD" }
~~~

Expected: only logo-loader work is present in the new commits; the two pre-existing unrelated files remain uncommitted and untouched; remote `egorribun` equals local `HEAD`.

## Final acceptance audit

- [ ] The SSR shell contains the loader before `#root` and hydrates without React #418 or recoverable errors.
- [ ] Exact paths and colors match the source; no rocking or animated transform exists.
- [ ] A slow load reaches a 2.5-second static full-logo hold inside each six-second cycle.
- [ ] Both colored halves fade through the common mark opacity.
- [ ] `Загрузка` remains visible when mark opacity is zero and through the reset gap.
- [ ] Hydration exits the whole overlay immediately and removes it within 600 ms.
- [ ] Reduced motion, hidden-tab pause/resume, StrictMode, pre-fired hydration, transition fallback, and the real-browser CSS-only 12-second failsafe are covered.
- [ ] Light/dark and 320×568, 568×320, 768×1024, 1440×900, and 3840×2160 layouts have no clipping or overflow.
- [ ] The production shell preserves CSP nonce placeholders and adds no runtime dependency or network asset.
- [ ] The standalone HTML and application loader share persistent-status behavior.
- [ ] All targeted tests, lint, typecheck, build, browser checks, `git diff --check`, commit, push, and remote-SHA verification succeed.
