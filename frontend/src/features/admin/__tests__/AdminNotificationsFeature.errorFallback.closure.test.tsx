import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { HttpResponse, http } from "msw"
import { QueryClient } from "@tanstack/react-query"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

const translationOverrides = vi.hoisted(() => ({
  values: new Map<string, string | undefined>(),
  topicLabel: false,
}))

vi.mock("react-i18next", async () => {
  const actual = await vi.importActual<typeof import("react-i18next")>("react-i18next")
  return {
    ...actual,
    useTranslation: (namespace?: unknown, options?: unknown) => {
      const result = actual.useTranslation(namespace as any, options as any)
      return {
        ...result,
        t: ((key: string, values?: unknown) => {
          if (translationOverrides.topicLabel && key.endsWith("topics.experimental")) {
            return "Experimental topic"
          }
          if (translationOverrides.values.has(key)) {
            return translationOverrides.values.get(key)
          }
          return result.t(key, values as any)
        }) as typeof result.t,
      }
    },
  }
})

import { AuthContext } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { resetAdminDeadLetterJobs } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"

vi.mock("@/api/notifications", async () => {
  const actual = await vi.importActual<typeof import("@/api/notifications")>("@/api/notifications")
  return {
    ...actual,
    fetchAdminUserTopics: vi.fn(actual.fetchAdminUserTopics),
    retryDeadLetterJobs: vi.fn().mockRejectedValue({ reason: "non-error rejection" }),
  }
})

import AdminNotifications from "@/pages/AdminNotifications"
import { fetchAdminUserTopics, retryDeadLetterJobs } from "@/api/notifications"

const adminUser: User = {
  id: "uuid-1",
  email: "admin@example.com",
  full_name: "Admin User",
  role: "admin",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: undefined,
  education_path: undefined,
  preferences: undefined,
  spotify_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
}

const authValue = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  user: adminUser,
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

describe("AdminNotificationsFeature defensive error handling", () => {
  beforeEach(() => {
    translationOverrides.values.clear()
    translationOverrides.topicLabel = false
    resetAdminDeadLetterJobs()
    server.use(
      http.get("*/notifications/admin/dead-letter", () =>
        HttpResponse.json({
          items: [
            {
              id: "non-error-job",
              kind: "news",
              record_id: "record-1",
              locale: "en",
              enqueued_at: new Date().toISOString(),
              claimed_at: null,
              attempts: 1,
              last_error: null,
              next_retry_at: null,
            },
          ],
          total: 1,
        })
      )
    )
  })

  it("uses the translated fallback for a non-Error mutation rejection", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    await renderWithRouter({
      ui: () => (
        <AuthContext.Provider value={authValue}>
          <AdminNotifications />
        </AuthContext.Provider>
      ),
      queryClient,
      authProvider: false,
    })

    const checkbox = await screen.findByRole("checkbox", { name: /Select job non-error-job/i })
    await userEvent.click(checkbox)
    await userEvent.click(screen.getByRole("button", { name: /Retry selected/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to update the queue.")
    queryClient.clear()
  })

  it("surfaces the backend detail for an Axios mutation rejection", async () => {
    const response = {
      data: { detail: "queue detail from backend" },
      status: 502,
      statusText: "Bad Gateway",
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    vi.mocked(retryDeadLetterJobs).mockRejectedValueOnce(
      new AxiosError("request failed", "ERR_BAD_RESPONSE", undefined, undefined, response)
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    await renderWithRouter({
      ui: () => (
        <AuthContext.Provider value={authValue}>
          <AdminNotifications />
        </AuthContext.Provider>
      ),
      queryClient,
      authProvider: false,
    })

    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Select job non-error-job/i })
    )
    await userEvent.click(screen.getByRole("button", { name: /Retry selected/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("queue detail from backend")
    queryClient.clear()
  })

  it("falls back when an Axios response detail is not a string", async () => {
    const response = {
      data: { detail: 502 },
      status: 502,
      statusText: "Bad Gateway",
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    vi.mocked(retryDeadLetterJobs).mockRejectedValueOnce(
      new AxiosError("request failed", "ERR_BAD_RESPONSE", undefined, undefined, response)
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    await renderWithRouter({
      ui: () => (
        <AuthContext.Provider value={authValue}>
          <AdminNotifications />
        </AuthContext.Provider>
      ),
      queryClient,
      authProvider: false,
    })

    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Select job non-error-job/i })
    )
    await userEvent.click(screen.getByRole("button", { name: /Retry selected/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("request failed")
    queryClient.clear()
  })

  it("uses component fallbacks when selected translations are unavailable", async () => {
    translationOverrides.values.set("admin:notifications.table.aria", undefined)
    translationOverrides.values.set("admin:notifications.table.selectAll", undefined)
    translationOverrides.values.set("admin:notifications.table.selectRow", undefined)
    translationOverrides.values.set(
      "notifications:topics.raw-topic",
      "notifications:topics.raw-topic"
    )
    translationOverrides.topicLabel = true
    vi.mocked(fetchAdminUserTopics)
      .mockResolvedValueOnce({
        user_id: "44444444-4444-4444-4444-444444444444",
        email: "experimental@example.com",
        allowed_topics: ["experimental"],
        topics: [],
      })
      .mockResolvedValueOnce({
        user_id: "55555555-5555-5555-5555-555555555555",
        email: "non-string@example.com",
        allowed_topics: [42 as unknown as string, "raw-topic"],
        topics: null as unknown as string[],
      })
    server.use(
      http.get("*/push/admin/topics/:userId", () =>
        HttpResponse.json({
          user_id: "44444444-4444-4444-4444-444444444444",
          email: "experimental@example.com",
          allowed_topics: ["experimental"],
          topics: [],
        })
      )
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    await renderWithRouter({
      ui: () => (
        <AuthContext.Provider value={authValue}>
          <AdminNotifications />
        </AuthContext.Provider>
      ),
      queryClient,
      authProvider: false,
    })

    expect(await screen.findByRole("table", { name: "Dead-letter queue" })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "Select all" })).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "Select" })).toBeInTheDocument()

    const userIdInput = await screen.findByRole("textbox")
    await userEvent.type(userIdInput, "44444444-4444-4444-4444-444444444444")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(await screen.findByText("Experimental topic")).toBeInTheDocument()

    await userEvent.clear(userIdInput)
    await userEvent.type(userIdInput, "55555555-5555-5555-5555-555555555555")
    await userEvent.click(screen.getByRole("button", { name: /Load topics/i }))
    expect(
      await screen.findByText(
        "Topics loaded for non-string@example.com (ID 55555555-5555-5555-5555-555555555555)."
      )
    ).toBeInTheDocument()
    expect(screen.getByText("raw-topic")).toBeInTheDocument()
    expect(vi.mocked(fetchAdminUserTopics)).toHaveBeenLastCalledWith(
      "55555555-5555-5555-5555-555555555555"
    )
    queryClient.clear()
  })
})
