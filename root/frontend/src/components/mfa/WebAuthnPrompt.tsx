import { useCallback, useEffect, useMemo, useState } from "react"
import { startAuthentication } from "@simplewebauthn/browser"
import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser"
import { useTranslation } from "react-i18next"
import { Alert, Button } from "@/components/ui"
import { cn } from "@/utils/cn"

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
    <div className="flex flex-col items-center gap-4 text-center">
      <h3 className="text-[1.1rem] font-semibold text-page-foreground">
        {t("mfa.webauthn.heading")}
      </h3>
      <p className="text-sm text-[color:color-mix(in_srgb,var(--page-text)_70%,transparent)]">
        {t("mfa.webauthn.instructions")}
      </p>
      <Button
        onClick={() => void trigger()}
        disabled={busy || loading || !resolvedOptions}
        loading={busy || loading}
        className={cn("min-w-[200px]", !resolvedOptions && "pointer-events-none opacity-60")}
      >
        {busy || loading ? t("mfa.webauthn.waiting") : t("mfa.webauthn.start")}
      </Button>
      {error || localError ? (
        <Alert tone="error" role="alert" className="max-w-md">
          {error || localError}
        </Alert>
      ) : null}
    </div>
  )
}

export default WebAuthnPrompt
