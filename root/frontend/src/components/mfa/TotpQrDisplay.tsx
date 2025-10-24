import { useCallback, useMemo, useState } from "react"
import { Box, Stack, Typography, IconButton, Tooltip, TextField } from "@mui/material"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import { QRCodeSVG } from "qrcode.react"
import { useTranslation } from "react-i18next"

type TotpQrDisplayProps = {
  otpauthUrl: string
  secret: string
  label?: string | null
}

export const TotpQrDisplay = ({ otpauthUrl, secret, label }: TotpQrDisplayProps) => {
  const { t } = useTranslation("auth")
  const [copied, setCopied] = useState(false)

  const normalizedSecret = useMemo(() => secret.replace(/\s+/g, "").toUpperCase(), [secret])

  const handleCopy = useCallback(async () => {
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard) {
        throw new Error("clipboard unsupported")
      }
      await navigator.clipboard.writeText(normalizedSecret)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to copy secret", error)
      }
      setCopied(false)
    }
  }, [normalizedSecret])

  return (
    <Stack spacing={2} alignItems="center" textAlign="center">
      <Typography variant="h6" fontWeight={600} sx={{ color: "var(--page-text)" }}>
        {t("mfa.totp.scanHeading")}
      </Typography>
      {label ? (
        <Typography variant="body2" sx={{ color: "color-mix(in srgb, var(--page-text) 72%, transparent)" }}>
          {t("mfa.totp.accountLabel", { label })}
        </Typography>
      ) : null}
      <Box
        sx={{
          p: 2,
          borderRadius: 2,
          border: "1px solid var(--glass-border)",
          backgroundColor: "var(--card-bg)",
        }}
      >
        <QRCodeSVG value={otpauthUrl} size={192} />
      </Box>
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{
          width: "100%",
          maxWidth: 320,
        }}
      >
        <TextField
          fullWidth
          size="small"
          label={t("mfa.totp.manualHeading")}
          value={normalizedSecret}
          InputProps={{ readOnly: true }}
          sx={{
            "& .MuiOutlinedInput-root": {
              fontFamily: "monospace",
              letterSpacing: 1,
            },
          }}
        />
        <Tooltip title={copied ? t("mfa.totp.copied") : t("mfa.totp.copySecret")}>
          <span>
            <IconButton
              color={copied ? "success" : "primary"}
              onClick={() => void handleCopy()}
              aria-label={t("mfa.totp.copySecret")}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
      <Typography variant="body2" sx={{ color: "color-mix(in srgb, var(--page-text) 70%, transparent)" }}>
        {t("mfa.totp.instructions")}
      </Typography>
    </Stack>
  )
}

export default TotpQrDisplay
