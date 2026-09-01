import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

type MotionProps = Record<string, unknown> & { children?: unknown }
type FocusTrapOptions = { active: boolean; onDeactivate?: () => void }

const testState = vi.hoisted(() => ({
  prefersReduced: true,
  mediaQueries: [] as string[],
  translationNamespaces: [] as string[],
  translationKeys: [] as string[],
  motionCalls: [] as MotionProps[],
  focusTrapOptions: [] as FocusTrapOptions[],
}))

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const captureMotionDiv = (props: MotionProps) => {
    testState.motionCalls.push(props)
    return base.m.div(props)
  }

  return {
    ...base,
    m: { div: captureMotionDiv },
    motion: { div: captureMotionDiv },
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: (namespace: string) => {
    testState.translationNamespaces.push(namespace)
    return {
      t: (key: string) => {
        testState.translationKeys.push(key)
        return key
      },
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    testState.mediaQueries.push(query)
    return testState.prefersReduced
  },
}))
vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: FocusTrapOptions) => {
    testState.focusTrapOptions.push(options)
    return { current: null }
  },
}))

import { MapShortcutsOverlay } from "@/components/map/MapShortcutsOverlay"

const baseProps = { open: true, onClose: vi.fn() }

afterEach(() => {
  testState.prefersReduced = true
  testState.mediaQueries.length = 0
  testState.translationNamespaces.length = 0
  testState.translationKeys.length = 0
  testState.motionCalls.length = 0
  testState.focusTrapOptions.length = 0
})

describe("MapShortcutsOverlay", () => {
  it("renders nothing when closed", () => {
    render(<MapShortcutsOverlay {...baseProps} open={false} />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("renders the shortcuts dialog with title and shortcut rows when open", () => {
    render(<MapShortcutsOverlay {...baseProps} />)
    expect(screen.getByRole("dialog", { name: "shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "shortcuts.title" })).toBeInTheDocument()
    expect(screen.getByText("shortcuts.buildings")).toBeInTheDocument()
    expect(screen.getByText("shortcuts.zoom")).toBeInTheDocument()
    expect(screen.getByText("F")).toBeInTheDocument()
  })

  it("uses the map namespace and reduced-motion media query contract", () => {
    render(<MapShortcutsOverlay {...baseProps} />)

    expect(testState.translationNamespaces).toEqual(["map"])
    expect(testState.mediaQueries).toEqual(["(prefers-reduced-motion: reduce)"])
    expect(testState.translationKeys).toContain("shortcuts.title")
    expect(testState.translationKeys).toContain("sidebar.close")
  })

  it("fires onClose from the close button", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<MapShortcutsOverlay {...baseProps} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "sidebar.close" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("fires onClose when the focus trap deactivates on Escape", () => {
    const onClose = vi.fn()
    render(<MapShortcutsOverlay {...baseProps} onClose={onClose} />)

    const options = testState.focusTrapOptions.at(-1)
    expect(options?.active).toBe(true)
    options?.onDeactivate?.()
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("updates the focus-trap callback when onClose changes", () => {
    const firstOnClose = vi.fn()
    const nextOnClose = vi.fn()
    const { rerender } = render(<MapShortcutsOverlay open onClose={firstOnClose} />)

    rerender(<MapShortcutsOverlay open onClose={nextOnClose} />)
    const options = testState.focusTrapOptions.at(-1)
    expect(options?.onDeactivate).toBeTypeOf("function")
    options?.onDeactivate?.()

    expect(firstOnClose).not.toHaveBeenCalled()
    expect(nextOnClose).toHaveBeenCalledOnce()
  })

  it("passes complete entrance and exit motion contracts", () => {
    testState.prefersReduced = false

    render(<MapShortcutsOverlay {...baseProps} />)

    expect(screen.getByRole("dialog", { name: "shortcuts.title" })).toBeInTheDocument()

    const outerMotion = testState.motionCalls.find((call) =>
      String(call.className).includes("fixed inset-0")
    )
    const dialogMotion = testState.motionCalls.find((call) => call.role === "dialog")

    expect(outerMotion).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.2 },
    })
    expect(dialogMotion).toMatchObject({
      initial: { scale: 0.95, y: 8 },
      animate: { scale: 1, y: 0 },
      exit: { scale: 0.95, y: 8 },
      transition: { type: "spring", stiffness: 400, damping: 30 },
    })
  })

  it("uses reduced-motion-safe dialog transitions", () => {
    testState.prefersReduced = true

    render(<MapShortcutsOverlay {...baseProps} />)

    const dialogMotion = testState.motionCalls.find((call) => call.role === "dialog")
    expect(dialogMotion).toMatchObject({
      initial: false,
      animate: { scale: 1, y: 0 },
      exit: { opacity: 0 },
      transition: { duration: 0 },
    })
  })

  it("keeps keyboard shortcuts accessible as a definition list", () => {
    render(<MapShortcutsOverlay {...baseProps} />)

    const dialog = screen.getByRole("dialog", { name: "shortcuts.title" })
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(dialog.querySelectorAll("dt")).toHaveLength(9)
    expect(dialog.querySelectorAll("dd")).toHaveLength(9)
    expect(Array.from(dialog.querySelectorAll("kbd"), (key) => key.textContent)).toEqual([
      "1",
      "–",
      "9",
      "↑",
      "↓",
      "←",
      "→",
      "+",
      "−",
      "⇧+←",
      "⇧+→",
      "⇧+↑",
      "⇧+↓",
      "F",
      "/",
      "Esc",
      "?",
    ])

    const backdrop = dialog.parentElement?.querySelector('[aria-hidden="true"]')
    expect(backdrop).toBeInTheDocument()
    expect(backdrop).toHaveClass("absolute", "inset-0")
  })
})
