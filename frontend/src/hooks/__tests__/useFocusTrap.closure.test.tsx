import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  activate: vi.fn(),
  deactivate: vi.fn(),
  options: undefined as
    | {
        fallbackFocus: HTMLElement | (() => HTMLElement)
        initialFocus?: false
        onDeactivate: () => void
        allowOutsideClick: boolean
        returnFocusOnDeactivate: boolean
      }
    | undefined,
}))

vi.mock("focus-trap", () => ({
  createFocusTrap: vi.fn(
    (
      _container: HTMLElement,
      options: NonNullable<typeof mocks.options>
    ) => {
      mocks.options = options
      return {
        activate: mocks.activate,
        deactivate: (...args: unknown[]) => {
          mocks.deactivate(...args)
          options.onDeactivate()
        },
      }
    }
  ),
}))

import useFocusTrap from "@/hooks/useFocusTrap"

function TrapHarness({
  active,
  tabIndex = -1,
  initialFocus,
  fallbackFocus,
  onDeactivate,
}: {
  active: boolean
  tabIndex?: number
  initialFocus?: false
  fallbackFocus?: HTMLElement
  onDeactivate?: () => void
}) {
  const ref = useFocusTrap<HTMLDivElement>({
    active,
    initialFocus,
    fallbackFocus,
    onDeactivate,
    allowOutsideClick: false,
    returnFocus: false,
  })
  return <div ref={ref} tabIndex={tabIndex} />
}

describe("useFocusTrap deterministic lifecycle", () => {
  it("activates with default fallback focus and cleans up on an active-state change", () => {
    const onDeactivate = vi.fn()
    const { container, rerender } = render(
      <TrapHarness active initialFocus={false} onDeactivate={onDeactivate} />
    )

    expect(mocks.activate).toHaveBeenCalledOnce()
    expect(mocks.options?.initialFocus).toBe(false)
    expect(mocks.options?.allowOutsideClick).toBe(false)
    expect(mocks.options?.returnFocusOnDeactivate).toBe(false)
    const fallback = mocks.options?.fallbackFocus as () => HTMLElement
    expect(fallback()).toBe(container.firstElementChild)

    rerender(<TrapHarness active={false} onDeactivate={onDeactivate} />)
    expect(mocks.deactivate).toHaveBeenCalledWith()

    mocks.options?.onDeactivate()
    expect(onDeactivate).toHaveBeenCalledOnce()
  })

  it("honors an explicit fallback target and cleans up the active trap", () => {
    const fallback = document.createElement("button")
    const { unmount } = render(
      <TrapHarness active tabIndex={0} fallbackFocus={fallback} />
    )

    expect(mocks.options?.fallbackFocus).toBe(fallback)
    expect(mocks.options?.initialFocus).toBeUndefined()
    unmount()
    expect(mocks.deactivate).toHaveBeenCalled()
  })
})
