import { act, renderHook, waitFor } from "@testing-library/react"
import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useLoginForm } from "./useLoginFlow"
import type { PendingMfaState } from "@/types/Auth"

const mocks = vi.hoisted(() => ({
  login: vi.fn((..._args: unknown[]) => Promise.resolve(null as PendingMfaState | null)),
  navigate: vi.fn(),
  routerSearch: {} as Record<string, unknown>,
}))

vi.mock("@/contexts/AuthContext", async () => {
  const { ChallengeLockedError } =
    await vi.importActual<typeof import("@/types/Auth")>("@/types/Auth")
  return {
    useAuth: () => ({
      login: mocks.login,
      pendingMfa: null,
    }),
    ChallengeLockedError,
  }
})

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { search: mocks.routerSearch, state: null } }),
}))

vi.mock("@/api/mfa", () => ({
  resendEmailMfaChallenge: vi.fn(),
}))

vi.mock("@/utils/authUtils", () => ({
  suggestEmailDomain: (value: string) => value,
}))

vi.mock("@/utils/telemetryContext", () => ({
  captureActiveTelemetryContext: () => ({
    run: (callback: () => unknown) => callback(),
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.login.mockResolvedValue(null)
  mocks.routerSearch = {}
  window.localStorage.clear()
})

describe("login API error details", () => {
  it("shows the request error when an Axios response has an undefined detail", async () => {
    const error = new AxiosError("Gateway unavailable")
    error.response = {
      status: 502,
      headers: {},
      data: { detail: undefined },
      statusText: "Bad Gateway",
      config: {} as never,
    }
    mocks.login.mockRejectedValueOnce(error)

    const { result } = renderHook(() => useLoginForm())
    act(() => {
      result.current.form.setValue("email", "student@example.com")
      result.current.form.setValue("password", "Password123!")
    })

    await act(async () => {
      await result.current.onSubmit()
    })

    await waitFor(() => expect(result.current.submitError).toBe("Gateway unavailable"))
  })
})
