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
        escapeDeactivates: boolean
      }
    | undefined,
}))

vi.mock("focus-trap", () => ({
  createFocusTrap: vi.fn((_container: HTMLElement, options: NonNullable<typeof mocks.options>) => {
    mocks.options = options
    return {
      activate: mocks.activate,
      deactivate: (...args: unknown[]) => {
        mocks.deactivate(...args)
        options.onDeactivate()
      },
    }
  }),
}))

import useFocusTrap from "@/hooks/useFocusTrap"

function TrapHarness({
  active,
  tabIndex = -1,
  initialFocus,
  fallbackFocus,
  onDeactivate,
  escapeDeactivates,
}: {
  active: boolean
  tabIndex?: number
  initialFocus?: false
  fallbackFocus?: HTMLElement
  onDeactivate?: () => void
  escapeDeactivates?: boolean
}) {
  const ref = useFocusTrap<HTMLDivElement>({
    active,
    initialFocus,
    fallbackFocus,
    onDeactivate,
    allowOutsideClick: false,
    returnFocus: false,
    escapeDeactivates,
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
      <TrapHarness active tabIndex={0} fallbackFocus={fallback} escapeDeactivates={false} />
    )

    expect(mocks.options?.fallbackFocus).toBe(fallback)
    expect(mocks.options?.initialFocus).toBeUndefined()
    expect(mocks.options?.escapeDeactivates).toBe(false)
    unmount()
    expect(mocks.deactivate).toHaveBeenCalled()
  })

  it("preserves an already keyboard-focusable container in the default fallback", () => {
    const { container } = render(<TrapHarness active tabIndex={0} />)

    const fallback = mocks.options?.fallbackFocus as () => HTMLElement
    const target = fallback()

    expect(target).toBe(container.firstElementChild)
    expect(target.tabIndex).toBe(0)
  })

  it("refreshes callback and initial-focus refs when props change", () => {
    const firstDeactivate = vi.fn()
    const nextDeactivate = vi.fn()
    const { rerender } = render(
      <TrapHarness active initialFocus={false} onDeactivate={firstDeactivate} />
    )

    // The trap itself is intentionally not recreated for callback changes;
    // the ref-sync effect must still make its existing callback current.
    rerender(<TrapHarness active initialFocus={undefined} onDeactivate={nextDeactivate} />)
    mocks.options?.onDeactivate()
    expect(firstDeactivate).not.toHaveBeenCalled()
    expect(nextDeactivate).toHaveBeenCalledOnce()

    // Re-activating after the prop update must omit initialFocus entirely when
    // it is undefined (rather than passing an own property with undefined).
    rerender(<TrapHarness active={false} initialFocus={undefined} onDeactivate={nextDeactivate} />)
    rerender(<TrapHarness active initialFocus={undefined} onDeactivate={nextDeactivate} />)
    expect(Object.prototype.hasOwnProperty.call(mocks.options, "initialFocus")).toBe(false)
  })

  it("deactivates safely when no callback is supplied", () => {
    const { unmount } = render(<TrapHarness active />)
    expect(() => unmount()).not.toThrow()
  })
})
