import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createInstance } from "i18next"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import enCommon from "@/i18n/locales/en/common.json"
import enSettings from "@/i18n/locales/en/settings.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import ruSettings from "@/i18n/locales/ru/settings.json"

const mockState = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  nowPlaying: null as Record<string, unknown> | null,
  isFetching: false,
  refetch: vi.fn(() => Promise.resolve({ data: null })),
  setUser: vi.fn(),
  invalidateQueries: vi.fn<
    (
      filters: { queryKey: readonly string[] },
      options?: { throwOnError?: boolean }
    ) => Promise<void>
  >(() => Promise.resolve()),
  apiGet: vi.fn<(..._args: unknown[]) => Promise<{ data?: { url: string } }>>(() =>
    Promise.resolve({ data: { url: "https://accounts.spotify.com/authorize?x=1" } })
  ),
  apiPost: vi.fn((..._args: unknown[]) => Promise.resolve({ data: {} })),
  translationArgs: [] as unknown[],
  clickOutcomes: [] as Promise<unknown>[],
  translate: (key: string) => key,
}))

// Record how every async click handler settles. React ignores the promise an
// onClick returns, so a rejected handler would otherwise surface only as an
// unhandled rejection outside the test that caused it. Keep the original
// promise rejected: explicit rejection assertions or afterEach must consume it.
vi.mock("@/components/settings/SettingsUI", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/settings/SettingsUI")>()
  const Original = actual.Button as unknown as React.ComponentType<Record<string, unknown>>
  const Button = ({ onClick, ...props }: { onClick?: (event: unknown) => unknown }) => (
    <Original
      {...props}
      onClick={(event: unknown) => {
        const outcome = Promise.resolve(onClick?.(event))
        mockState.clickOutcomes.push(outcome)
        // Observe it immediately to avoid a premature unhandled-rejection
        // report; this does not change the recorded promise's rejection.
        void outcome.catch(() => undefined)
      }}
    />
  )
  return { ...actual, Button }
})

type JsdomVirtualConsole = {
  on: (event: "jsdomError", listener: (error: Error) => void) => void
  off: (event: "jsdomError", listener: (error: Error) => void) => void
}

// jsdom cannot leave the document; it reports every attempted cross-document
// navigation on its virtual console, which makes such attempts observable.
const recordNavigationAttempts = () => {
  const attempts: string[] = []
  const { virtualConsole } = (
    globalThis as unknown as { jsdom: { virtualConsole: JsdomVirtualConsole } }
  ).jsdom
  const listener = (error: Error) => {
    if (error.message.includes("navigation")) attempts.push(error.message)
  }
  virtualConsole.on("jsdomError", listener)
  return { attempts, stop: () => virtualConsole.off("jsdomError", listener) }
}

vi.mock("react-i18next", () => ({
  useTranslation: (...args: unknown[]) => {
    mockState.translationArgs = args
    return {
      t: mockState.translate,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mockState.user, setUser: mockState.setUser }),
  currentUserQueryKey: ["users", "me"],
}))

vi.mock("@/hooks/useNowPlaying", () => ({
  nowPlayingQueryKey: ["spotify", "now-playing"],
  useNowPlaying: () => ({
    data: mockState.nowPlaying,
    isFetching: mockState.isFetching,
    refetch: mockState.refetch,
  }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockState.invalidateQueries }),
}))

vi.mock("@/api/client", () => ({
  default: {
    get: (...args: unknown[]) => mockState.apiGet(...args),
    post: (...args: unknown[]) => mockState.apiPost(...args),
  },
}))

vi.mock("@/utils/spotify", () => ({
  sanitizeSpotifyAuthorizeUrl: (url?: string) => url ?? null,
}))

import SpotifyConnect from "@/components/ui/SpotifyConnect"

describe("SpotifyConnect", () => {
  beforeEach(() => {
    mockState.user = null
    mockState.nowPlaying = null
    mockState.isFetching = false
    mockState.refetch.mockClear()
    mockState.setUser.mockClear()
    mockState.invalidateQueries.mockReset()
    mockState.invalidateQueries.mockResolvedValue(undefined)
    mockState.apiGet.mockClear()
    mockState.apiPost.mockClear()
    mockState.translationArgs = []
    mockState.clickOutcomes = []
    mockState.translate = (key: string) => key
  })

  afterEach(async () => {
    // Every recorded click must resolve, unless a test has consumed it with
    // an explicit rejection assertion. Unexpected failures fail that test.
    await expect(Promise.all(mockState.clickOutcomes)).resolves.toEqual(
      mockState.clickOutcomes.map(() => undefined)
    )
  })

  it("renders nothing when there is no user", () => {
    const { container } = render(<SpotifyConnect />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the connect button when Spotify is not connected", () => {
    mockState.user = { spotify_connected: false }
    render(<SpotifyConnect />)
    expect(mockState.translationArgs).toEqual([["settings", "common"]])
    expect(screen.getByText("settings:integrations.spotify.title")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "settings:integrations.spotify.connect" })
    ).toBeEnabled()
  })

  it("reports an authorization request failure accessibly and restores the connect button", async () => {
    const user = userEvent.setup()
    const failure = new Error("authorization unavailable")
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockRejectedValueOnce(failure)
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.connect" })

    await user.click(button)

    expect(mockState.apiGet).toHaveBeenCalledWith("/spotify/auth-url")
    expect(mockState.clickOutcomes).toHaveLength(1)
    await expect(mockState.clickOutcomes.shift()).resolves.toBeUndefined()
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.connectFailed"
    )
    await waitFor(() => expect(button).toBeEnabled())
    mockState.apiGet.mockResolvedValueOnce({ data: { url: "#spotify" } })
    await user.click(button)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    window.history.replaceState({}, "", "/")
  })

  it.each([
    ["en", "Connect Spotify", "Couldn't connect to Spotify"],
    ["ru", "Подключить Spotify", "Ошибка подключения Spotify"],
  ])("localizes authorization failure feedback in %s", async (language, buttonLabel, message) => {
    const instance = createInstance()
    await instance.init({
      lng: language,
      resources: {
        en: { settings: enSettings, common: enCommon },
        ru: { settings: ruSettings, common: ruCommon },
      },
    })
    mockState.translate = (key: string) => instance.t(key)
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockRejectedValueOnce(new Error("authorization unavailable"))
    render(<SpotifyConnect />)

    await userEvent.setup().click(screen.getByRole("button", { name: buttonLabel }))

    expect(screen.getByRole("alert")).toHaveTextContent(message)
  })

  it("disables connect while the authorization request is pending", async () => {
    const user = userEvent.setup()
    let resolveRequest!: (value: { data: { url: string } }) => void
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.connect" })

    const click = user.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    resolveRequest({ data: { url: "" } })
    await click
    await waitFor(() => expect(button).toBeEnabled())
  })

  it("shows the connected controls + display name when connected", () => {
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    expect(screen.getByText("Egor's Spotify")).toBeInTheDocument()
    expect(screen.getByText("common:buttons.refresh")).toBeInTheDocument()
    expect(screen.getByText("settings:integrations.spotify.disconnect")).toBeInTheDocument()
    expect(screen.queryByText("settings:integrations.spotify.connect")).not.toBeInTheDocument()
  })

  it("renders safe fallbacks for an incomplete now-playing payload", () => {
    mockState.user = { spotify_connected: true }
    mockState.nowPlaying = { track_name: "", artists: undefined, album_name: "", track_url: "" }

    render(<SpotifyConnect />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.queryByText("Album X")).not.toBeInTheDocument()
  })

  it("falls back to the status label when connected without a display name", () => {
    mockState.user = { spotify_is_connected: true }
    render(<SpotifyConnect />)
    expect(
      screen.getByText("settings:integrations.spotify.status.connectedFallback")
    ).toBeInTheDocument()
  })

  it("renders the now-playing card with track, album and external link", () => {
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    mockState.nowPlaying = {
      track_name: "Track One",
      artists: ["Artist A", "Artist B"],
      album_name: "Album X",
      track_url: "https://open.spotify.com/track/1",
    }
    render(<SpotifyConnect />)
    expect(screen.getByText("Track One")).toBeInTheDocument()
    expect(screen.getByText("Artist A, Artist B")).toBeInTheDocument()
    expect(screen.getByText("Album X")).toBeInTheDocument()
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "https://open.spotify.com/track/1")
  })

  it("disconnects via the disconnect button, calling api + setUser + invalidateQueries", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    await user.click(screen.getByText("settings:integrations.spotify.disconnect"))
    expect(mockState.apiPost).toHaveBeenCalledWith("/spotify/disconnect")
    expect(mockState.setUser).toHaveBeenCalled()
    expect(mockState.invalidateQueries).toHaveBeenNthCalledWith(
      1,
      { queryKey: ["users", "me"] },
      { throwOnError: true }
    )
    expect(mockState.invalidateQueries).toHaveBeenNthCalledWith(
      2,
      { queryKey: ["spotify", "now-playing"] },
      { throwOnError: true }
    )

    const updater = mockState.setUser.mock.calls[0]?.[0] as (
      previous: Record<string, unknown>
    ) => Record<string, unknown> | null
    expect(updater(mockState.user ?? {})).toMatchObject({
      spotify_connected: false,
      spotify_is_connected: false,
      spotify_display_name: null,
    })
    expect(updater(null as never)).toBeNull()
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })
      ).toBeEnabled()
    )
  })

  it("disables disconnect while the disconnect request is pending", async () => {
    const user = userEvent.setup()
    let resolveRequest!: (value: { data: Record<string, never> }) => void
    mockState.user = { spotify_connected: true }
    mockState.apiPost.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })

    const click = user.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    resolveRequest({ data: {} })
    await click
    await waitFor(() => expect(button).toBeEnabled())
  })

  it("reports a disconnect failure without clearing the user and restores the button", async () => {
    const user = userEvent.setup()
    const failure = new Error("disconnect unavailable")
    mockState.user = { spotify_connected: true }
    mockState.apiPost.mockRejectedValueOnce(failure)
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })

    await user.click(button)

    expect(mockState.apiPost).toHaveBeenCalledWith("/spotify/disconnect")
    expect(mockState.clickOutcomes).toHaveLength(1)
    await expect(mockState.clickOutcomes.shift()).resolves.toBeUndefined()
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.disconnectFailed"
    )
    expect(mockState.setUser).not.toHaveBeenCalled()
    expect(mockState.invalidateQueries).not.toHaveBeenCalled()
    await waitFor(() => expect(button).toBeEnabled())
  })

  it("refreshes now-playing via the refresh button", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    mockState.refetch.mockClear()
    await user.click(screen.getByText("common:buttons.refresh"))
    expect(mockState.refetch).toHaveBeenCalled()
  })

  it("reports a refresh failure without changing the connected user and clears it on retry", async () => {
    const user = userEvent.setup()
    const failure = new Error("refresh unavailable")
    mockState.user = { spotify_connected: true }
    mockState.refetch.mockRejectedValueOnce(failure)
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "common:buttons.refresh" })

    await user.click(button)

    expect(mockState.refetch).toHaveBeenCalledOnce()
    expect(mockState.clickOutcomes).toHaveLength(1)
    await expect(mockState.clickOutcomes.shift()).resolves.toBeUndefined()
    expect(mockState.refetch).toHaveBeenCalledWith({ throwOnError: true })
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
    expect(mockState.setUser).not.toHaveBeenCalled()
    expect(button).toBeEnabled()
    await user.click(button)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps a successful disconnect when cache invalidation fails and reports the cache error", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true }
    mockState.invalidateQueries.mockRejectedValueOnce(new Error("cache unavailable"))
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })

    await user.click(button)

    await expect(mockState.clickOutcomes.shift()).resolves.toBeUndefined()
    expect(mockState.setUser).toHaveBeenCalledOnce()
    const updater = mockState.setUser.mock.calls[0]?.[0] as (
      previous: Record<string, unknown>
    ) => Record<string, unknown>
    expect(updater(mockState.user ?? {})).toMatchObject({ spotify_connected: false })
    expect(mockState.invalidateQueries).toHaveBeenCalledTimes(2)
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.disconnected"
    )
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "settings:integrations.spotify.snackbar.disconnectFailed"
    )
    expect(button).toBeEnabled()
  })

  it.each([
    ["users", "me"],
    ["spotify", "now-playing"],
  ])(
    "reports a real active-query refetch failure for %s/%s after disconnect",
    async (...queryKey) => {
      const { QueryClient, QueryObserver } =
        await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query")
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const fetchFailure = new Error("query refresh unavailable")
      const fetchQuery = vi.fn(async () => {
        throw fetchFailure
      })
      client.setQueryData(queryKey, { spotify_connected: true })
      const observer = new QueryObserver(client, {
        queryKey,
        queryFn: fetchQuery,
        staleTime: Infinity,
      })
      const unsubscribe = observer.subscribe(() => undefined)
      mockState.invalidateQueries.mockImplementation((filters, options) =>
        client.invalidateQueries(filters, options)
      )
      mockState.user = { spotify_connected: true }
      const { unmount } = render(<SpotifyConnect />)
      const button = screen.getByRole("button", {
        name: "settings:integrations.spotify.disconnect",
      })

      try {
        await userEvent.setup().click(button)
        await expect(Promise.all(mockState.clickOutcomes)).resolves.toEqual([undefined])

        expect(fetchQuery).toHaveBeenCalledOnce()
        expect(observer.getCurrentResult().error).toBe(fetchFailure)
        expect(mockState.apiPost).toHaveBeenCalledWith("/spotify/disconnect")
        const updater = mockState.setUser.mock.calls[0]?.[0] as (
          previous: Record<string, unknown>
        ) => Record<string, unknown>
        expect(updater(mockState.user ?? {})).toMatchObject({
          spotify_connected: false,
          spotify_is_connected: false,
        })
        expect(screen.getByRole("alert")).toHaveTextContent(
          "settings:integrations.spotify.snackbar.disconnected"
        )
        expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
        expect(screen.getByRole("alert")).not.toHaveTextContent(
          "settings:integrations.spotify.snackbar.disconnectFailed"
        )
        expect(button).toBeEnabled()
      } finally {
        unmount()
        unsubscribe()
        client.clear()
      }
    }
  )

  it("disables refresh and animates its icon while now-playing is fetching", () => {
    mockState.user = { spotify_connected: true }
    mockState.isFetching = true
    render(<SpotifyConnect />)

    const refreshButton = screen.getByText("common:buttons.refresh").closest("button")
    expect(refreshButton).toBeDisabled()
    expect(refreshButton?.querySelector("svg")).toHaveClass("h-4", "w-4", "animate-spin")
  })

  it("requests the authorization URL and follows a safe hash redirect", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockResolvedValueOnce({ data: { url: "#spotify" } })
    window.history.replaceState({}, "", "/settings")
    render(<SpotifyConnect />)

    await user.click(screen.getByText("settings:integrations.spotify.connect"))

    expect(mockState.apiGet).toHaveBeenCalledWith("/spotify/auth-url")
    expect(window.location.hash).toBe("#spotify")
    window.history.replaceState({}, "", "/")
  })

  it("stays on the settings page when no safe authorization URL is returned", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockResolvedValueOnce({ data: { url: "" } })
    window.history.replaceState({}, "", "/settings")
    render(<SpotifyConnect />)
    const connectButton = screen.getByRole("button", {
      name: "settings:integrations.spotify.connect",
    })
    const navigation = recordNavigationAttempts()

    try {
      await user.click(connectButton)
      await waitFor(() => expect(connectButton).not.toBeDisabled())
      await expect(Promise.all(mockState.clickOutcomes)).resolves.toEqual([undefined])
    } finally {
      navigation.stop()
    }
    expect(navigation.attempts).toEqual([])
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.openFailed"
    )
    expect(window.location.pathname).toBe("/settings")
    window.history.replaceState({}, "", "/")
  })

  it("handles an authorization response without a data object", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockResolvedValueOnce({ data: undefined })
    window.history.replaceState({}, "", "/settings")
    render(<SpotifyConnect />)
    const connectButton = screen.getByRole("button", {
      name: "settings:integrations.spotify.connect",
    })
    const navigation = recordNavigationAttempts()

    try {
      await user.click(connectButton)
      await waitFor(() => expect(connectButton).toBeEnabled())
      await expect(Promise.all(mockState.clickOutcomes)).resolves.toEqual([undefined])
    } finally {
      navigation.stop()
    }
    expect(navigation.attempts).toEqual([])
    expect(window.location.pathname).toBe("/settings")
    window.history.replaceState({}, "", "/")
  })

  it("refetches now-playing when the Spotify callback query is present", () => {
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")

    render(<SpotifyConnect />)

    expect(mockState.refetch).toHaveBeenCalled()
    window.history.replaceState({}, "", "/")
  })

  it("reports a failed callback refetch without leaving a rejected effect promise", async () => {
    let rejectRequest!: (error: Error) => void
    const request = new Promise<{ data: null }>((_, reject) => {
      rejectRequest = reject
    })
    // Observe the controlled request itself; the component still receives its
    // original rejected promise and must provide the user-facing feedback.
    void request.catch(() => undefined)
    mockState.refetch.mockReturnValueOnce(request)
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")
    render(<SpotifyConnect />)

    await act(async () => rejectRequest(new Error("callback unavailable")))

    expect(mockState.refetch).toHaveBeenCalledWith({ throwOnError: true })
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
    window.history.replaceState({}, "", "/")
  })

  it("ignores a stale callback failure after the refetch dependency changes", async () => {
    let rejectRequest!: (error: Error) => void
    const request = new Promise<{ data: null }>((_, reject) => {
      rejectRequest = reject
    })
    void request.catch(() => undefined)
    const originalRefetch = mockState.refetch
    const replacementRefetch = vi.fn(() => Promise.resolve({ data: null }))
    originalRefetch.mockReturnValueOnce(request)
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")
    const { rerender } = render(<SpotifyConnect />)

    try {
      mockState.refetch = replacementRefetch
      rerender(<SpotifyConnect />)
      await act(async () => rejectRequest(new Error("stale callback unavailable")))

      expect(replacementRefetch).toHaveBeenCalledWith({ throwOnError: true })
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    } finally {
      mockState.refetch = originalRefetch
      window.history.replaceState({}, "", "/")
    }
  })

  it("does not refetch when no Spotify callback query is present", () => {
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings")

    render(<SpotifyConnect />)

    expect(mockState.refetch).not.toHaveBeenCalled()
    window.history.replaceState({}, "", "/")
  })

  it("refetches the Spotify callback only once when the query result identity changes", () => {
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")

    const { rerender } = render(<SpotifyConnect />)
    expect(mockState.refetch).toHaveBeenCalledOnce()

    mockState.isFetching = true
    rerender(<SpotifyConnect />)

    expect(mockState.refetch).toHaveBeenCalledOnce()
    window.history.replaceState({}, "", "/")
  })

  it("reruns the callback effect when the refetch function identity changes", () => {
    const originalRefetch = mockState.refetch
    const replacementRefetch = vi.fn(() => Promise.resolve({ data: null }))
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")

    const { rerender } = render(<SpotifyConnect />)
    expect(originalRefetch).toHaveBeenCalledOnce()

    mockState.refetch = replacementRefetch
    rerender(<SpotifyConnect />)
    expect(replacementRefetch).toHaveBeenCalledOnce()

    mockState.refetch = originalRefetch
    window.history.replaceState({}, "", "/")
  })

  it("renders an empty artist list without inventing artist text", () => {
    mockState.user = { spotify_connected: true }
    mockState.nowPlaying = { track_name: "Track", artists: undefined }

    render(<SpotifyConnect />)

    expect(screen.getByText("Track")).toBeInTheDocument()
    expect(screen.queryByText("Stryker was here")).not.toBeInTheDocument()
  })
})
