import { renderHook, act, waitFor } from "@testing-library/react"
import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useWebAuthn } from "./useWebAuthn"

type RegistrationStartResponse = {
  publicKey: unknown
  challenge_token: string
}

const mocks = vi.hoisted(() => ({
  browserSupportsWebAuthn: vi.fn(() => true),
  startRegistration: vi.fn(async () => ({ id: "credential-response" })),
  startWebAuthnRegistration: vi.fn<() => Promise<RegistrationStartResponse>>(async () => ({
    publicKey: { challenge: "challenge", pubKeyCredParams: [] },
    challenge_token: "challenge-token",
  })),
  confirmWebAuthnRegistration: vi.fn(async () => undefined),
  listWebAuthnCredentials: vi.fn<() => Promise<unknown>>(async () => []),
  deleteWebAuthnCredential: vi.fn(async () => undefined),
  fetchQuery: vi.fn(async () => ({ id: "fresh-user" })),
  setUser: vi.fn(),
  t: vi.fn((key: string) => key),
}))

vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: mocks.browserSupportsWebAuthn,
  startRegistration: mocks.startRegistration,
}))

vi.mock("@/api/mfa", () => ({
  startWebAuthnRegistration: mocks.startWebAuthnRegistration,
  confirmWebAuthnRegistration: mocks.confirmWebAuthnRegistration,
  listWebAuthnCredentials: mocks.listWebAuthnCredentials,
  deleteWebAuthnCredential: mocks.deleteWebAuthnCredential,
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ setUser: mocks.setUser }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ fetchQuery: mocks.fetchQuery }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: vi.fn(),
}))

const validOptions = {
  challenge: "challenge",
  pubKeyCredParams: [],
}

const makeAxiosError = (status: number, detail?: string) => {
  const error = new AxiosError("request failed")
  error.response = {
    status,
    headers: {},
    data: detail === undefined ? {} : { detail },
    statusText: "",
    config: {} as never,
  }
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.browserSupportsWebAuthn.mockReturnValue(true)
  mocks.startRegistration.mockResolvedValue({ id: "credential-response" })
  mocks.startWebAuthnRegistration.mockResolvedValue({
    publicKey: validOptions,
    challenge_token: "challenge-token",
  })
  mocks.confirmWebAuthnRegistration.mockResolvedValue(undefined)
  mocks.listWebAuthnCredentials.mockResolvedValue([])
  mocks.deleteWebAuthnCredential.mockResolvedValue(undefined)
  mocks.fetchQuery.mockResolvedValue({ id: "fresh-user" })
})

describe("useWebAuthn — loading and dialog state", () => {
  it("loads credentials when the settings tab becomes active", async () => {
    mocks.listWebAuthnCredentials.mockResolvedValue([
      { id: "cred-1", label: "Laptop", created_at: "2026-01-01", last_used_at: null },
    ])
    const { result } = renderHook(() => useWebAuthn({ setSnackbar: vi.fn(), tabActive: true }))

    await waitFor(() => expect(result.current.credentials).toHaveLength(1))
    expect(result.current.credentials[0]?.label).toBe("Laptop")
    expect(result.current.credentialsLoading).toBe(false)
  })

  it("normalizes a non-array credential response and tolerates loading failure", async () => {
    mocks.listWebAuthnCredentials.mockResolvedValueOnce({ items: [] })
    const { result } = renderHook(() => useWebAuthn({ setSnackbar: vi.fn(), tabActive: true }))
    await waitFor(() => expect(result.current.credentialsLoading).toBe(false))
    expect(result.current.credentials).toEqual([])

    mocks.listWebAuthnCredentials.mockRejectedValueOnce(new Error("offline"))
    await act(async () => {
      await result.current.fetchCredentials()
    })
    expect(result.current.credentials).toEqual([])
    expect(result.current.credentialsLoading).toBe(false)
  })

  it("reports browser support and resets dialog state on open/close", () => {
    const { result } = renderHook(() => useWebAuthn({ setSnackbar: vi.fn(), tabActive: false }))
    expect(result.current.supported).toBe(true)

    act(() => {
      result.current.setLabel("Old label")
      result.current.openDialog()
    })
    expect(result.current.isAdding).toBe(true)
    expect(result.current.label).toBe("")

    act(() => {
      result.current.setLabel("New label")
      result.current.closeDialog()
    })
    expect(result.current.isAdding).toBe(false)
    expect(result.current.label).toBe("")
  })
})

describe("useWebAuthn — registration", () => {
  it("ignores registration while busy or when the label is blank", async () => {
    const { result } = renderHook(() => useWebAuthn({ setSnackbar: vi.fn() }))

    await act(async () => {
      await result.current.handleRegister()
    })
    expect(mocks.startWebAuthnRegistration).not.toHaveBeenCalled()

    act(() => result.current.setLabel("   "))
    await act(async () => {
      await result.current.handleRegister()
    })
    expect(mocks.startWebAuthnRegistration).not.toHaveBeenCalled()
  })

  it("completes registration, refreshes user/credentials, and closes the dialog", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useWebAuthn({ setSnackbar }))
    act(() => {
      result.current.openDialog()
      result.current.setLabel("  Security key  ")
    })

    await act(async () => {
      await result.current.handleRegister()
    })

    expect(mocks.startRegistration).toHaveBeenCalledWith({ optionsJSON: validOptions })
    expect(mocks.confirmWebAuthnRegistration).toHaveBeenCalledWith({
      challenge: "challenge-token",
      response: { id: "credential-response" },
      label: "Security key",
    })
    expect(mocks.fetchQuery).toHaveBeenCalled()
    expect(mocks.setUser).toHaveBeenCalledWith({ id: "fresh-user" })
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.webauthn.snackbar.registered",
      severity: "success",
    })
    expect(result.current.isAdding).toBe(false)
    expect(result.current.busy).toBe(false)
  })

  it("rejects malformed server options with the registration error fallback", async () => {
    const setSnackbar = vi.fn()
    mocks.startWebAuthnRegistration.mockResolvedValueOnce({
      publicKey: null,
      challenge_token: "bad-token",
    })
    const { result } = renderHook(() => useWebAuthn({ setSnackbar }))
    act(() => result.current.setLabel("Key"))

    await act(async () => {
      await result.current.handleRegister()
    })

    expect(setSnackbar).toHaveBeenCalledWith({
      text: "Invalid WebAuthn options received from server",
      severity: "error",
    })
    expect(mocks.startRegistration).not.toHaveBeenCalled()
  })

  it("opens step-up and retries registration when the server returns 428", async () => {
    const setSnackbar = vi.fn()
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    mocks.startWebAuthnRegistration.mockRejectedValueOnce(makeAxiosError(428))
    const { result } = renderHook(() => useWebAuthn({ setSnackbar, openStepUpFor }))
    act(() => result.current.setLabel("Key"))

    await act(async () => {
      await result.current.handleRegister()
    })
    expect(openStepUpFor).toHaveBeenCalledTimes(1)
    expect(setSnackbar).not.toHaveBeenCalled()

    await act(async () => {
      await retry?.()
    })
    expect(mocks.confirmWebAuthnRegistration).toHaveBeenCalled()
    expect(setSnackbar).toHaveBeenCalledWith(expect.objectContaining({ severity: "success" }))
  })

  it("uses Axios detail and unknown-error fallbacks for registration failures", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useWebAuthn({ setSnackbar }))
    act(() => result.current.setLabel("Key"))

    mocks.startWebAuthnRegistration.mockRejectedValueOnce(
      makeAxiosError(400, "Registration denied")
    )
    await act(async () => {
      await result.current.handleRegister()
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "Registration denied", severity: "error" })

    mocks.startWebAuthnRegistration.mockRejectedValueOnce({ reason: "unknown" })
    await act(async () => {
      await result.current.handleRegister()
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.webauthn.snackbar.registrationFailed",
      severity: "error",
    })
  })

  it("reports a second step-up failure without reopening the step-up flow", async () => {
    const setSnackbar = vi.fn()
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    mocks.startWebAuthnRegistration.mockRejectedValueOnce(makeAxiosError(428))
    const { result } = renderHook(() => useWebAuthn({ setSnackbar, openStepUpFor }))
    act(() => result.current.setLabel("Key"))

    await act(async () => {
      await result.current.handleRegister()
    })
    mocks.startWebAuthnRegistration.mockRejectedValueOnce(makeAxiosError(428))

    await act(async () => {
      await retry?.()
    })

    expect(openStepUpFor).toHaveBeenCalledTimes(1)
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "request failed",
      severity: "error",
    })
  })
})

describe("useWebAuthn — deletion", () => {
  it("deletes a credential, refreshes state, and reports success", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useWebAuthn({ setSnackbar }))

    await act(async () => {
      await result.current.handleDelete("cred-1")
    })

    expect(mocks.deleteWebAuthnCredential).toHaveBeenCalledWith("cred-1")
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:security.webauthn.snackbar.deleted",
      severity: "success",
    })
  })

  it("opens step-up and retries deletion on 428", async () => {
    const setSnackbar = vi.fn()
    let retry: (() => Promise<void>) | undefined
    const openStepUpFor = vi.fn((action: () => Promise<void>) => {
      retry = action
    })
    mocks.deleteWebAuthnCredential.mockRejectedValueOnce(makeAxiosError(428))
    const { result } = renderHook(() => useWebAuthn({ setSnackbar, openStepUpFor }))

    await act(async () => {
      await result.current.handleDelete("cred-2")
    })
    expect(openStepUpFor).toHaveBeenCalledTimes(1)

    await act(async () => {
      await retry?.()
    })
    expect(mocks.deleteWebAuthnCredential).toHaveBeenCalledTimes(2)
    expect(setSnackbar).toHaveBeenCalledWith(expect.objectContaining({ severity: "success" }))
  })

  it("uses Axios detail, Error message, and fallback text for deletion failures", async () => {
    const setSnackbar = vi.fn()
    const { result } = renderHook(() => useWebAuthn({ setSnackbar }))

    mocks.deleteWebAuthnCredential.mockRejectedValueOnce(makeAxiosError(400, "Delete denied"))
    await act(async () => {
      await result.current.handleDelete("cred-3")
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "Delete denied", severity: "error" })

    mocks.deleteWebAuthnCredential.mockRejectedValueOnce(new Error("Delete failed"))
    await act(async () => {
      await result.current.handleDelete("cred-3")
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({ text: "Delete failed", severity: "error" })

    mocks.deleteWebAuthnCredential.mockRejectedValueOnce("unknown")
    await act(async () => {
      await result.current.handleDelete("cred-3", { skipStepUp: true })
    })
    expect(setSnackbar).toHaveBeenLastCalledWith({
      text: "settings:security.webauthn.snackbar.deleteFailed",
      severity: "error",
    })
  })
})
