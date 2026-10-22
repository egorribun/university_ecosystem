import type { PropsWithChildren } from "react"
import React, { useCallback, useEffect, useState } from "react"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import Login from "@/pages/Login"
import { AuthContext } from "@/contexts/AuthContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import { Route as AuthRoute } from "@/routes/_auth"
import { evaluateAuthGuard } from "@/routes/guards"
import { useAuthStore } from "@/stores/useAuthStore"
import { useLogoutNoticeStore } from "@/stores/logoutNoticeStore"
import { testUser } from "@/tests/mocks/handlers"
import i18n from "@/i18n/config"
import type { PendingMfaState, SetUserArg, UserState } from "@/types/Auth"

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
  logWarning: vi.fn(),
  setPushConsent: vi.fn(),
  releasePushServerBinding: vi.fn(async () => undefined),
  hasPushConsent: vi.fn(() => false),
  syncPushForConfirmedIdentity: vi.fn(async () => null),
}))

vi.mock("@/api/client", () => ({
  default: { post: mocks.apiPost },
  API_UNAUTHORIZED_EVENT: "auth:unauthorized",
  resetEtagCache: vi.fn(),
}))

vi.mock("@/api/interceptors/etagCache", () => ({
  incrementSessionEpoch: vi.fn(),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  fetchCurrentUser: vi.fn(),
}))

vi.mock("@/push/subscribe", () => ({
  hasPushConsent: mocks.hasPushConsent,
  releasePushServerBinding: mocks.releasePushServerBinding,
  setPushConsent: mocks.setPushConsent,
  syncPushForConfirmedIdentity: mocks.syncPushForConfirmedIdentity,
}))

vi.mock("@/app/logger", () => ({ logWarning: mocks.logWarning }))

vi.mock("@/hooks/useNowPlaying", () => ({ SPOTIFY_REAUTH_EVENT: "spotify:reauth" }))
vi.mock("@/hooks/useDashboardEvents", () => ({ prefetchDashboardEvents: vi.fn() }))
vi.mock("@/hooks/useDashboardStories", () => ({ prefetchDashboardStories: vi.fn() }))
vi.mock("@/api/hooks/events", () => ({
  EVENTS_PAGE_SIZE: 20,
  prefetchEventsListQuery: vi.fn(),
}))

vi.mock("@/hooks/auth/useLoginFlow", () => ({
  useLoginForm: () => ({ activeEmail: "" }),
  useMfaFlow: () => ({ loginChallenge: null }),
}))

vi.mock("@/components/auth/LoginCredentialForm", () => ({
  LoginCredentialForm: function LoginCredentialForm() {
    const { login } = React.useContext(AuthContext)
    return (
      <button
        type="button"
        onClick={() => {
          void login("b@example.com", "incorrect-password").catch(() => undefined)
        }}
      >
        Attempt another account login
      </button>
    )
  },
}))
vi.mock("@/components/auth/MfaChallengeView", () => ({
  MfaChallengeView: () => null,
}))

function LogoutAuthProvider({ children }: PropsWithChildren) {
  const [user, setUserState] = useState<UserState>(testUser)
  const [authOperation, setAuthOperation] = useState(false)
  const [pendingMfa, setPendingMfa] = useState<PendingMfaState | null>(null)
  const setUser = useCallback((value: SetUserArg) => setUserState(value), [])
  const updatePendingMfa = useCallback((value: PendingMfaState | null) => setPendingMfa(value), [])
  const handleUnauthorized = useCallback(() => {
    setUserState(null)
    useAuthStore.setState({ user: null, loading: false })
  }, [])
  const updateSessionSigningKey = useCallback((_value: string | null) => undefined, [])
  const resetEtagCache = useCallback(() => undefined, [])
  const actions = useAuthApi(
    user,
    setUser,
    updatePendingMfa,
    handleUnauthorized,
    updateSessionSigningKey,
    authOperation,
    setAuthOperation,
    resetEtagCache,
    pendingMfa
  )

  useEffect(() => {
    useAuthStore.setState({ user, loading: false, authOperation })
  }, [authOperation, user])

  return (
    <AuthContext.Provider
      value={{
        ...actions,
        user,
        loading: false,
        authOperation,
        setUser,
        refresh: actions.refresh,
        pendingMfa,
        resetEtagCache,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

const SettingsPage = () => {
  const { logout } = React.useContext(AuthContext)
  return (
    <button type="button" onClick={() => void logout()}>
      Sign out
    </button>
  )
}

async function createLogoutRouter() {
  const root = createRootRoute({ component: () => <Outlet /> })
  const auth = createRoute({
    getParentRoute: () => root,
    id: "_auth",
    beforeLoad: ({ location }) => evaluateAuthGuard(useAuthStore.getState(), location),
    component: AuthRoute.options.component,
  })
  const settings = createRoute({
    getParentRoute: () => auth,
    path: "/settings",
    component: SettingsPage,
  })
  const login = createRoute({
    getParentRoute: () => root,
    path: "/login",
    component: Login,
  })
  const router = createRouter({
    routeTree: root.addChildren([auth.addChildren([settings]), login]),
    history: createMemoryHistory({ initialEntries: ["/settings"] }),
  })
  await router.load()
  return router
}

beforeEach(async () => {
  localStorage.clear()
  localStorage.setItem("ue:language", "en")
  useAuthStore.setState({ user: testUser, loading: false, pendingMfa: null, authOperation: false })
  useLogoutNoticeStore.getState().clear()
  mocks.apiPost.mockReset()
  mocks.apiPost.mockResolvedValue({ status: 200, data: {} })
  mocks.logWarning.mockReset()
  mocks.hasPushConsent.mockReturnValue(false)
  mocks.releasePushServerBinding.mockResolvedValue(undefined)
  await act(async () => {
    await i18n.changeLanguage("en")
  })
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  useLogoutNoticeStore.getState().clear()
})

describe("logout feedback across the auth redirect", () => {
  it("keeps a server-unconfirmed alert after the protected route unmounts", async () => {
    let rejectLogout: ((reason: Error) => void) | undefined
    let logoutResponseSettled = false
    mocks.apiPost.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectLogout = (reason) => {
            logoutResponseSettled = true
            reject(reason)
          }
        })
    )
    mocks.apiPost.mockRejectedValueOnce(new Error("login was not accepted"))
    const router = await createLogoutRouter()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <LogoutAuthProvider>
            <RouterProvider router={router as never} />
          </LogoutAuthProvider>
        </LanguageProvider>
      </QueryClientProvider>
    )

    try {
      fireEvent.click(screen.getByRole("button", { name: "Sign out" }))
      await waitFor(() => expect(mocks.apiPost).toHaveBeenCalledWith("/auth/logout"))
      expect(router.state.location.pathname).toBe("/settings")
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()

      await act(async () => {
        if (!rejectLogout) throw new Error("logout request was not started")
        rejectLogout(new Error("server response included private transport details"))
      })

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Sign-out could not be confirmed. Your session may still be active on the server."
      )
      expect(router.state.location.pathname).toBe("/login")
      expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument()
      expect(mocks.logWarning).toHaveBeenCalledWith(
        "Server logout could not be confirmed; local cleanup will continue"
      )

      fireEvent.click(screen.getByRole("button", { name: "Attempt another account login" }))
      await waitFor(() =>
        expect(mocks.apiPost).toHaveBeenCalledWith(
          "/auth/login",
          expect.any(URLSearchParams),
          expect.objectContaining({ skipRateLimitQueue: true })
        )
      )
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Sign-out could not be confirmed. Your session may still be active on the server."
      )
      expect(router.state.location.pathname).toBe("/login")
    } finally {
      if (!logoutResponseSettled && rejectLogout) {
        await act(async () => {
          rejectLogout?.(new Error("test cleanup released the pending logout response"))
          await Promise.resolve()
        })
      }
    }
  })
})
