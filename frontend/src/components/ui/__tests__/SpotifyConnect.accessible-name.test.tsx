import { createInstance } from "i18next"
import { render, screen } from "@testing-library/react"
import { I18nextProvider, initReactI18next } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import enCommon from "@/i18n/locales/en/common.json"
import enProfile from "@/i18n/locales/en/profile.json"
import enSettings from "@/i18n/locales/en/settings.json"
import ruCommon from "@/i18n/locales/ru/common.json"
import ruProfile from "@/i18n/locales/ru/profile.json"
import ruSettings from "@/i18n/locales/ru/settings.json"

const mockState = vi.hoisted(() => ({
  user: null as { id: string; spotify_connected: boolean; spotify_display_name: string } | null,
  nowPlaying: null as {
    track_name?: string | null
    artists: string[]
    album_name?: string | null
    track_url: string
  } | null,
  setUser: vi.fn(),
  refetch: vi.fn(),
  invalidateQueries: vi.fn(),
  captureOperation: vi.fn(() => () => true),
}))

vi.mock("@/contexts/AuthContext", () => ({
  currentUserQueryKey: ["users", "me"],
  useAuth: () => ({ user: mockState.user, setUser: mockState.setUser }),
}))

vi.mock("@/hooks/useNowPlaying", () => ({
  nowPlayingQueryKey: ["spotify", "now-playing"],
  useNowPlaying: () => ({
    data: mockState.nowPlaying,
    isFetching: false,
    refetch: mockState.refetch,
  }),
}))

vi.mock("@/hooks/useProfileSessionGuard", () => ({
  useProfileSessionGuard: () => mockState.captureOperation,
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockState.invalidateQueries }),
}))

vi.mock("@/api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

vi.mock("@/utils/spotify", () => ({
  sanitizeSpotifyAuthorizeUrl: (url?: string) => url ?? null,
}))

import SpotifyConnect from "@/components/ui/SpotifyConnect"

type Language = "en" | "ru"

const localeResources = {
  en: { common: enCommon, profile: enProfile, settings: enSettings },
  ru: { common: ruCommon, profile: ruProfile, settings: ruSettings },
}

const trackUrl = "https://open.spotify.com/track/accessibility-fixture"

const accessibleNameCases: {
  label: string
  language: Language
  trackName?: string
  expectedName: string
}[] = [
  {
    label: "English populated track",
    language: "en",
    trackName: "Midnight Train",
    expectedName: "Open in Spotify: Midnight Train",
  },
  {
    label: "Russian populated track",
    language: "ru",
    trackName: "Ночной поезд",
    expectedName: "Открыть в Spotify: Ночной поезд",
  },
  {
    label: "English blank track fallback",
    language: "en",
    trackName: "",
    expectedName: "Open Spotify",
  },
  {
    label: "Russian blank track fallback",
    language: "ru",
    trackName: "",
    expectedName: "Открыть Spotify",
  },
  {
    label: "English missing track fallback",
    language: "en",
    expectedName: "Open Spotify",
  },
  {
    label: "Russian missing track fallback",
    language: "ru",
    expectedName: "Открыть Spotify",
  },
  {
    label: "English whitespace-only track fallback",
    language: "en",
    trackName: "   ",
    expectedName: "Open Spotify",
  },
  {
    label: "Russian whitespace-only track fallback",
    language: "ru",
    trackName: " \t ",
    expectedName: "Открыть Spotify",
  },
]

async function renderSpotifyPlayer(language: Language, trackName?: string) {
  mockState.nowPlaying = {
    ...(trackName === undefined ? {} : { track_name: trackName }),
    artists: ["Accessibility Fixture"],
    album_name: "Test Album",
    track_url: trackUrl,
  }

  const i18n = createInstance()
  await i18n.use(initReactI18next).init({
    lng: language,
    fallbackLng: false,
    defaultNS: "settings",
    ns: ["settings", "common", "profile"],
    resources: localeResources,
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  })

  return render(
    <I18nextProvider i18n={i18n}>
      <SpotifyConnect />
    </I18nextProvider>
  )
}

describe("SpotifyConnect now-playing link accessible name", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockState.user = {
      id: "user-1",
      spotify_connected: true,
      spotify_display_name: "Fixture Account",
    }
    mockState.nowPlaying = null
    window.history.replaceState({}, "", "/settings")
  })

  it.each(accessibleNameCases)(
    "$label exposes the translated track link name",
    async ({ language, trackName, expectedName }) => {
      await renderSpotifyPlayer(language, trackName)

      const link = screen.getByRole("link", { name: expectedName })
      expect(link).toHaveAttribute("href", trackUrl)
    }
  )
})
