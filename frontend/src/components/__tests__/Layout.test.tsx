import { act, render, screen } from "@testing-library/react"
import type { HTMLAttributes, ReactNode } from "react"
import { hydrateRoot } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ online: true }))
const translation = vi.hoisted(() => ({
  useTranslation: vi.fn(() => ({ t: (key: string) => key })),
}))

vi.mock("framer-motion", () => {
  const serializeMotionValue = (value: unknown): string | undefined => {
    if (value === undefined) return undefined
    return typeof value === "string" ? value : JSON.stringify(value)
  }

  type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
    children?: ReactNode
    initial?: unknown
    animate?: unknown
    exit?: unknown
    variants?: unknown
  }

  const MotionDiv = ({
    children,
    initial,
    animate,
    exit,
    variants: _variants,
    ...props
  }: MotionDivProps) => (
    <div
      {...props}
      data-motion-initial={serializeMotionValue(initial)}
      data-motion-animate={serializeMotionValue(animate)}
      data-motion-exit={serializeMotionValue(exit)}
    >
      {children}
    </div>
  )

  return {
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    m: { div: MotionDiv },
  }
})
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => state.online }))
vi.mock("react-i18next", () => ({ useTranslation: translation.useTranslation }))

import Layout from "@/components/Layout"

describe("Layout", () => {
  beforeEach(() => {
    state.online = true
    delete window.__APP_HYDRATED
    translation.useTranslation.mockClear()
  })

  afterEach(() => {
    delete window.__APP_HYDRATED
    vi.unstubAllEnvs()
  })

  it("renders online content without an offline warning", () => {
    const { container } = render(
      <Layout className="custom-layout">
        <span>Page content</span>
      </Layout>
    )

    expect(screen.getByText("Page content")).toBeInTheDocument()
    expect(screen.queryByText("offlineIndicator.offline")).not.toBeInTheDocument()
    expect(container.firstElementChild).toHaveClass("custom-layout")
    expect(translation.useTranslation).toHaveBeenCalledWith("system")
  })

  it("announces an offline connection", () => {
    state.online = false
    render(<Layout>Offline page</Layout>)

    expect(screen.getByText("offlineIndicator.offline")).toBeInTheDocument()
  })

  it("keeps the server-rendered shell visible in the Lighthouse preview", () => {
    vi.stubEnv("VITE_LHCI", "true")

    render(
      <Layout>
        <span>Audit content</span>
      </Layout>
    )

    expect(screen.getByText("Audit content")).toBeInTheDocument()
  })

  it("uses the composed entrance for client route mounts after hydration", () => {
    window.__APP_HYDRATED = true
    const route = (name: string) => <Layout key={name}>{name} content</Layout>
    const { container, rerender } = render(route("News"))

    const firstRouteShell = container.firstElementChild
    expect(firstRouteShell).toHaveAttribute("data-motion-initial", "hidden")
    expect(firstRouteShell).toHaveAttribute("data-motion-animate", "visible")
    expect(firstRouteShell).toHaveAttribute("data-motion-exit", "exit")

    rerender(route("Events"))
    const nextRouteShell = container.firstElementChild
    expect(nextRouteShell).toHaveAttribute("data-motion-initial", "hidden")
    expect(nextRouteShell).toHaveAttribute("data-motion-animate", "visible")
    expect(nextRouteShell).toHaveAttribute("data-motion-exit", "exit")
    expect(nextRouteShell).toHaveClass(
      "box-border",
      "min-h-screen",
      "w-full",
      "bg-page",
      "text-text-primary"
    )
  })

  it("keeps SSR and first hydration visible when the sentinel is already published", async () => {
    window.__APP_HYDRATED = true
    const serverMarkup = renderToString(<Layout>Hydrated route</Layout>)

    expect(serverMarkup).toContain('data-motion-initial="false"')
    expect(serverMarkup).toContain("Hydrated route")

    const container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.append(container)
    const recoverableErrors: unknown[] = []
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    let root: ReturnType<typeof hydrateRoot> | undefined

    try {
      await act(async () => {
        root = hydrateRoot(container, <Layout>Hydrated route</Layout>, {
          onRecoverableError: (error) => recoverableErrors.push(error),
        })
      })

      expect(recoverableErrors).toEqual([])
      expect(consoleError).not.toHaveBeenCalled()
      expect(container.querySelector("[data-scroll-root]")).toHaveAttribute(
        "data-motion-initial",
        "hidden"
      )
      expect(container.querySelector("[data-scroll-root]")).toHaveAttribute(
        "data-motion-animate",
        "visible"
      )
    } finally {
      if (root) {
        await act(async () => {
          root?.unmount()
        })
      }
      container.remove()
      consoleError.mockRestore()
    }
  })

  it("disables the entrance animation for Lighthouse audits", () => {
    vi.stubEnv("VITE_LHCI", "true")
    const { container } = render(<Layout>Audit shell</Layout>)

    expect(container.firstElementChild).toHaveAttribute("data-motion-initial", "false")
  })

  it("announces the complete offline banner motion contract", () => {
    state.online = false
    render(<Layout>Offline content</Layout>)
    const banner = screen.getByTestId("offline-banner")

    expect(banner).toHaveAttribute("data-motion-initial", '{"height":0,"opacity":0}')
    expect(banner).toHaveAttribute("data-motion-animate", '{"height":"auto","opacity":1}')
    expect(banner).toHaveAttribute("data-motion-exit", '{"height":0,"opacity":0}')
  })
})
