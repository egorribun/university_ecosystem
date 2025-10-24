import { useCallback, useEffect, useMemo, useState } from "react"
import { Alert, Button, Stack, Typography } from "@mui/material"
import { startAuthentication } from "@simplewebauthn/browser"
import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser"
import { useTranslation } from "react-i18next"

type WebAuthnPromptProps = {
  options?: Record<string, unknown> | PublicKeyCredentialRequestOptionsJSON | null
  autoStart?: boolean
  loading?: boolean
  error?: string | null
  onResolve: (response: AuthenticationResponseJSON) => Promise<void> | void
  onStart?: () => void
}

const isRequestOptions = (
  value: Record<string, unknown> | PublicKeyCredentialRequestOptionsJSON | null | undefined
): value is PublicKeyCredentialRequestOptionsJSON => {
  if (!value || typeof value !== "object") return false
  return typeof (value as { challenge?: unknown }).challenge === "string"
}

export const WebAuthnPrompt = ({
  options,
  autoStart = false,
  loading = false,
  error,
  onResolve,
  onStart,
}: WebAuthnPromptProps) => {
  const { t } = useTranslation("auth")
  const [localError, setLocalError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const resolvedOptions = useMemo(() => {
    if (!isRequestOptions(options)) return null
    return options
  }, [options])

  const trigger = useCallback(async () => {
    if (!resolvedOptions || busy || loading) return
    setLocalError(null)
    setBusy(true)
    try {
      onStart?.()
      const credential = await startAuthentication({ optionsJSON: resolvedOptions })
      await onResolve(credential)
    } catch (err) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setLocalError(t("mfa.webauthn.errors.denied"))
      } else if (err instanceof Error) {
        setLocalError(err.message)
      } else {
        setLocalError(t("mfa.webauthn.errors.generic"))
      }
    } finally {
      setBusy(false)
    }
  }, [busy, loading, onResolve, onStart, resolvedOptions, t])

  useEffect(() => {
    if (autoStart && resolvedOptions) {
      void trigger()
    }
  }, [autoStart, resolvedOptions, trigger])

  return (
    <Stack spacing={2} alignItems="center" textAlign="center">
      <Typography variant="h6" fontWeight={600} sx={{ color: "var(--page-text)" }}>
        {t("mfa.webauthn.heading")}
      </Typography>
      <Typography
        variant="body2"
        sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
      >
        {t("mfa.webauthn.instructions")}
      </Typography>
      <Button
        variant="contained"
        onClick={() => void trigger()}
        disabled={busy || loading || !resolvedOptions}
        size="large"
      >
        {busy || loading ? t("mfa.webauthn.waiting") : t("mfa.webauthn.start")}
      </Button>
      {error || localError ? (
        <Alert severity="error" variant="outlined" sx={{ width: "100%" }}>
          {error || localError}
        </Alert>
      ) : null}
    </Stack>
  )
}

export default WebAuthnPrompt
