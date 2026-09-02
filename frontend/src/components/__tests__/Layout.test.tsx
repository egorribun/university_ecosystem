import { render, screen } from "@testing-library/react"
import type { HTMLAttributes, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

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
    translation.useTranslation.mockClear()
  })

  afterEach(() => {
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

  it("uses the composed entrance outside Lighthouse audits", () => {
    const { container } = render(<Layout>Animated content</Layout>)
    const shell = container.firstElementChild

    expect(shell).toHaveAttribute("data-motion-initial", "hidden")
    expect(shell).toHaveAttribute("data-motion-animate", "visible")
    expect(shell).toHaveAttribute("data-motion-exit", "exit")
    expect(shell).toHaveClass(
      "box-border",
      "min-h-screen",
      "w-full",
      "bg-page",
      "text-text-primary"
    )
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
