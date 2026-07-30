import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, renderHook, act } from "@testing-library/react"
import { useState, memo } from "react"
import { useDebounced } from "../../hooks/useDebounced"
import { NewsCardList } from "../dashboard/NewsCardList"
import { ClockWidget } from "../dashboard/ClockWidget"
import { Card } from "../ui/Card"
import { ContentCard } from "../ui/ContentCard"

// Mock router / translation hooks required by dashboard components
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: any) => <a {...props}>{children}</a>,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}))

describe("Milestone 2 Component Re-render & Debounce Challenge Suite", () => {
  describe("1. Empirical verification of useDebounced presets", () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it("verifies 'search' preset delays exactly 200ms", () => {
      const { result, rerender } = renderHook(({ val }) => useDebounced(val, "search"), {
        initialProps: { val: "search_initial" },
      })
      expect(result.current).toBe("search_initial")

      rerender({ val: "search_updated" })
      act(() => {
        vi.advanceTimersByTime(199)
      })
      expect(result.current).toBe("search_initial") // must NOT update at 199ms

      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe("search_updated") // MUST update at 200ms
    })

    it("verifies 'default' preset delays exactly 300ms", () => {
      const { result, rerender } = renderHook(({ val }) => useDebounced(val, "default"), {
        initialProps: { val: "def_initial" },
      })
      expect(result.current).toBe("def_initial")

      rerender({ val: "def_updated" })
      act(() => {
        vi.advanceTimersByTime(299)
      })
      expect(result.current).toBe("def_initial") // must NOT update at 299ms

      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe("def_updated") // MUST update at 300ms
    })

    it("verifies 'validation' preset delays exactly 350ms", () => {
      const { result, rerender } = renderHook(({ val }) => useDebounced(val, "validation"), {
        initialProps: { val: "val_initial" },
      })
      expect(result.current).toBe("val_initial")

      rerender({ val: "val_updated" })
      act(() => {
        vi.advanceTimersByTime(349)
      })
      expect(result.current).toBe("val_initial") // must NOT update at 349ms

      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(result.current).toBe("val_updated") // MUST update at 350ms
    })

    it("prevents state thrashing under rapid input updates", () => {
      const { result, rerender } = renderHook(({ val }) => useDebounced(val, "search"), {
        initialProps: { val: "a" },
      })

      // Simulate 5 rapid keystrokes within 50ms intervals
      for (const char of ["b", "c", "d", "e", "final"]) {
        rerender({ val: char })
        act(() => {
          vi.advanceTimersByTime(50)
        })
        expect(result.current).toBe("a") // Intermediate updates remain suppressed
      }

      // After final keystroke + full 200ms
      act(() => {
        vi.advanceTimersByTime(200)
      })
      expect(result.current).toBe("final")
    })
  })

  describe("2. Component Memoization & Re-render Isolation", () => {
    it("verifies React.memo wrapper presence on target components", () => {
      // React.memo components have $$typeof Symbol(react.memo)
      expect((NewsCardList as any).$$typeof?.toString()).toContain("react.memo")
      expect((ClockWidget as any).$$typeof?.toString()).toContain("react.memo")
      expect((Card as any).$$typeof?.toString()).toContain("react.memo")
      expect((ContentCard as any).$$typeof?.toString()).toContain("react.memo")
    })

    it("prevents re-rendering of memoized child when parent state changes but child props are identical", () => {
      let childRenderCount = 0

      const MemoizedChild = memo(function TestChild({ title }: { title: string }) {
        childRenderCount++
        return <div>{title}</div>
      })

      function ParentComponent() {
        const [counter, setCounter] = useState(0)
        return (
          <div>
            <button onClick={() => setCounter((c) => c + 1)}>Count: {counter}</button>
            <MemoizedChild title="Static Title" />
          </div>
        )
      }

      const { getByText } = render(<ParentComponent />)
      expect(childRenderCount).toBe(1)

      // Trigger parent state change
      act(() => {
        getByText("Count: 0").click()
      })
      expect(getByText("Count: 1")).toBeInTheDocument()

      // Child must NOT re-render because props are identical
      expect(childRenderCount).toBe(1)

      // Trigger second parent state change
      act(() => {
        getByText("Count: 1").click()
      })
      expect(childRenderCount).toBe(1)
    })
  })
})
