import { StrictMode, useState, type PropsWithChildren } from "react"
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { PendingMfaState } from "@/types/Auth"
import type { User } from "@/types/User"

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  fetchCurrentUser: vi.fn(),
  translate: (key: string) => key,
}))

vi.mock("@/api/client", () => ({
  default: { post: mocks.post },
  API_UNAUTHORIZED_EVENT: "auth:unauthorized",
  resetEtagCache: vi.fn(),
  registerSigningKeyAccessor: vi.fn(),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: mocks.fetchCurrentUser,
  useProfileSync: vi.fn(),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.translate, i18n: { language: "en" } }),
}))

vi.mock("@/components/mfa/OtpEntry", () => ({
  OtpEntry: ({ onSubmit }: { onSubmit: (code: string) => void }) => (
    <button type="button" onClick={() => onSubmit("123456")}>
      Verify
    </button>
  ),
}))

import { AuthContext, useAuth } from "@/contexts/AuthContext"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import { StepUpDialog } from "@/components/mfa/StepUpDialog"
import { useEmailChange } from "@/pages/settings/hooks/useEmailChange"
import { useStepUpAction } from "@/pages/settings/hooks/useStepUpAction"
import { rotateBrowserSession } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"

const account = {
  id: "account-a",
  email: "current@example.test",
  full_name: "Account A",
  role: "student",
} as User
const otherAccount = { ...account, id: "account-b", email: "other@example.test" }

const challenge: PendingMfaState = {
  status: "mfa_required",
  reason: "step-up",
  user_id: account.id,
  session_id: "session-a",
  default_method: "totp",
  methods: [
    {
      method: "totp",
      challenge_token: "challenge-token-1234567890",
      challenge_expires_at: "2026-12-01T00:00:00Z",
      attempt_count: 0,
      attempt_limit: 5,
      remaining_attempts: 5,
    },
  ],
}

const noop = () => undefined

function EmailFlow() {
  const { loading } = useAuth()
  const { dialogId, openStepUpFor, closeStepUp, completeStepUp } = useStepUpAction()
  const email = useEmailChange({
    setSnackbar: noop,
    openStepUpFor,
  })

  return (
    <>
      <output aria-label="identity">{loading ? "pending" : "ready"}</output>
      <label>
        New email
        <input
          value={email.emailValue}
          onChange={(event) => email.setEmailValue(event.target.value)}
        />
      </label>
      <label>
        Password
        <input
          value={email.emailPassword}
          onChange={(event) => email.setEmailPassword(event.target.value)}
        />
      </label>
      <button type="button" onClick={() => void email.handleEmailSubmit()}>
        Save email
      </button>
      {dialogId !== null && (
        <StepUpDialog
          key={dialogId}
          open
          onClose={() => closeStepUp(dialogId)}
          onCompleted={() => completeStepUp(dialogId)}
        />
      )}
    </>
  )
}

function AuthHarness() {
  const [user, setUser] = useState<User | null>(account)
  const [pendingMfa, setPendingMfa] = useState<PendingMfaState | null>(null)
  const [authOperation, setAuthOperation] = useState(false)
  const [externalBusy, setExternalBusy] = useState(false)
  const busy = authOperation || externalBusy
  const actions = useAuthApi(
    user,
    setUser,
    setPendingMfa,
    noop,
    noop,
    busy,
    setAuthOperation,
    noop,
    pendingMfa
  )

  return (
    <AuthContext.Provider
      value={{
        ...actions,
        user,
        setUser,
        pendingMfa,
        loading: false,
        authOperation: busy,
        resetEtagCache: noop,
      }}
    >
      <button type="button" onClick={() => setExternalBusy(true)}>
        Start unrelated authentication
      </button>
      <button type="button" onClick={() => setExternalBusy(false)}>
        Finish unrelated authentication
      </button>
      <EmailFlow />
    </AuthContext.Provider>
  )
}

describe("email change after step-up", () => {
  beforeEach(async () => {
    vi.resetAllMocks()
    await act(async () => {
      rotateBrowserSession()
      useAuthStore.setState({ user: account, loading: false })
      await Promise.resolve()
    })
    mocks.fetchCurrentUser.mockResolvedValue(account)
  })

  it("retries a same-account email change when verification finishes during auth loading", async () => {
    let resolveVerification!: (value: { data: { user: User } }) => void
    const verification = new Promise<{ data: { user: User } }>((resolve) => {
      resolveVerification = resolve
    })
    const stepUpError = new AxiosError("step-up required")
    stepUpError.response = { status: 428 } as AxiosError["response"]
    let emailRequests = 0
    mocks.post.mockImplementation((path: string) => {
      if (path === "/users/me/email") {
        emailRequests += 1
        return emailRequests === 1
          ? Promise.reject(stepUpError)
          : Promise.resolve({ data: account })
      }
      if (path === "/auth/mfa/step-up") return Promise.resolve({ status: 202, data: challenge })
      if (path === "/auth/mfa/verify") return verification
      throw new Error(`Unexpected request: ${path}`)
    })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <AuthHarness />
      </QueryClientProvider>
    )
    fireEvent.change(screen.getByLabelText("New email"), {
      target: { value: "next@example.test" },
    })
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } })
    fireEvent.click(screen.getByRole("button", { name: "Save email" }))
    fireEvent.click(await screen.findByRole("button", { name: "Verify" }))
    await waitFor(() => expect(screen.getByLabelText("identity")).toHaveTextContent("pending"))
    expect(emailRequests).toBe(1)

    await act(async () => {
      resolveVerification({ data: { user: account } })
      await verification
    })

    await waitFor(() => expect(screen.getByLabelText("identity")).toHaveTextContent("ready"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() => expect(emailRequests).toBe(2))
  })

  it.each(["busy", "missing-profile"] as const)(
    "does not replay when verification is not accepted (%s)",
    async (outcome) => {
      const stepUpError = new AxiosError("step-up required")
      stepUpError.response = { status: 428 } as AxiosError["response"]
      let emailRequests = 0
      mocks.post.mockImplementation((path: string) => {
        if (path === "/users/me/email") {
          emailRequests += 1
          return emailRequests === 1
            ? Promise.reject(stepUpError)
            : Promise.resolve({ data: account })
        }
        if (path === "/auth/mfa/step-up") return Promise.resolve({ status: 202, data: challenge })
        if (path === "/auth/mfa/verify") return Promise.resolve({ data: {} })
        throw new Error(`Unexpected request: ${path}`)
      })

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      render(
        <QueryClientProvider client={queryClient}>
          <AuthHarness />
        </QueryClientProvider>
      )
      fireEvent.change(screen.getByLabelText("New email"), {
        target: { value: "next@example.test" },
      })
      fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } })
      fireEvent.click(screen.getByRole("button", { name: "Save email" }))
      const verify = await screen.findByRole("button", { name: "Verify" })
      if (outcome === "busy") {
        fireEvent.click(screen.getByRole("button", { name: "Start unrelated authentication" }))
        expect(screen.getByLabelText("identity")).toHaveTextContent("pending")
      }
      await act(async () => {
        fireEvent.click(verify)
        await Promise.resolve()
      })
      const stillOpen = screen.queryByRole("dialog") !== null
      if (outcome === "busy") {
        await act(async () => {
          fireEvent.click(screen.getByRole("button", { name: "Finish unrelated authentication" }))
          await Promise.resolve()
        })
      }
      expect(emailRequests).toBe(1)
      expect(stillOpen).toBe(true)
      if (outcome === "busy") {
        expect(mocks.post).not.toHaveBeenCalledWith(
          "/auth/mfa/verify",
          expect.anything(),
          expect.anything()
        )
      }
    }
  )
})

describe("step-up action coordination", () => {
  beforeEach(async () => {
    await act(async () => {
      rotateBrowserSession()
      useAuthStore.setState({ user: account, loading: false })
      await Promise.resolve()
    })
  })

  it("waits for the same account to be confirmed and replays only once in StrictMode", async () => {
    const action = vi.fn(async () => undefined)
    const wrapper = ({ children }: PropsWithChildren) => <StrictMode>{children}</StrictMode>
    const { result } = renderHook(() => useStepUpAction(), { wrapper })
    act(() => result.current.openStepUpFor(action))
    const id = result.current.dialogId!

    act(() => useAuthStore.setState({ loading: true }))
    act(() => result.current.completeStepUp(id))
    expect(action).not.toHaveBeenCalled()

    act(() => useAuthStore.setState({ loading: false }))
    await waitFor(() => expect(action).toHaveBeenCalledOnce())
    act(() => {
      result.current.completeStepUp(id)
      result.current.closeStepUp(id)
    })
    expect(action).toHaveBeenCalledOnce()
  })

  it("does not open a step-up while identity is unconfirmed", () => {
    useAuthStore.setState({ loading: true })
    const action = vi.fn(async () => undefined)
    const { result } = renderHook(() => useStepUpAction())
    act(() => result.current.openStepUpFor(action))
    expect(result.current.dialogId).toBeNull()
    expect(action).not.toHaveBeenCalled()
  })

  it("does not open a step-up after sign-out", () => {
    useAuthStore.setState({ user: null, loading: false })
    const action = vi.fn(async () => undefined)
    const { result } = renderHook(() => useStepUpAction())
    act(() => result.current.openStepUpFor(action))
    expect(result.current.dialogId).toBeNull()
    expect(action).not.toHaveBeenCalled()
  })

  it.each(["account", "session"] as const)(
    "cancels a waiting replay when its %s changes",
    async (transition) => {
      const action = vi.fn(async () => undefined)
      const { result } = renderHook(() => useStepUpAction())
      act(() => result.current.openStepUpFor(action))
      const id = result.current.dialogId!
      act(() => useAuthStore.setState({ loading: true }))
      act(() => result.current.completeStepUp(id))
      expect(action).not.toHaveBeenCalled()

      await act(async () => {
        if (transition === "account") useAuthStore.setState({ user: otherAccount })
        else rotateBrowserSession()
        await Promise.resolve()
      })
      act(() => useAuthStore.setState({ user: account, loading: false }))
      expect(action).not.toHaveBeenCalled()
    }
  )

  it.each(["account", "session"] as const)(
    "closes an open dialog when its %s changes",
    async (transition) => {
      const action = vi.fn(async () => undefined)
      const { result } = renderHook(() => useStepUpAction())
      act(() => result.current.openStepUpFor(action))
      const id = result.current.dialogId!
      await act(async () => {
        if (transition === "account") useAuthStore.setState({ user: otherAccount })
        else rotateBrowserSession()
        await Promise.resolve()
      })
      expect(result.current.dialogId).toBeNull()
      act(() => {
        useAuthStore.setState({ user: account, loading: false })
        result.current.completeStepUp(id)
      })
      expect(action).not.toHaveBeenCalled()
    }
  )

  it("ignores a canceled dialog's late completion and close after another dialog opens", async () => {
    const firstAction = vi.fn(async () => undefined)
    const secondAction = vi.fn(async () => undefined)
    const { result } = renderHook(() => useStepUpAction())
    act(() => result.current.openStepUpFor(firstAction))
    const firstId = result.current.dialogId!
    act(() => result.current.closeStepUp(firstId))
    act(() => result.current.openStepUpFor(secondAction))
    const secondId = result.current.dialogId!
    expect(secondId).not.toBe(firstId)

    act(() => {
      result.current.completeStepUp(firstId)
      result.current.closeStepUp(firstId)
    })
    expect(result.current.dialogId).toBe(secondId)
    expect(firstAction).not.toHaveBeenCalled()
    expect(secondAction).not.toHaveBeenCalled()

    act(() => {
      result.current.completeStepUp(secondId)
      // StepUpDialog calls onClose immediately after onCompleted.
      result.current.closeStepUp(secondId)
      result.current.completeStepUp(secondId)
    })
    await waitFor(() => expect(secondAction).toHaveBeenCalledOnce())
    expect(firstAction).not.toHaveBeenCalled()
  })

  it("discards pending and late dialog actions on unmount", () => {
    const action = vi.fn(async () => undefined)
    const { result, unmount } = renderHook(() => useStepUpAction())
    act(() => result.current.openStepUpFor(action))
    const id = result.current.dialogId!
    const complete = result.current.completeStepUp
    act(() => useAuthStore.setState({ loading: true }))
    act(() => complete(id))
    unmount()
    act(() => {
      useAuthStore.setState({ loading: false })
      complete(id)
    })
    expect(action).not.toHaveBeenCalled()
  })
})
