import { useState } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import postcss from "postcss"
import { describe, expect, it, vi } from "vitest"

import { Button } from "@/components/ui/Button"
import compiledCss from "@/styles/tailwind.css?inline"
import { expectNoRouterNavigation } from "@/tests/helpers/expectNoRouterNavigation"

const stylesheet = postcss.parse(compiledCss)

function expectUtility(
  element: HTMLElement,
  className: string,
  property: string,
  value: string,
  pseudoClass = ""
) {
  expect(element).toHaveClass(className)
  const declarations: string[] = []
  stylesheet.walkRules((rule) => {
    if (rule.selector === `.${CSS.escape(className)}${pseudoClass}`) {
      rule.walkDecls(property, (declaration) => {
        declarations.push(declaration.value)
      })
    }
  })
  expect(declarations).toContain(value)
}

describe("Button semantic CSS", () => {
  it.each([undefined, "gradient"] as const)(
    "uses the existing hover opacity token for variant %s",
    (variant) => {
      render(<Button variant={variant}>Continue</Button>)
      const button = screen.getByRole("button", { name: "Continue" })
      expect(button).toBeEnabled()
      expectUtility(
        button,
        "hover:opacity-(--opacity-heavy)",
        "opacity",
        "var(--opacity-heavy)",
        ":hover"
      )
    }
  )

  it.each(["disabled", "loading"] as const)(
    "exposes the neutral solid background while %s and restores the enabled gradient",
    (state) => {
      const { rerender } = render(<Button {...{ [state]: true }}>Save changes</Button>)
      const button = screen.getByRole("button", { name: "Save changes" })
      expect(button).toBeDisabled()
      expectUtility(button, "disabled:bg-none", "background-image", "none", ":disabled")
      expectUtility(
        button,
        "disabled:bg-(--border-subtle)",
        "background-color",
        "var(--border-subtle)",
        ":disabled"
      )

      rerender(<Button>Save changes</Button>)
      expect(button).toBeEnabled()
      expect(button.matches(":disabled")).toBe(false)
      expectUtility(
        button,
        "bg-(image:--gradient-brand)",
        "background-image",
        "var(--gradient-brand)"
      )
    }
  )

  it.each([undefined, "gradient"] as const)(
    "renders the existing brand gradient for variant %s",
    (variant) => {
      render(<Button variant={variant}>Continue</Button>)
      const button = screen.getByRole("button", { name: "Continue" })
      expectUtility(
        button,
        "bg-(image:--gradient-brand)",
        "background-image",
        "var(--gradient-brand)"
      )
      expectUtility(button, "text-inverse-text", "color", "var(--color-inverse-text)")
    }
  )

  it.each([
    ["sm", "--fs-sm"],
    ["md", "--fs-base"],
    ["lg", "--fs-lg"],
  ] as const)("keeps the solid text color when applying %s font sizing", (size, fontToken) => {
    render(<Button size={size}>Save changes</Button>)
    const button = screen.getByRole("button", { name: "Save changes" })
    expectUtility(button, `text-(length:${fontToken})`, "font-size", `var(${fontToken})`)
    expectUtility(button, "text-inverse-text", "color", "var(--color-inverse-text)")
  })

  it.each(["disabled", "loading"] as const)(
    "uses the existing opacity token while %s and restores the enabled treatment",
    (state) => {
      const { rerender } = render(<Button {...{ [state]: true }}>Save changes</Button>)
      const button = screen.getByRole("button", { name: "Save changes" })
      expectUtility(button, "opacity-(--opacity-strong)", "opacity", "var(--opacity-strong)")
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute("aria-disabled", "true")

      rerender(<Button>Save changes</Button>)
      expect(button).not.toHaveClass("opacity-(--opacity-strong)")
      expect(button).toBeEnabled()
    }
  )
})

describe("Button link activation", () => {
  it.each(["disabled", "loading"] as const)(
    "cancels native keyboard navigation while %s and allows it after enabling",
    async (state) => {
      const user = userEvent.setup()
      const originalUrl = window.location.href
      const originalState = window.history.state
      const onClick = vi.fn()
      const activations: MouseEvent[] = []
      const observeClick = (event: MouseEvent) => {
        activations.push(event)
      }
      const { rerender, unmount } = render(
        <Button as="a" href="#button-native-action" {...{ [state]: true }} onClick={onClick}>
          View details
        </Button>
      )
      document.addEventListener("click", observeClick)
      try {
        const link = screen.getByRole("link", { name: "View details" })
        expect(link).toHaveAttribute("aria-disabled", "true")
        expect(link).not.toHaveAttribute("disabled")
        await user.tab()
        expect(link).toHaveFocus()
        await user.keyboard("{Enter}")
        expect(onClick).not.toHaveBeenCalled()
        expect(activations).toHaveLength(1)
        // Drain an unexpected native navigation before failing, so even a red
        // regression run cannot leak a pending location change into another test.
        if (!activations[0]?.defaultPrevented) {
          await waitFor(() => expect(window.location.hash).toBe("#button-native-action"))
        }
        expect(activations[0]?.defaultPrevented).toBe(true)
        expect(window.location.href).toBe(originalUrl)

        rerender(
          <Button as="a" href="#button-native-action" onClick={onClick}>
            View details
          </Button>
        )
        expect(link).not.toHaveAttribute("aria-disabled")
        expect(link).not.toHaveClass("pointer-events-none")
        expect(link).toHaveFocus()
        await user.keyboard("{Enter}")
        await waitFor(() => expect(window.location.hash).toBe("#button-native-action"))
        expect(onClick).toHaveBeenCalledOnce()
        expect(activations).toHaveLength(2)
        expect(activations[1]?.defaultPrevented).toBe(false)
      } finally {
        try {
          document.removeEventListener("click", observeClick)
          unmount()
        } finally {
          window.history.replaceState(originalState, "", originalUrl)
        }
      }
    }
  )

  it.each(["disabled", "loading"] as const)(
    "prevents router navigation while %s and preserves enabled Link behavior",
    async (state) => {
      const onClick = vi.fn()
      function NavigationFixture() {
        const [blocked, setBlocked] = useState(true)
        return (
          <>
            <Button as={Link} to="/news" {...{ [state]: blocked }} onClick={onClick}>
              View news
            </Button>
            <button onClick={() => setBlocked(false)}>Enable link</button>
            <Outlet />
          </>
        )
      }
      const root = createRootRoute({ component: NavigationFixture })
      const home = createRoute({
        getParentRoute: () => root,
        path: "/",
        component: () => <p>Home</p>,
      })
      const destination = createRoute({
        getParentRoute: () => root,
        path: "/news",
        component: () => <p>News destination</p>,
      })
      const router = createRouter({
        routeTree: root.addChildren([home, destination]),
        history: createMemoryHistory({ initialEntries: ["/"] }),
      })
      await router.load()
      const { unmount } = render(<RouterProvider router={router as never} />)
      try {
        const link = screen.getByRole("link", { name: "View news" })
        await expectNoRouterNavigation(router, () => fireEvent.click(link))
        expect(onClick).not.toHaveBeenCalled()
        expect(screen.getByText("Home")).toBeInTheDocument()

        fireEvent.click(screen.getByRole("button", { name: "Enable link" }))
        fireEvent.click(link)
        expect(await screen.findByText("News destination")).toBeInTheDocument()
        expect(router.state.location.pathname).toBe("/news")
        expect(onClick).toHaveBeenCalledOnce()
      } finally {
        unmount()
      }
    }
  )
})
