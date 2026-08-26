/**
 * Coverage tests for NavbarOverflowMenu (testing session 9).
 *
 * Previously ~9% covered (only the module import). Exercises: empty-items
 * null render, open/close toggle, Escape + outside-pointerdown close,
 * item click → go() + close, active styling.
 */
import { fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { Home } from "lucide-react"

import { NavbarOverflowMenu } from "@/components/navbar/NavbarOverflowMenu"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import type { NavigationItem } from "@/config/navigation"

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
    prefersReducedMotion: true,
    isCompact: false,
    ...overrides,
  }
  await renderWithRouter({
    ui: () => <NavbarOverflowMenu {...props} />,
    extraRoutes,
    authProvider: false,
  })
  return props
}

describe("NavbarOverflowMenu", () => {
  it("renders nothing when items list is empty", async () => {
    await renderMenu({ items: [] })
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("opens the menu on trigger click and lists items", async () => {
    await renderMenu()
    const trigger = screen.getByRole("button")
    expect(trigger).toHaveAccessibleName("More navigation")
    expect(trigger).toHaveAttribute("aria-haspopup", "menu")
    expect(trigger).toHaveAttribute("aria-controls", "navbar-overflow-menu")
    expect(trigger).toHaveClass("size-11")
    expect(trigger).toHaveAttribute("aria-expanded", "false")

    await userEvent.click(trigger)

    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("menu")).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "News" })).toHaveFocus()
    expect(screen.getByRole("menuitem", { name: "Events" })).toBeInTheDocument()
  })

  it("supports roving keyboard focus and restores the trigger on Escape", async () => {
    const user = userEvent.setup()
    await renderMenu()
    const trigger = screen.getByRole("button")
    await user.click(trigger)

    await user.keyboard("{ArrowDown}")
    expect(screen.getByRole("menuitem", { name: "Events" })).toHaveFocus()
    await user.keyboard("{ArrowUp}")
    expect(screen.getByRole("menuitem", { name: "News" })).toHaveFocus()
    await user.keyboard("{Home}")
    expect(screen.getByRole("menuitem", { name: "News" })).toHaveFocus()
    await user.keyboard("{End}")
    expect(screen.getByRole("menuitem", { name: "Events" })).toHaveFocus()
    await user.keyboard("{Escape}")

    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("closes the menu on second trigger click", async () => {
    await renderMenu()
    const trigger = screen.getByRole("button")
    await userEvent.click(trigger)
    expect(screen.getByRole("menu")).toBeInTheDocument()

    await userEvent.click(trigger)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("invokes go() and closes when an item is clicked", async () => {
    const props = await renderMenu()
    await userEvent.click(screen.getByRole("button"))
    await userEvent.click(screen.getByText("News"))

    expect(props.go).toHaveBeenCalledWith("/news")
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("closes on Escape", async () => {
    await renderMenu()
    await userEvent.click(screen.getByRole("button"))
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("stays open for unrelated document keys", async () => {
    await renderMenu()
    await userEvent.click(screen.getByRole("button"))

    fireEvent.keyDown(document, { key: "Enter" })

    expect(screen.getByRole("menu")).toBeInTheDocument()
  })

  it("closes on outside pointerdown but stays open on inside pointerdown", async () => {
    await renderMenu()
    await userEvent.click(screen.getByRole("button"))
    const menu = screen.getByRole("menu")

    fireEvent.pointerDown(menu)
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.pointerDown(document.body)
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })

  it("marks active items via data-active and highlights the trigger", async () => {
    await renderMenu({ isActive: (to: string) => to === "/news" })
    const trigger = screen.getByRole("button")
    expect(trigger.className).toContain("nav-active")

    await userEvent.click(trigger)
    const newsLink = screen.getByText("News").closest("a")
    const eventsLink = screen.getByText("Events").closest("a")
    expect(newsLink).toHaveAttribute("data-active", "true")
    expect(eventsLink).not.toHaveAttribute("data-active")
  })

  it("respects compact sizing and non-reduced motion props", async () => {
    await renderMenu({ isCompact: true, prefersReducedMotion: false })
    const trigger = screen.getByRole("button")
    expect(trigger.className).toContain("size-11")
    await userEvent.click(trigger)
    expect(screen.getByRole("menu")).toBeInTheDocument()
  })
})
