import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ online: true }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => state.online }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import Layout from "@/components/Layout"

describe("Layout", () => {
  beforeEach(() => {
    state.online = true
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
})
