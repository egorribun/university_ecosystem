import type { ReactNode } from "react"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Home } from "lucide-react"
import type { NavigationItem } from "@/config/navigation"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const state = vi.hoisted(() => ({
  namespaces: [] as unknown[],
}))

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>()
  return {
    ...actual,
    useTranslation: (namespaces?: unknown) => {
      state.namespaces.push(namespaces)
      return { t: (key: string) => key }
    },
  }
})

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type Props = Record<string, unknown> & { children?: ReactNode }
  const motionOnly = new Set(["initial", "animate", "exit", "transition", "whileTap"])
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const Motion = React.forwardRef<HTMLElement, Props>(function Motion({ children, ...props }, ref) {
    const tag = (props["data-motion-tag"] as string | undefined) ?? "div"
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(props)) {
      if (key === "data-motion-tag" || motionOnly.has(key)) continue
      cleaned[key] = value
    }
    return React.createElement(
      tag,
      {
        ...cleaned,
        ref,
        "data-motion-initial": serialise(props.initial),
        "data-motion-animate": serialise(props.animate),
        "data-motion-exit": serialise(props.exit),
        "data-motion-transition": serialise(props.transition),
        "data-motion-while-tap": serialise(props.whileTap),
      },
      children as React.ReactNode
    )
  })
  const motion = new Proxy(
    {},
    {
      get: (_target, key) =>
        typeof key === "string"
          ? React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
              return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
            })
          : undefined,
    }
  )
  return {
    m: motion,
    motion,
    LazyMotion: ({ children }: { children?: ReactNode }) => <>{children}</>,
    domAnimation: {},
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

import { NavbarOverflowMenu } from "@/components/navbar/NavbarOverflowMenu"

const items: NavigationItem[] = [
  { to: "/news", label: "News", icon: Home },
  { to: "/events", label: "Events", icon: Home },
]

const extraRoutes = [
  { path: "/news", Component: () => <div>News page</div> },
  { path: "/events", Component: () => <div>Events page</div> },
]

const renderMenu = async (overrides: Partial<Parameters<typeof NavbarOverflowMenu>[0]> = {}) => {
  const props = {
    items,
    isActive: () => false,
    go: vi.fn(),
    prefersReducedMotion: false,
    isCompact: false,
    ...overrides,
  }
  const view = await renderWithRouter({
    ui: () => <NavbarOverflowMenu {...props} />,
    extraRoutes,
    authProvider: false,
  })
  return { props, view }
}

beforeEach(() => {
  state.namespaces.length = 0
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NavbarOverflowMenu mutation contract", () => {
  it("keeps labels, aria state and reduced-motion transitions observable", async () => {
    const { view } = await renderMenu({ prefersReducedMotion: true })
    expect(state.namespaces).toContainEqual(undefined)
    const trigger = screen.getByRole("button", { name: "navigation:aria.overflowMenu" })
    expect(trigger).toHaveAttribute("aria-haspopup", "menu")
    expect(trigger).toHaveAttribute("aria-controls", "navbar-overflow-menu")
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).toHaveAttribute("data-motion-while-tap", "undefined")
    expect(trigger).toHaveAttribute("data-motion-transition", JSON.stringify({ duration: 0 }))

    await userEvent.click(trigger)
    const menu = screen.getByRole("menu", { name: "navigation:aria.overflowMenu" })
    expect(menu).toHaveAttribute(
      "data-motion-initial",
      JSON.stringify({ opacity: 0, scale: 0.95, y: -4 })
    )
    expect(menu).toHaveAttribute(
      "data-motion-animate",
      JSON.stringify({ opacity: 1, scale: 1, y: 0 })
    )
    expect(menu).toHaveAttribute(
      "data-motion-exit",
      JSON.stringify({ opacity: 0, scale: 0.95, y: -4 })
    )
    expect(menu).toHaveAttribute("data-motion-transition", JSON.stringify({ duration: 0 }))
    expect(screen.getAllByRole("menuitem")).toHaveLength(2)
    expect(
      screen.getAllByRole("menuitem").every((item) => item.getAttribute("tabindex") === "-1")
    ).toBe(true)
    view.unmount()
  })

  it("wraps recognized keyboard navigation and ignores keys without a next item", async () => {
    const { view } = await renderMenu({ items: [items[0]!] })
    const trigger = screen.getByRole("button", { name: "navigation:aria.overflowMenu" })
    await userEvent.click(trigger)
    const menu = screen.getByRole("menu")
    const item = screen.getByRole("menuitem", { name: "News" })
    expect(item).toHaveFocus()

    const unrelated = new KeyboardEvent("keydown", {
      key: "PageDown",
      bubbles: true,
      cancelable: true,
    })
    menu.dispatchEvent(unrelated)
    expect(unrelated.defaultPrevented).toBe(false)
    expect(menu).toBeInTheDocument()

    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    menu.dispatchEvent(enter)
    expect(enter.defaultPrevented).toBe(false)
    expect(menu).toBeInTheDocument()

    const arrowDown = new KeyboardEvent("keydown", {
      key: "ArrowDown",
      bubbles: true,
      cancelable: true,
    })
    menu.dispatchEvent(arrowDown)
    expect(arrowDown.defaultPrevented).toBe(true)
    expect(item).toHaveFocus()

    const arrowUp = new KeyboardEvent("keydown", {
      key: "ArrowUp",
      bubbles: true,
      cancelable: true,
    })
    menu.dispatchEvent(arrowUp)
    expect(arrowUp.defaultPrevented).toBe(true)
    expect(item).toHaveFocus()
    view.unmount()
  })

  it("removes outside and Escape listeners when the menu closes", async () => {
    const add = vi.spyOn(document, "addEventListener")
    const remove = vi.spyOn(document, "removeEventListener")
    const { view } = await renderMenu()
    const trigger = screen.getByRole("button", { name: "navigation:aria.overflowMenu" })
    await userEvent.click(trigger)
    expect(add.mock.calls.some(([type]) => type === "pointerdown")).toBe(true)
    expect(add.mock.calls.some(([type]) => type === "keydown")).toBe(true)

    await userEvent.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
    expect(remove.mock.calls.some(([type]) => type === "pointerdown")).toBe(true)
    expect(remove.mock.calls.some(([type]) => type === "keydown")).toBe(true)
    view.unmount()
  })
})
