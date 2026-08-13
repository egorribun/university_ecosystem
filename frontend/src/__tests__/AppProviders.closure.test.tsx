import { StrictMode, type ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { APP_HYDRATED_EVENT } from "@/app/hydration"

const provider = (name: string) => {
  const TestProvider = ({ children }: { children?: ReactNode }) => (
    <div data-provider={name}>{children}</div>
  )
  TestProvider.displayName = `TestProvider(${name})`
  return TestProvider
}

vi.mock("framer-motion", () => ({
  LazyMotion: ({ children }: { children?: ReactNode }) => (
    <div data-testid="lazy-motion">{children}</div>
  ),
  MotionConfig: ({ children, reducedMotion }: { children?: ReactNode; reducedMotion?: string }) => (
    <div data-testid="motion-config" data-reduced-motion={reducedMotion}>
      {children}
    </div>
  ),
  domAnimation: {},
}))

vi.mock("@/components/feedback/ErrorBoundary", () => ({
  default: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))
vi.mock("@/components/ui/LiveRegionProvider", () => ({
  LiveRegionProvider: provider("live-region"),
}))
vi.mock("@/contexts/AppShellContext", () => ({
  AppShellProvider: provider("app-shell"),
}))
vi.mock("@/contexts/AuthContext", () => ({
  AuthProvider: provider("auth"),
}))
vi.mock("@/hooks/useChatWebSocket", () => ({
  WebSocketProvider: provider("websocket"),
}))
vi.mock("@/contexts/MessengerContext", () => ({
  MessengerProvider: provider("messenger"),
}))
vi.mock("@/contexts/LanguageContext", () => ({
  LanguageProvider: provider("language"),
}))
vi.mock("@/components/ui/GlobalHapticsListener", () => ({
  GlobalHapticsListener: () => <span data-testid="global-haptics" />,
}))
vi.mock("@/db/RxDBContext", () => ({
  RxDBProvider: provider("rxdb"),
}))

const loadProviders = async (lhci: string) => {
  vi.resetModules()
  vi.stubEnv("VITE_LHCI", lhci)
  return (await import("@/AppProviders")).AppProviders
}

beforeEach(() => {
  delete window.__APP_HYDRATED
  vi.unstubAllEnvs()
})

describe("AppProviders closure", () => {
  it("composes every provider and marks the client as hydrated in normal mode", async () => {
    const AppProviders = await loadProviders("false")

    render(
      <AppProviders>
        <span>application child</span>
      </AppProviders>
    )

    expect(screen.getByText("application child")).toBeInTheDocument()
    expect(screen.getByTestId("motion-config")).toHaveAttribute("data-reduced-motion", "user")
    expect(screen.getByTestId("global-haptics")).toBeInTheDocument()
    for (const name of [
      "language",
      "rxdb",
      "live-region",
      "app-shell",
      "auth",
      "websocket",
      "messenger",
    ]) {
      expect(document.querySelector(`[data-provider="${name}"]`)).toBeInTheDocument()
    }
    await waitFor(() => expect(window.__APP_HYDRATED).toBe(true))
  })

  it("uses always-reduced motion for Lighthouse CI runs", async () => {
    const AppProviders = await loadProviders("true")

    render(
      <AppProviders>
        <span>lhci child</span>
      </AppProviders>
    )

    expect(screen.getByText("lhci child")).toBeInTheDocument()
    expect(screen.getByTestId("motion-config")).toHaveAttribute("data-reduced-motion", "always")
    await waitFor(() => expect(window.__APP_HYDRATED).toBe(true))
  })

  it("publishes hydration exactly once, including under StrictMode effects", async () => {
    const AppProviders = await loadProviders("false")
    const onHydrated = vi.fn()
    window.addEventListener(APP_HYDRATED_EVENT, onHydrated)

    render(
      <StrictMode>
        <AppProviders>
          <span>strict application child</span>
        </AppProviders>
      </StrictMode>
    )

    await waitFor(() => expect(window.__APP_HYDRATED).toBe(true))
    expect(onHydrated).toHaveBeenCalledTimes(1)
    window.removeEventListener(APP_HYDRATED_EVENT, onHydrated)
  })
})
