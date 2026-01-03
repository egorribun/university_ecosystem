import { useActionState, useEffect, useRef, useState } from "react"
import axios from "../api/client"
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Stack,
  InputAdornment,
  IconButton,
  LinearProgress,
  Tooltip,
} from "@mui/material"
import Visibility from "@mui/icons-material/Visibility"
import VisibilityOff from "@mui/icons-material/VisibilityOff"
import { useParams, useSearchParams, Link } from "react-router-dom"
import { useTranslation } from "react-i18next"

const RESET_URL = "/password/reset"

type ResetState = {
  status: "idle" | "success" | "error"
  error?: string
  field?: "password" | "confirm"
}

async function sha1Hex(str: string) {
  const buf = new TextEncoder().encode(str)
  const hash = await crypto.subtle.digest("SHA-1", buf)
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
}
async function isPwnedPassword(pwd: string) {
  if (!pwd) return false
  const hash = await sha1Hex(pwd)
  const prefix = hash.slice(0, 5)
  const suffix = hash.slice(5)
  const resp = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`)
  if (!resp.ok) return false
  const text = await resp.text()
  return text.split("\n").some((line) => line.split(":")[0] === suffix)
}

export default function ResetPassword() {
  const { t } = useTranslation(["auth"])
  const params = useParams<{ token?: string }>()
  const [sp] = useSearchParams()
  const token = params.token || sp.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<string>("")
  const [pwned, setPwned] = useState(false)
  const passwordRef = useRef<HTMLInputElement | null>(null)
  const confirmRef = useRef<HTMLInputElement | null>(null)

  const minLenOk = password.length >= 8
  const matchOk = confirm.length > 0 && password === confirm
  const canSubmit = token && minLenOk && matchOk

  const onPass = async (v: string) => {
    setPassword(v)
    setFeedback("")
    if (!v) {
      setStrength(null)
      setPwned(false)
      return
    }
    try {
      const { zxcvbn, zxcvbnOptions } = await import("@zxcvbn-ts/core")
      const zxcvbnCommon = await import("@zxcvbn-ts/language-common")
      zxcvbnOptions.setOptions(zxcvbnCommon)
      const res = zxcvbn(v)
      setStrength(res.score)
      const tips =
        (res.feedback?.warning || "") +
        (res.feedback?.suggestions?.length ? " · " + res.feedback.suggestions.join(" · ") : "")
      setFeedback(tips)
    } catch {
      setStrength(null)
    }
    try {
      const bad = await isPwnedPassword(v)
      if (v === password) setPwned(bad)
    } catch {}
  }

  const [resetState, resetAction, resetPending] = useActionState<ResetState, FormData>(
    async (_prev, input) => {
      if (input.get("__set_error__")) {
        return { status: "error" as const, error: String(input.get("__set_error__")) }
      }

      const pwd = String(input.get("password") ?? "")
      const confirmValue = String(input.get("confirm") ?? "")

      if (!token) {
        return { status: "error" as const, error: t("auth:reset.invalidLink") }
      }

      if (pwd !== confirmValue) {
        return {
          status: "error" as const,
          error: t("auth:register.passwordMismatch"),
          field: "confirm" as const,
        }
      }

      try {
        await axios.post(RESET_URL, { token, password: pwd })
        return { status: "success" as const }
      } catch (err: any) {
        const msg = err?.response?.data?.detail || t("auth:reset.errorGeneric")
        return { status: "error" as const, error: msg }
      }
    },
    token
      ? { status: "idle" as const }
      : { status: "error" as const, error: t("auth:reset.invalidLink") }
  )

  const resetStatus = resetState.status
  const resetErrorMessage = resetStatus === "error" ? (resetState.error ?? "") : ""

  useEffect(() => {
    if (!resetPending && resetStatus === "error" && resetState.field) {
      if (resetState.field === "password") passwordRef.current?.focus()
      else if (resetState.field === "confirm") confirmRef.current?.focus()
    }
  }, [resetPending, resetStatus, resetState.field])

  const isSuccess = resetStatus === "success"
  if (isSuccess) {
    return (
      <Box
        sx={{
          minHeight: "100vh",
          bgcolor: "var(--page-bg)",
          color: "var(--page-text)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          px: 1,
        }}
      >
        <Paper
          elevation={7}
          sx={{
            width: "100%",
            maxWidth: 460,
            p: { xs: 2, sm: 4 },
            borderRadius: { xs: 3, sm: 5 },
            bgcolor: "var(--card-bg)",
          }}
        >
          <Typography variant="h5" fontWeight={800} align="center" mb={1.5}>
            {t("auth:reset.successTitle")}
          </Typography>
          <Stack alignItems="center" spacing={1}>
            <Typography color="text.secondary" align="center">
              {t("auth:reset.successMessage")}
            </Typography>
            <Button component={Link} to="/login" variant="contained" sx={{ mt: 1 }}>
              {t("auth:actions.goToLogin")}
            </Button>
          </Stack>
        </Paper>
      </Box>
    )
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        bgcolor: "var(--page-bg)",
        color: "var(--page-text)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 1,
      }}
    >
      <Paper
        elevation={7}
        sx={{
          width: "100%",
          maxWidth: 460,
          p: { xs: 2, sm: 4 },
          borderRadius: { xs: 3, sm: 5 },
          bgcolor: "var(--card-bg)",
        }}
      >
        <Typography variant="h5" fontWeight={800} align="center" mb={1.5}>
          {t("auth:reset.title")}
        </Typography>
        <Typography color="text.secondary" align="center" sx={{ mb: 2 }}>
          {t("auth:reset.subtitle")}
        </Typography>
        <form action={resetAction} autoComplete="off">
          <Stack spacing={2}>
            <TextField
              label={t("auth:fields.password")}
              name="password"
              type={showPass ? "text" : "password"}
              value={password}
              onChange={(e) => onPass(e.target.value)}
              onKeyUp={(e) => setCapsPass((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e) => setCapsPass((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              autoFocus
              autoComplete="new-password"
              inputRef={passwordRef}
              disabled={resetPending}
              helperText={t("auth:register.passwordHint")}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title={t("auth:actions.holdReveal")}>
                      <IconButton
                        aria-label={t("auth:actions.showPassword")}
                        onMouseDown={() => setShowPass(true)}
                        onMouseUp={() => setShowPass(false)}
                        onMouseLeave={() => setShowPass(false)}
                        onClick={() => setShowPass((v) => !v)}
                        edge="end"
                        tabIndex={-1}
                      >
                        {showPass ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ),
              }}
            />
            {strength !== null && (
              <LinearProgress
                variant="determinate"
                value={[10, 30, 55, 75, 100][strength]}
                sx={{ mt: -0.5, height: 8, borderRadius: 1 }}
                aria-label={t("auth:register.passwordStrength")}
              />
            )}
            {!!feedback && (
              <Typography fontSize={13} color="text.secondary">
                {feedback}
              </Typography>
            )}
            {capsPass && (
              <Typography color="warning.main" fontSize={13}>
                {t("auth:messages.capsLock")}
              </Typography>
            )}
            {pwned && (
              <Typography color="warning.main" fontSize={13}>
                {t("auth:reset.pwnedWarning")}
              </Typography>
            )}
            <TextField
              label={t("auth:fields.confirmPassword")}
              name="confirm"
              type={showConfirm ? "text" : "password"}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyUp={(e) => setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e) => setCapsConfirm((e as any).getModifierState?.("CapsLock"))}
              fullWidth
              autoComplete="new-password"
              inputRef={confirmRef}
              disabled={resetPending}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title={t("auth:actions.holdReveal")}>
                      <IconButton
                        aria-label={t("auth:actions.showPassword")}
                        onMouseDown={() => setShowConfirm(true)}
                        onMouseUp={() => setShowConfirm(false)}
                        onMouseLeave={() => setShowConfirm(false)}
                        onClick={() => setShowConfirm((v) => !v)}
                        edge="end"
                        tabIndex={-1}
                      >
                        {showConfirm ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ),
              }}
            />
            {capsConfirm && (
              <Typography color="warning.main" fontSize={13}>
                {t("auth:messages.capsLock")}
              </Typography>
            )}
            <Box sx={{ minHeight: 22, textAlign: "center" }} aria-live="assertive">
              {resetErrorMessage && (
                <Typography color="error" fontSize={15}>
                  {resetErrorMessage}
                </Typography>
              )}
            </Box>
            <Button
              type="submit"
              variant="contained"
              size="large"
              fullWidth
              disabled={!canSubmit || resetPending}
            >
              {resetPending ? t("auth:reset.saving") : t("auth:reset.saveButton")}
            </Button>
            <Button component={Link} to="/forgot-password" variant="text">
              {t("auth:reset.linkHelp")}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  )
}
