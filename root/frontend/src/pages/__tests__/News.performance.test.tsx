import { useEffect, type ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { AppShellProvider } from "@/contexts/AppShellContext"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("../../components/NewsCard", () => {
  const MockNewsCard = ({ id }: { id: number }) => (
    <div data-testid="news-card" data-news-id={id}>
      News {id}
    </div>
  )

  MockNewsCard.displayName = "MockNewsCard"

  return {
    __esModule: true,
    default: MockNewsCard,
  }
})

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, role: "admin" },
  }),
}))

const useMediaQueryMock = vi.fn<(query: string) => boolean>(() => false)

vi.mock("@/hooks/useMediaQuery", () => ({
  __esModule: true,
  default: (query: string) => useMediaQueryMock(query),
}))

vi.mock("@/hooks/useNewsFeed", () => ({
  useNewsFeed: vi.fn(),
}))

import News from "../News"
import { useNewsFeed } from "@/hooks/useNewsFeed"

const largeFeed = Array.from({ length: 96 }, (_, index) => ({
  id: index + 1,
  title: `Sample news ${index + 1}`,
  content: `Sample news body ${index + 1}`,
  created_at: new Date(2024, 0, 1 + index).toISOString(),
  image_url: null,
}))

const useNewsFeedMock = vi.mocked(useNewsFeed)

type PortalRegistration = { node: HTMLElement | null; created: boolean }

const ensurePortalElement = (id: string): PortalRegistration => {
  if (typeof document === "undefined") return { node: null, created: false }
  const existing = document.getElementById(id)
  if (existing) return { node: existing, created: false }
  const node = document.createElement("div")
  node.setAttribute("id", id)
  document.body.appendChild(node)
  return { node, created: true }
}

const TailwindPortalProvider = ({ children }: { children: ReactNode }) => {
  useEffect(() => {
    const registrations: PortalRegistration[] = [
      ensurePortalElement("ue-modal-root"),
      ensurePortalElement("ue-toast-root"),
    ]

    return () => {
      registrations.forEach(({ node, created }) => {
        if (created && node?.parentNode) {
          node.parentNode.removeChild(node)
        }
      })
    }
  }, [])

  return <>{children}</>
}

TailwindPortalProvider.displayName = "TailwindPortalProvider"

const setIsMobile = (isMobile: boolean) => {
  useMediaQueryMock.mockImplementation((query) =>
    query === "(max-width:600px)" ? isMobile : false
  )
}

const buildWrapper = (mode: "light" | "dark") => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  const NewsTestWrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <AppShellProvider>
        <LanguageProvider>
          <TailwindPortalProvider>{children}</TailwindPortalProvider>
        </LanguageProvider>
      </AppShellProvider>
    </QueryClientProvider>
  )

  NewsTestWrapper.displayName = `NewsTestWrapper(${mode})`

  return NewsTestWrapper
}

let matchMediaMock: ReturnType<typeof vi.fn>
let originalMatchMedia: typeof window.matchMedia | undefined
let originalRequestIdleCallback: typeof window.requestIdleCallback | undefined
let originalCancelIdleCallback: typeof window.cancelIdleCallback | undefined
let currentMode: "light" | "dark" = "light"

describe("News page feed rendering", () => {
  beforeAll(() => {
    originalMatchMedia = window.matchMedia
    originalRequestIdleCallback = window.requestIdleCallback
    originalCancelIdleCallback = window.cancelIdleCallback
    matchMediaMock = vi.fn((query: string) => ({
      matches:
        query.includes("prefers-color-scheme") && query.includes("dark")
          ? currentMode === "dark"
          : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    }))

    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: matchMediaMock,
    })

    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      writable: true,
      value: ((callback: IdleRequestCallback) => {
        callback({ didTimeout: false, timeRemaining: () => 16 })
        return 1
      }) as typeof window.requestIdleCallback,
    })

    Object.defineProperty(window, "cancelIdleCallback", {
      configurable: true,
      writable: true,
      value: (() => {}) as typeof window.cancelIdleCallback,
    })
  })

  afterAll(() => {
    if (originalMatchMedia) {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: originalMatchMedia,
      })
    } else {
      delete (window as { matchMedia?: typeof window.matchMedia }).matchMedia
    }

    if (originalRequestIdleCallback) {
      Object.defineProperty(window, "requestIdleCallback", {
        configurable: true,
        writable: true,
        value: originalRequestIdleCallback,
      })
    } else {
      delete (window as { requestIdleCallback?: typeof window.requestIdleCallback })
        .requestIdleCallback
    }

    if (originalCancelIdleCallback) {
      Object.defineProperty(window, "cancelIdleCallback", {
        configurable: true,
        writable: true,
        value: originalCancelIdleCallback,
      })
    } else {
      delete (window as { cancelIdleCallback?: typeof window.cancelIdleCallback })
        .cancelIdleCallback
    }
  })

  beforeEach(() => {
    useNewsFeedMock.mockReturnValue({
      data: largeFeed,
      isPending: false,
      isFetching: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useNewsFeed>)
    localStorage.setItem("ue:language", "en")
    setIsMobile(false)
  })

  afterEach(() => {
    localStorage.clear()
    matchMediaMock.mockClear()
    useNewsFeedMock.mockClear()
    useMediaQueryMock.mockReset()
  })

  it.each(
    [
      ["light", false],
      ["light", true],
      ["dark", false],
      ["dark", true],
    ] as const
  )(
    "renders a large news feed without blur in %s mode (mobile=%s)",
    async (mode, isMobile) => {
      currentMode = mode
      const wrapper = buildWrapper(mode)
      setIsMobile(isMobile)

      const { container } = render(<News />, { wrapper })

      const cards = await screen.findAllByTestId("news-card")
      expect(cards.length).toBeGreaterThan(0)

      const fadeContainer = container.querySelector<HTMLElement>("[data-page-fade]")
      expect(fadeContainer).not.toBeNull()
      expect(fadeContainer?.dataset.effect).toBeUndefined()
      await waitFor(() => expect(fadeContainer?.dataset.ready).toBe("true"))
      expect(useNewsFeedMock).toHaveBeenCalled()
    }
  )
})
