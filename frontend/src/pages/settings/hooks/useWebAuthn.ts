import { useState, useCallback, useMemo, useRef, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { startRegistration, browserSupportsWebAuthn } from "@simplewebauthn/browser"

import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import {
  startWebAuthnRegistration,
  confirmWebAuthnRegistration,
  listWebAuthnCredentials,
  deleteWebAuthnCredential,
} from "@/api/mfa"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"

interface WebAuthnCredential {
  id: string
  label: string
  created_at: string
  last_used_at: string | null
}

interface PublicKeyCredentialCreationOptionsJSON {
  challenge: string
  pubKeyCredParams: { type: "public-key"; alg: number }[]
  rp: { id: string; name: string }
  user: { id: string; name: string; displayName: string }
  timeout: number
  attestation: AttestationConveyancePreference
  excludeCredentials: { id: string; type: "public-key" }[]
  authenticatorSelection?: AuthenticatorSelectionCriteria
  extensions?: AuthenticationExtensionsClientInputs
}

const isCreationOptions = (value: unknown): value is PublicKeyCredentialCreationOptionsJSON => {
  if (!value || typeof value !== "object") return false
  const candidate = value as {
    challenge?: unknown
    pubKeyCredParams?: unknown
  }
  return typeof candidate.challenge === "string" && Array.isArray(candidate.pubKeyCredParams)
}

const resolveDetailMessage = (error: unknown, fallback: string): string => {
  if (isAxiosError(error) && error.response?.data?.detail) {
    return String(error.response.data.detail)
  }
  return error instanceof Error ? error.message : fallback
}

interface UseWebAuthnOptions {
  setSnackbar: SetSnackbar
  tabActive?: boolean
  openStepUpFor?: (action: () => Promise<void>) => void
}

export function useWebAuthn({ setSnackbar, tabActive, openStepUpFor }: UseWebAuthnOptions) {
  const { t } = useTranslation(["settings", "common"])
  const { setUser } = useAuth()
  const queryClient = useQueryClient()

  const [isAdding, setIsAdding] = useState(false)
  const [label, setLabel] = useState("")
  const [busy, setBusy] = useState(false)
  const [credentials, setCredentials] = useState<WebAuthnCredential[]>([])
  const [credentialsLoading, setCredentialsLoading] = useState(false)

  // Store challenge token from registration start
  const challengeTokenRef = useRef<string | null>(null)

  const supported = useMemo(() => browserSupportsWebAuthn(), [])

  const refreshUser = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const fetchCredentials = useCallback(async () => {
    setCredentialsLoading(true)
    try {
      const response = await listWebAuthnCredentials()
      setCredentials(Array.isArray(response) ? (response as WebAuthnCredential[]) : [])
    } catch {
      setCredentials([])
    } finally {
      setCredentialsLoading(false)
    }
  }, [])

  // Initial fetch when tab becomes active
  useEffect(() => {
    if (tabActive) {
      void fetchCredentials()
    }
  }, [tabActive, fetchCredentials])

  const openDialog = useCallback(() => {
    setLabel("")
    setIsAdding(true)
  }, [])

  const closeDialog = useCallback(() => {
    setIsAdding(false)
    setLabel("")
    challengeTokenRef.current = null
  }, [])

  const register = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (busy || !label.trim()) return

      setBusy(true)
      try {
        // Step 1: Start registration and get options from server
        const { publicKey, challenge_token } = await startWebAuthnRegistration()

        if (!isCreationOptions(publicKey)) {
          throw new Error("Invalid WebAuthn options received from server")
        }

        challengeTokenRef.current = challenge_token

        // Step 2: Trigger browser WebAuthn ceremony
        const credential = await startRegistration({ optionsJSON: publicKey })

        // Step 3: Send credential back to server for verification
        await confirmWebAuthnRegistration({
          challenge: challenge_token,
          response: credential,
          label: label.trim(),
        })

        await refreshUser()
        await fetchCredentials()

        setSnackbar({
          text: t("settings:security.webauthn.snackbar.registered"),
          severity: "success",
        })
        closeDialog()
      } catch (error) {
        if (
          !options?.skipStepUp &&
          isAxiosError(error) &&
          error.response?.status === 428 &&
          openStepUpFor
        ) {
          openStepUpFor(async () => {
            await register({ skipStepUp: true })
          })
          return
        }
        const message = resolveDetailMessage(
          error,
          t("settings:security.webauthn.snackbar.registrationFailed")
        )
        setSnackbar({ text: message, severity: "error" })
      } finally {
        setBusy(false)
      }
    },
    [busy, closeDialog, fetchCredentials, label, openStepUpFor, refreshUser, setSnackbar, t]
  )

  const remove = useCallback(
    async (credentialId: string, options?: { skipStepUp?: boolean }) => {
      try {
        await deleteWebAuthnCredential(credentialId)
        await refreshUser()
        await fetchCredentials()
        setSnackbar({
          text: t("settings:security.webauthn.snackbar.deleted"),
          severity: "success",
        })
      } catch (error) {
        if (
          !options?.skipStepUp &&
          isAxiosError(error) &&
          error.response?.status === 428 &&
          openStepUpFor
        ) {
          openStepUpFor(async () => {
            await remove(credentialId, { skipStepUp: true })
          })
          return
        }
        const message = resolveDetailMessage(
          error,
          t("settings:security.webauthn.snackbar.deleteFailed")
        )
        setSnackbar({ text: message, severity: "error" })
      }
    },
    [fetchCredentials, openStepUpFor, refreshUser, setSnackbar, t]
  )

  return {
    supported,
    isAdding,
    setIsAdding,
    label,
    setLabel,
    busy,
    credentials,
    credentialsLoading,
    openDialog,
    closeDialog,
    handleRegister: register,
    handleDelete: remove,
    fetchCredentials,
  }
}
