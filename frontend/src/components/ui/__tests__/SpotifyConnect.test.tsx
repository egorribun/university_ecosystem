import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createInstance } from "i18next"
import { http, HttpResponse } from "msw"
import { renderToStaticMarkup } from "react-dom/server"
import postcss from "postcss"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import enCommon from "@/i18n/locales/en/common.json"
import enSettings from "@/i18n/locales/en/settings.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import ruSettings from "@/i18n/locales/ru/settings.json"
import { server } from "@/tests/mocks/server"
import compiledCss from "@/styles/tailwind.css?inline"

const mockState = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  nowPlaying: null as Record<string, unknown> | null | undefined,
  isFetching: false,
  refetch: vi.fn(() => Promise.resolve({ data: null })),
  setUser: vi.fn(),
  invalidateQueries: vi.fn<
    (
      filters: { queryKey: readonly string[] },
      options?: { throwOnError?: boolean }
    ) => Promise<void>
  >(() => Promise.resolve()),
  apiGet: vi.fn<(..._args: unknown[]) => Promise<{ data?: { url: string } | null }>>(() =>
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
  useAuth: () => ({ user: mockState.user, loading: false, setUser: mockState.setUser }),
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
import { rotateBrowserSession } from "@/stores/sessionEpoch"

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolveRequest, rejectRequest) => {
    resolve = resolveRequest
    reject = rejectRequest
  })
  return { promise, resolve, reject }
}

describe("SpotifyConnect", () => {
  beforeEach(() => {
    rotateBrowserSession()
    window.history.replaceState({}, "", "/settings")
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
    mockState.user = { id: "user-1", spotify_connected: false }
    render(<SpotifyConnect />)
    expect(mockState.translationArgs).toEqual([["settings", "common"]])
    expect(screen.getByText("settings:integrations.spotify.title")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "settings:integrations.spotify.connect" })
    ).toBeEnabled()
  })

  it("preserves the existing Spotify colors without the shared brand background image", () => {
    mockState.user = { id: "user-1", spotify_connected: false }
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.connect" })
    expect(button).toBeEnabled()
    expect(button).not.toHaveClass("bg-(image:--gradient-brand)")

    const stylesheet = postcss.parse(compiledCss)
    const expectUtility = (
      className: string,
      property: string,
      value: string,
      pseudoClass = ""
    ) => {
      expect(button).toHaveClass(className)
      const declarations: string[] = []
      stylesheet.walkRules((rule) => {
        if (rule.selectors.includes(`.${CSS.escape(className)}${pseudoClass}`)) {
          rule.walkDecls(property, (declaration) => {
            declarations.push(declaration.value)
          })
        }
      })
      expect(declarations).toContain(value)
    }

    expectUtility("bg-none", "background-image", "none")
    expectUtility("bg-(--color-spotify)", "background-color", "var(--color-spotify)")
    expectUtility(
      "hover:bg-(--color-spotify-hover)",
      "background-color",
      "var(--color-spotify-hover)",
      ":hover"
    )
  })

  it.each([false, true])(
    "renders idle controls in server markup when Spotify is connected: %s",
    (connected) => {
      mockState.user = { id: "user-1", spotify_connected: connected }
      const serverMarkup = document.createElement("div")
      serverMarkup.innerHTML = renderToStaticMarkup(<SpotifyConnect />)

      const controls = within(serverMarkup).getAllByRole("button")
      expect(controls).toHaveLength(connected ? 2 : 1)
      for (const control of controls) expect(control).toBeEnabled()
      expect(mockState.apiGet).not.toHaveBeenCalled()
      expect(mockState.apiPost).not.toHaveBeenCalled()
      expect(mockState.refetch).not.toHaveBeenCalled()
    }
  )

  it("reports an authorization request failure accessibly and restores the connect button", async () => {
    const user = userEvent.setup()
    const failure = new Error("authorization unavailable")
    mockState.user = { id: "user-1", spotify_connected: false }
    mockState.apiGet.mockRejectedValueOnce(failure)
    render(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.connect" })

    await user.click(button)

    expect(mockState.apiGet).toHaveBeenCalledWith("/spotify/auth-url")
    expect(mockState.clickOutcomes).toHaveLength(1)
    await act(async () => {
      await expect(mockState.clickOutcomes.shift()).resolves.toBeUndefined()
    })
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.connectFailed"
    )
    expect(button).toBeEnabled()
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
    mockState.user = { id: "user-1", spotify_connected: false }
    mockState.apiGet.mockRejectedValueOnce(new Error("authorization unavailable"))
    render(<SpotifyConnect />)

    await userEvent.setup().click(screen.getByRole("button", { name: buttonLabel }))

    expect(screen.getByRole("alert")).toHaveTextContent(message)
  })

  it("disables connect while the authorization request is pending", async () => {
    const user = userEvent.setup()
    let resolveRequest!: (value: { data: { url: string } }) => void
    mockState.user = { id: "user-1", spotify_connected: false }
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

  it.each([null, undefined])("shows connected controls with no now-playing data (%s)", (data) => {
    mockState.user = {
      id: "user-1",
      spotify_connected: true,
      spotify_display_name: "Egor's Spotify",
    }
    mockState.nowPlaying = data
    render(<SpotifyConnect />)
    expect(screen.getByText("Egor's Spotify")).toBeInTheDocument()
    expect(screen.getByText("common:buttons.refresh")).toBeInTheDocument()
    expect(screen.getByText("settings:integrations.spotify.disconnect")).toBeInTheDocument()
    expect(screen.queryByText("settings:integrations.spotify.connect")).not.toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.queryByText("—")).not.toBeInTheDocument()
  })

  it("renders safe fallbacks for an incomplete now-playing payload", () => {
    mockState.user = { id: "user-1", spotify_connected: true }
    mockState.nowPlaying = { track_name: "", artists: undefined, album_name: "", track_url: "" }

    render(<SpotifyConnect />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.queryByText("Album X")).not.toBeInTheDocument()
  })

  it("falls back to the status label when connected without a display name", () => {
    mockState.user = { id: "user-1", spotify_is_connected: true }
    render(<SpotifyConnect />)
    expect(
      screen.getByText("settings:integrations.spotify.status.connectedFallback")
    ).toBeInTheDocument()
  })

  it("renders the now-playing card with track, album and external link", () => {
    mockState.user = {
      id: "user-1",
      spotify_connected: true,
      spotify_display_name: "Egor's Spotify",
    }
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
    mockState.user = {
      id: "user-1",
      spotify_connected: true,
      spotify_display_name: "Egor's Spotify",
    }
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

  it("stops cache invalidation when a profile observer synchronously replaces the session", async () => {
    mockState.user = { id: "user-1", spotify_connected: true }
    const nextAccount = {
      id: "user-2",
      spotify_connected: true,
      spotify_display_name: "Next account",
    }
    let disconnectedProfile: Record<string, unknown> | null = null
    mockState.setUser.mockImplementationOnce(
      (update: (previous: typeof mockState.user) => typeof mockState.user) => {
        disconnectedProfile = update(mockState.user)
        // Auth-store subscribers run synchronously during setUser. A subscriber
        // can replace the session before this disconnect handler resumes.
        rotateBrowserSession()
        mockState.user = nextAccount
      }
    )
    const { rerender } = render(<SpotifyConnect />)

    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))
    await expect(Promise.all(mockState.clickOutcomes)).resolves.toEqual([undefined])

    expect(disconnectedProfile).toMatchObject({ id: "user-1", spotify_connected: false })
    expect(mockState.invalidateQueries).not.toHaveBeenCalled()
    expect(mockState.user).toBe(nextAccount)
    rerender(<SpotifyConnect />)
    expect(screen.getByText("Next account")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })
    ).toBeEnabled()
  })

  it("disables disconnect while the disconnect request is pending", async () => {
    const user = userEvent.setup()
    let resolveRequest!: (value: { data: Record<string, never> }) => void
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
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

  it("clears a failed disconnect's feedback while its retry is pending", async () => {
    const retry = deferred<{ data: Record<string, never> }>()
    mockState.apiPost
      .mockRejectedValueOnce(new Error("disconnect unavailable"))
      .mockReturnValueOnce(retry.promise)
    mockState.user = { id: "user-1", spotify_connected: true }
    render(<SpotifyConnect />)
    const user = userEvent.setup()
    const button = screen.getByRole("button", {
      name: "settings:integrations.spotify.disconnect",
    })
    await user.click(button)
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.disconnectFailed"
    )

    await user.click(button)
    const feedbackDuringRetry = screen.queryByRole("alert")
    const busyDuringRetry = button.hasAttribute("disabled")
    await act(async () => retry.resolve({ data: {} }))

    expect(feedbackDuringRetry).toBeNull()
    expect(busyDuringRetry).toBe(true)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(button).toBeEnabled()
    expect(mockState.apiPost).toHaveBeenCalledTimes(2)
    expect(mockState.setUser).toHaveBeenCalledOnce()
  })

  it("refreshes now-playing via the refresh button", async () => {
    const user = userEvent.setup()
    mockState.user = {
      id: "user-1",
      spotify_connected: true,
      spotify_display_name: "Egor's Spotify",
    }
    render(<SpotifyConnect />)
    mockState.refetch.mockClear()
    await user.click(screen.getByText("common:buttons.refresh"))
    expect(mockState.refetch).toHaveBeenCalled()
  })

  it("reports a refresh failure without changing the connected user and clears it on retry", async () => {
    const user = userEvent.setup()
    const failure = new Error("refresh unavailable")
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
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
      mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
    mockState.isFetching = true
    render(<SpotifyConnect />)

    const refreshButton = screen.getByText("common:buttons.refresh").closest("button")
    expect(refreshButton).toBeDisabled()
    expect(refreshButton?.querySelector("svg")).toHaveClass("h-4", "w-4", "animate-spin")
  })

  it("requests the authorization URL and follows a safe hash redirect", async () => {
    const user = userEvent.setup()
    mockState.user = { id: "user-1", spotify_connected: false }
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
    mockState.user = { id: "user-1", spotify_connected: false }
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

  it("reports a missing authorization URL when the API returns a JSON null body", async () => {
    const { default: client } = await vi.importActual<typeof import("@/api/client")>("@/api/client")
    server.use(http.get("*/spotify/auth-url", () => HttpResponse.json(null)))
    const user = userEvent.setup()
    mockState.user = { id: "user-1", spotify_connected: false }
    mockState.apiGet.mockImplementationOnce((url) => client.get(String(url)))
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
    expect(screen.getByRole("alert")).toHaveTextContent(
      "settings:integrations.spotify.snackbar.openFailed"
    )
    expect(window.location.pathname).toBe("/settings")
    window.history.replaceState({}, "", "/")
  })

  it("refetches now-playing when the Spotify callback query is present", () => {
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")
    render(<SpotifyConnect />)

    await act(async () => rejectRequest(new Error("callback unavailable")))

    expect(mockState.refetch).toHaveBeenCalledWith({ throwOnError: true })
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
    window.history.replaceState({}, "", "/")
  })

  it("clears callback feedback for a new account and reports that account's refetch failure", async () => {
    const nextAccountRefetch = deferred<{ data: null }>()
    void nextAccountRefetch.promise.catch(() => undefined)
    mockState.refetch
      .mockRejectedValueOnce(new Error("first account callback unavailable"))
      .mockReturnValueOnce(nextAccountRefetch.promise)
    mockState.user = { id: "user-1", spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")
    const { rerender } = render(<SpotifyConnect />)
    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")

    rotateBrowserSession()
    mockState.user = { id: "user-2", spotify_connected: true }
    rerender(<SpotifyConnect />)
    const feedbackForNewAccount = screen.queryByRole("alert")
    await act(async () => nextAccountRefetch.reject(new Error("new account callback unavailable")))

    expect(feedbackForNewAccount).toBeNull()
    expect(mockState.refetch).toHaveBeenCalledTimes(2)
    expect(screen.getByRole("alert")).toHaveTextContent("common:errors.generic")
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
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
    window.history.replaceState({}, "", "/settings")

    render(<SpotifyConnect />)

    expect(mockState.refetch).not.toHaveBeenCalled()
    window.history.replaceState({}, "", "/")
  })

  it("refetches the Spotify callback only once when the query result identity changes", () => {
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
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
    mockState.user = { id: "user-1", spotify_connected: true }
    mockState.nowPlaying = { track_name: "Track", artists: undefined }

    render(<SpotifyConnect />)

    expect(screen.getByText("Track")).toBeInTheDocument()
    expect(screen.queryByText("Stryker was here")).not.toBeInTheDocument()
  })

  it.each(["success", "error"])(
    "ignores a stale authorization %s after the account changes",
    async (outcome) => {
      const pending = deferred<{ data: { url: string } }>()
      mockState.apiGet.mockReturnValueOnce(pending.promise)
      mockState.user = { id: "user-1", spotify_connected: false }
      const { rerender } = render(<SpotifyConnect />)
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "settings:integrations.spotify.connect" }))

      rotateBrowserSession()
      mockState.user = { id: "user-2", spotify_connected: false }
      rerender(<SpotifyConnect />)
      const readyForNextAccount = !screen
        .getByRole("button", { name: "settings:integrations.spotify.connect" })
        .hasAttribute("disabled")
      await act(async () => {
        if (outcome === "success") pending.resolve({ data: { url: "#stale-authorization" } })
        else pending.reject(new Error("stale authorization"))
      })

      expect(window.location.hash).toBe("")
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(readyForNextAccount).toBe(true)
    }
  )

  it.each(["success", "error"])(
    "does not adopt a stale disconnect %s for the next account",
    async (outcome) => {
      const pending = deferred<{ data: Record<string, never> }>()
      mockState.apiPost.mockReturnValueOnce(pending.promise)
      mockState.user = { id: "user-1", spotify_connected: true }
      const { rerender } = render(<SpotifyConnect />)
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))

      rotateBrowserSession()
      mockState.user = { id: "user-2", spotify_connected: true }
      rerender(<SpotifyConnect />)
      const readyForNextAccount = !screen
        .getByRole("button", { name: "settings:integrations.spotify.disconnect" })
        .hasAttribute("disabled")
      await act(async () => {
        if (outcome === "success") pending.resolve({ data: {} })
        else pending.reject(new Error("stale disconnect"))
      })

      expect(mockState.setUser).not.toHaveBeenCalled()
      expect(mockState.invalidateQueries).not.toHaveBeenCalled()
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(readyForNextAccount).toBe(true)
    }
  )

  it.each(["success", "error"])(
    "keeps the next account's authorization pending when an old request ends with %s",
    async (outcome) => {
      const first = deferred<{ data: { url: string } }>()
      const second = deferred<{ data: { url: string } }>()
      mockState.apiGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
      mockState.user = { id: "user-1", spotify_connected: false }
      const { rerender } = render(<SpotifyConnect />)
      const user = userEvent.setup()
      const button = screen.getByRole("button", {
        name: "settings:integrations.spotify.connect",
      })
      await user.click(button)
      rotateBrowserSession()
      mockState.user = { id: "user-2", spotify_connected: false }
      rerender(<SpotifyConnect />)
      await user.click(button)

      await act(async () => {
        if (outcome === "success") first.resolve({ data: { url: "#old-authorization" } })
        else first.reject(new Error("old authorization unavailable"))
      })
      const busyAfterOldRequest = button.hasAttribute("disabled")
      const feedbackAfterOldRequest = screen.queryByRole("alert")
      const hashAfterOldRequest = window.location.hash
      await act(async () => second.resolve({ data: { url: "#current-authorization" } }))

      expect(mockState.apiGet).toHaveBeenCalledTimes(2)
      expect(busyAfterOldRequest).toBe(true)
      expect(feedbackAfterOldRequest).toBeNull()
      expect(hashAfterOldRequest).toBe("")
      expect(button).toBeEnabled()
      expect(window.location.hash).toBe("#current-authorization")
    }
  )

  it.each(["logout", "unmount", "same-account-session"])(
    "discards a disconnect response after %s",
    async (boundary) => {
      const pending = deferred<{ data: Record<string, never> }>()
      mockState.apiPost.mockReturnValueOnce(pending.promise)
      mockState.user = { id: "user-1", spotify_connected: true }
      const { rerender, unmount } = render(<SpotifyConnect />)
      await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))

      rotateBrowserSession()
      if (boundary === "logout") mockState.user = null
      if (boundary === "unmount") unmount()
      else rerender(<SpotifyConnect />)
      await act(async () => pending.resolve({ data: {} }))

      expect(mockState.setUser).not.toHaveBeenCalled()
      expect(mockState.invalidateQueries).not.toHaveBeenCalled()
    }
  )

  it("does not let an old action clear the next account's loading state", async () => {
    const first = deferred<{ data: Record<string, never> }>()
    const second = deferred<{ data: Record<string, never> }>()
    mockState.apiPost.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    mockState.user = { id: "user-1", spotify_connected: true }
    const { rerender } = render(<SpotifyConnect />)
    const user = userEvent.setup()
    await user.click(
      screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })
    )
    rotateBrowserSession()
    mockState.user = { id: "user-2", spotify_connected: true }
    rerender(<SpotifyConnect />)
    const button = screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" })
    await user.click(button)
    await act(async () => first.resolve({ data: {} }))
    const stillBusy = button.hasAttribute("disabled")
    await act(async () => second.resolve({ data: {} }))

    expect(mockState.apiPost).toHaveBeenCalledTimes(2)
    expect(stillBusy).toBe(true)
    expect(button).toBeEnabled()
  })

  it("clears the previous account's error on an account switch", async () => {
    mockState.user = { id: "user-1", spotify_connected: true }
    mockState.apiPost.mockRejectedValueOnce(new Error("previous account error"))
    const { rerender } = render(<SpotifyConnect />)
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))
    expect(screen.getByRole("alert")).toBeInTheDocument()

    rotateBrowserSession()
    mockState.user = { id: "user-2", spotify_connected: true }
    rerender(<SpotifyConnect />)

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it.each(["refresh", "callback"])(
    "ignores a stale %s failure after the account changes",
    async (source) => {
      const pending = deferred<{ data: null }>()
      mockState.refetch.mockReturnValueOnce(pending.promise)
      mockState.user = { id: "user-1", spotify_connected: true }
      if (source === "callback") window.history.replaceState({}, "", "/settings?spotify=connected")
      const { rerender } = render(<SpotifyConnect />)
      if (source === "refresh")
        await userEvent
          .setup()
          .click(screen.getByRole("button", { name: "common:buttons.refresh" }))
      rotateBrowserSession()
      mockState.user = { id: "user-2", spotify_connected: true }
      rerender(<SpotifyConnect />)
      await act(async () => pending.reject(new Error("stale refresh")))

      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    }
  )

  it("does not show stale cache failure feedback after a successful disconnect", async () => {
    const pending = deferred<void>()
    mockState.invalidateQueries.mockReturnValueOnce(pending.promise)
    mockState.user = { id: "user-1", spotify_connected: true }
    const { rerender } = render(<SpotifyConnect />)
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))
    expect(mockState.setUser).toHaveBeenCalledOnce()
    rotateBrowserSession()
    mockState.user = { id: "user-2", spotify_connected: true }
    rerender(<SpotifyConnect />)
    await act(async () => pending.reject(new Error("stale cache error")))

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("rechecks account identity and session inside a queued user updater", async () => {
    mockState.user = { id: "user-1", spotify_connected: true }
    render(<SpotifyConnect />)
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "settings:integrations.spotify.disconnect" }))
    const update = mockState.setUser.mock.calls[0]?.[0] as (
      previous: Record<string, unknown>
    ) => Record<string, unknown>
    const nextAccount = { id: "user-2", spotify_connected: true }
    expect(update(nextAccount)).toBe(nextAccount)
    rotateBrowserSession()
    expect(update(mockState.user)).toBe(mockState.user)
  })

  it.each(["connect", "disconnect", "refresh"])(
    "does not start %s from a stale browser tab",
    async (action) => {
      mockState.user = { id: "user-1", spotify_connected: action !== "connect" }
      render(<SpotifyConnect />)
      window.localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({ nonce: "other-tab", hash: null })
      )
      const name =
        action === "refresh" ? "common:buttons.refresh" : `settings:integrations.spotify.${action}`
      await userEvent.setup().click(screen.getByRole("button", { name }))

      expect(mockState.apiGet).not.toHaveBeenCalled()
      expect(mockState.apiPost).not.toHaveBeenCalled()
      expect(mockState.refetch).not.toHaveBeenCalled()
    }
  )

  it("does not start an action or callback refetch for an unconfirmed identity", async () => {
    mockState.user = { id: "ssr-stub", spotify_connected: false }
    window.history.replaceState({}, "", "/settings?spotify=connected")
    render(<SpotifyConnect />)
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "settings:integrations.spotify.connect" }))

    expect(mockState.apiGet).not.toHaveBeenCalled()
    expect(mockState.refetch).not.toHaveBeenCalled()
  })
})
