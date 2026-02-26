/* eslint-disable @typescript-eslint/no-explicit-any */
import { QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, act } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import api from "@/api/client"
import { createQueryClient } from "@/app/queryClient"
import { AuthContext } from "@/contexts/AuthContext"
import Settings from "@/pages/Settings"
import type { User } from "@/types/User"
import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "../../i18n/config"

const tSettings = (key: string, options?: Record<string, unknown>) =>
  i18n.t(`settings:${key}`, options)

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}))

vi.mock("@/hooks/usePushPreferences", () => ({
  usePushPreferences: () => ({
    topicKeys: [],
    topicState: {},
    pushSupported: false,
    notificationPermission: "default" as NotificationPermission,
    notificationsEnabled: false,
    pushBusy: false,
    pushInitializing: false,
    permissionText: "",
    selectedTopicsDescription: "",
    enableNotifications: vi.fn(),
    disableNotifications: vi.fn(),
    handleTopicToggle: () => () => {},
    safariIOS: false,
    safariGuideUrl: "#",
  }),
}))

vi.mock("@/stores/useAuthStore", () => ({
  useAuthStore: () => ({
    user: {
      id: "uuid-1",
      email: "test@example.com",
      full_name: "Test User",
      role: "student",
      group_id: "group-1",
      avatar_url: "/media/avatars/original.png",
      avatar_url_optimized: null,
      cover_url: "/media/covers/original.jpg",
      cover_url_optimized: null,
      profile_detail: undefined,
      education_path: undefined,
      preferences: { dnd_enabled: false, timezone: null, dnd_start: null, dnd_end: null },
      spotify_connected: false,
      is_active: true,
      mfa_required: false,
      mfa_default_method: null,
      mfa_last_verified_at: null,
      recovery_codes_left: 0,
      totp_enrollments: [],
      mfa_challenges: [],
    },
    loading: false,
    pendingMfa: null,
    authOperation: false,
    setUser: vi.fn(),
  }),
}))

const baseUser: User = {
  id: "uuid-1",
  email: "test@example.com",
  full_name: "Test User",
  role: "student",
  group_id: "group-1",
  avatar_url: "/media/avatars/original.png",
  avatar_url_optimized: null,
  cover_url: "/media/covers/original.jpg",
  cover_url_optimized: null,
  profile_detail: undefined,
  education_path: undefined,
  preferences: { dnd_enabled: false, timezone: null, dnd_start: null, dnd_end: null },
  spotify_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
  mfa_challenges: [],
}

const renderSettings = () => {
  const queryClient = createQueryClient()
  const mockSetUser = vi.fn()
  const mockLogout = vi.fn().mockResolvedValue(undefined)

  const utils = render(
    <MemoryRouter initialEntries={["/settings"]}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <LanguageProvider>
            <AuthContext.Provider
              value={{
                setUser: mockSetUser,
                logout: mockLogout,
                login: vi.fn(),
                loginWithPasskey: vi.fn(),
                refresh: vi.fn(),
                submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
                requireMfa: vi.fn().mockResolvedValue(null),
                resetEtagCache: vi.fn(),
              }}
            >
              <Settings />
            </AuthContext.Provider>
          </LanguageProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )

  return { ...utils, mockSetUser }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("Settings media actions", () => {
  it("uploads avatar and refreshes the profile", async () => {
    const updatedUser = { ...baseUser, avatar_url: "/media/avatars/new.png" }
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({ data: updatedUser } as any)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any)

    const { mockSetUser } = renderSettings()

    fireEvent.click(screen.getByRole("tab", { name: tSettings("tabs.account") }))
    await userEvent.click(await screen.findByText(tSettings("media.avatar.title")))

    await waitFor(() =>
      expect(document.querySelectorAll("input[type='file']").length).toBeGreaterThan(1)
    )
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']")

    const avatar = await screen.findByAltText(baseUser.full_name ?? "")
    const initialSrc = avatar.getAttribute("src")

    const file = new File(["avatar"], "avatar.png", { type: "image/png" })

    await act(async () => {
      fireEvent.change(fileInputs[0], { target: { files: [file] } })
      await new Promise((resolve) => setTimeout(resolve, 15))
    })

    await waitFor(() => expect(postSpy).toHaveBeenCalled())

    const formData = postSpy.mock.calls[0][1] as FormData
    expect(formData.get("file")).toBe(file)

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalled()
      const [endpoint, config] = getSpy.mock.calls[getSpy.mock.calls.length - 1]
      expect(endpoint).toBe("/users/me")
      if (config) {
        expect(config).toEqual(expect.objectContaining({ signal: expect.any(AbortSignal) }))
      }
    })
    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser))

    const updatedSrc = avatar.getAttribute("src")
    expect(updatedSrc).toContain("v=")
    expect(updatedSrc).not.toEqual(initialSrc)
  })

  it("shows an error when avatar upload fails", async () => {
    vi.spyOn(api, "post").mockRejectedValue({ response: { data: { detail: "Upload error" } } })

    renderSettings()
    fireEvent.click(screen.getByRole("tab", { name: tSettings("tabs.account") }))
    await userEvent.click(await screen.findByText(tSettings("media.avatar.title")))
    await waitFor(() => expect(document.querySelector("input[type='file']")).toBeTruthy())
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']")
    const file = new File(["avatar"], "avatar.png", { type: "image/png" })

    await act(async () => {
      fireEvent.change(fileInputs[0], { target: { files: [file] } })
    })

    await waitFor(() => expect(api.post).toHaveBeenCalled())

    expect(
      await screen.findByText(tSettings("media.avatar.uploadFailed"), {}, { timeout: 3000 })
    ).toBeInTheDocument()
  })

  it("uploads cover and updates preview", async () => {
    const updatedUser = { ...baseUser, cover_url: "/media/covers/new.jpg" }
    vi.spyOn(api, "post").mockImplementation((url: string) => {
      if (url === "/users/me/cover") {
        return Promise.resolve({ data: updatedUser } as any)
      }
      return Promise.resolve({ data: updatedUser } as any)
    })
    vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any)

    const { mockSetUser } = renderSettings()

    fireEvent.click(screen.getByRole("tab", { name: tSettings("tabs.account") }))
    await userEvent.click(await screen.findByText(tSettings("media.cover.title")))

    await waitFor(() =>
      expect(document.querySelectorAll("input[type='file']").length).toBeGreaterThan(1)
    )
    const fileInputs = document.querySelectorAll<HTMLInputElement>("input[type='file']")

    const coverLabel = await screen.findByText(tSettings("media.cover.title"))
    const coverItem = coverLabel.closest("li") as HTMLElement
    const preview = coverItem.querySelector<HTMLElement>("[data-testid='settings-cover-preview']")
    expect(preview).toBeTruthy()
    const initialBackground = window.getComputedStyle(preview!).backgroundImage

    const file = new File(["cover"], "cover.png", { type: "image/png" })
    await act(async () => {
      fireEvent.change(fileInputs[1], { target: { files: [file] } })
      await new Promise((resolve) => setTimeout(resolve, 15))
    })

    await waitFor(() => expect(api.post).toHaveBeenCalled())

    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser))

    const updatedBackground = window.getComputedStyle(preview!).backgroundImage
    expect(updatedBackground).toContain("v=")
    expect(updatedBackground).not.toEqual(initialBackground)
  })

  it("deletes avatar and refreshes the profile", async () => {
    const updatedUser = { ...baseUser, avatar_url: null }
    const deleteSpy = vi.spyOn(api, "delete").mockResolvedValue({ data: updatedUser } as any)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any)

    const { mockSetUser } = renderSettings()

    fireEvent.click(screen.getByRole("tab", { name: tSettings("tabs.account") }))
    await userEvent.click(await screen.findByText(tSettings("media.avatar.title")))

    const deleteButton = await screen.findByRole("button", {
      name: tSettings("media.avatar.delete"),
    })

    await act(async () => {
      fireEvent.click(deleteButton)
    })

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/users/me/avatar"))
    await waitFor(() => expect(getSpy).toHaveBeenCalled())
    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser))
  })

  it("deletes cover and refreshes the profile", async () => {
    const updatedUser = { ...baseUser, cover_url: null }
    const deleteSpy = vi.spyOn(api, "delete").mockResolvedValue({ data: updatedUser } as any)
    const getSpy = vi.spyOn(api, "get").mockResolvedValue({ data: updatedUser } as any)

    const { mockSetUser } = renderSettings()

    fireEvent.click(screen.getByRole("tab", { name: tSettings("tabs.account") }))
    await userEvent.click(await screen.findByText(tSettings("media.cover.title")))

    const deleteButton = await screen.findByRole("button", {
      name: tSettings("media.cover.remove"),
    })

    await act(async () => {
      fireEvent.click(deleteButton)
    })

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith("/users/me/cover"))
    await waitFor(() => expect(getSpy).toHaveBeenCalled())
    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(updatedUser))
  })
})

