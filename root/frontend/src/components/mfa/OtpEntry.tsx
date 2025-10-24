import { FormEvent, useEffect, useMemo, useState } from "react"
import {
  Alert,
  Box,
  Button,
  FormHelperText,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material"
import { useTranslation } from "react-i18next"
import type { MfaMethod } from "@/types/Mfa"

export type OtpMethod = Extract<MfaMethod, "totp" | "recovery">

type OtpEntryProps = {
  availableMethods: OtpMethod[]
  defaultMethod?: OtpMethod | null
  loading?: boolean
  error?: string | null
  helperText?: string | null
  onSubmit: (method: OtpMethod, code: string) => Promise<void> | void
}

export const OtpEntry = ({
  availableMethods,
  defaultMethod,
  loading,
  error,
  helperText,
  onSubmit,
}: OtpEntryProps) => {
  const { t } = useTranslation("auth")
  const [activeMethod, setActiveMethod] = useState<OtpMethod>(() =>
    defaultMethod && availableMethods.includes(defaultMethod) ? defaultMethod : availableMethods[0]
  )
  const [code, setCode] = useState("")
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (defaultMethod && availableMethods.includes(defaultMethod)) {
      setActiveMethod(defaultMethod)
    }
  }, [availableMethods, defaultMethod])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = code.trim()
    if (!trimmed) {
      setLocalError(t("mfa.otp.validation.required"))
      return
    }
    setLocalError(null)
    await onSubmit(activeMethod, trimmed)
  }

  const placeholders = useMemo(
    () => ({
      totp: t("mfa.otp.placeholders.totp"),
      recovery: t("mfa.otp.placeholders.recovery"),
    }),
    [t]
  )

  const titles = useMemo(
    () => ({
      totp: t("mfa.otp.methods.totp"),
      recovery: t("mfa.otp.methods.recovery"),
    }),
    [t]
  )

  const description = useMemo(() => {
    if (activeMethod === "recovery") {
      return t("mfa.otp.descriptions.recovery")
    }
    return t("mfa.otp.descriptions.totp")
  }, [activeMethod, t])

  const derivedError = localError || error

  return (
    <Box component="form" onSubmit={handleSubmit} width="100%">
      <Stack spacing={2} alignItems="stretch">
        {availableMethods.length > 1 ? (
          <ToggleButtonGroup
            color="primary"
            value={activeMethod}
            exclusive
            onChange={(_, value: OtpMethod | null) => {
              if (!value) return
              setActiveMethod(value)
              setCode("")
              setLocalError(null)
            }}
            aria-label={t("mfa.otp.methodToggle")}
            fullWidth
          >
            {availableMethods.map((method) => (
              <ToggleButton
                key={method}
                value={method}
                sx={{ textTransform: "none", fontWeight: 600 }}
              >
                {titles[method]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        ) : (
          <Typography
            variant="subtitle1"
            fontWeight={600}
            align="center"
            sx={{ color: "var(--page-text)" }}
          >
            {titles[activeMethod]}
          </Typography>
        )}

        <Typography
          variant="body2"
          sx={{ color: "color-mix(in srgb, var(--page-text) 72%, transparent)" }}
        >
          {description}
        </Typography>

        <TextField
          autoFocus
          value={code}
          onChange={(event) => setCode(event.target.value)}
          label={titles[activeMethod]}
          placeholder={placeholders[activeMethod]}
          inputMode={activeMethod === "totp" ? "numeric" : "text"}
          fullWidth
          size="medium"
          disabled={Boolean(loading)}
          error={Boolean(derivedError)}
        />

        {derivedError ? (
          <FormHelperText error>{derivedError}</FormHelperText>
        ) : helperText ? (
          <FormHelperText>{helperText}</FormHelperText>
        ) : null}

        <Button
          type="submit"
          variant="contained"
          color="primary"
          disabled={Boolean(loading)}
          size="large"
        >
          {loading ? t("mfa.otp.submitting") : t("mfa.otp.submit")}
        </Button>

        {activeMethod === "recovery" ? (
          <Alert severity="warning" variant="outlined">
            {t("mfa.otp.recoveryWarning")}
          </Alert>
        ) : null}
      </Stack>
    </Box>
  )
}

export default OtpEntry
