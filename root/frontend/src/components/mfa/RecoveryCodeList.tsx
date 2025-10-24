import { Fragment, useCallback, useState } from "react"
import { Alert, Box, Button, Divider, Stack, Typography } from "@mui/material"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import { useTranslation } from "react-i18next"

export type RecoveryCodeEntry = {
  code: string
  usedAt?: string | null
}

type RecoveryCodeListProps = {
  codes: RecoveryCodeEntry[]
  allowCopy?: boolean
}

export const RecoveryCodeList = ({ codes, allowCopy = true }: RecoveryCodeListProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)

  const handleCopyAll = useCallback(async () => {
    if (!allowCopy) return
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("clipboard unsupported")
      }
      const payload = codes.map((entry) => entry.code).join("\n")
      await navigator.clipboard.writeText(payload)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to copy recovery codes", error)
      }
      setCopied(false)
    }
  }, [allowCopy, codes])

  if (!codes.length) {
    return (
      <Alert severity="info" variant="outlined">
        {t("mfa.recovery.empty")}
      </Alert>
    )
  }

  return (
    <Stack spacing={2} alignItems="stretch">
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ color: "var(--page-text)" }}>
          {t("mfa.recovery.title")}
        </Typography>
        {allowCopy ? (
          <Button
            variant="outlined"
            size="small"
            startIcon={<ContentCopyIcon fontSize="small" />}
            onClick={() => void handleCopyAll()}
          >
            {copied ? t("mfa.recovery.copied") : t("mfa.recovery.copyAll")}
          </Button>
        ) : null}
      </Stack>
      <Typography
        variant="body2"
        sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}
      >
        {t("mfa.recovery.instructions")}
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "repeat(1, minmax(0, 1fr))", sm: "repeat(2, minmax(0, 1fr))" },
          gap: 1,
        }}
      >
        {codes.map((entry, index) => (
          <Fragment key={entry.code}>
            <Box
              sx={{
                borderRadius: 1.5,
                border: "1px solid var(--glass-border)",
                backgroundColor: "color-mix(in srgb, var(--page-text) 4%, transparent)",
                px: 2,
                py: 1.5,
                fontFamily: "monospace",
                letterSpacing: 1,
                fontSize: "1rem",
                textAlign: "center",
                color: entry.usedAt
                  ? "color-mix(in srgb, var(--page-text) 50%, transparent)"
                  : "var(--page-text)",
              }}
            >
              {entry.code}
            </Box>
            {(index + 1) % 2 === 0 ? <Divider sx={{ display: { sm: "none" } }} /> : null}
          </Fragment>
        ))}
      </Box>
      <Alert severity="warning" variant="outlined">
        {t("mfa.recovery.warning")}
      </Alert>
    </Stack>
  )
}

export default RecoveryCodeList
