import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, Link } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Stack,
  InputAdornment,
  IconButton,
  useMediaQuery,
  CircularProgress,
  Checkbox,
  FormControlLabel,
  Chip,
  Tooltip,
  Alert,
} from "@mui/material"
import Visibility from "@mui/icons-material/Visibility"
import VisibilityOff from "@mui/icons-material/VisibilityOff"
import { useTranslation } from "react-i18next"
import OtpEntry, { type OtpMethod } from "@/components/mfa/OtpEntry"
import WebAuthnPrompt from "@/components/mfa/WebAuthnPrompt"
import type { MfaMethod } from "@/types/Mfa"
import type { AuthenticationResponseJSON } from "@simplewebauthn/browser"

function levenshtein(a: string, b: string) {
  const m = a.length,
    n = b.length
  if (!m) return n
  if (!n) return m
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 0; i <= m; i++) dp[i][0] = i
  for (let j = 0; j <= n; j++) dp[0][j] = j
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    }
  }
  return dp[m][n]
}

const COMMON_EMAIL_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "icloud.com",
  "mail.ru",
  "bk.ru",
  "list.ru",
  "inbox.ru",
  "yandex.ru",
  "yandex.com",
  "rambler.ru",
  "proton.me",
]
const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function suggestEmailDomain(email: string) {
  const at = email.indexOf("@")
  if (at < 0) return null
  const local = email.slice(0, at).trim()
  const dom = email
    .slice(at + 1)
    .trim()
    .toLowerCase()
  if (!local || !dom) return null
  if (COMMON_EMAIL_DOMAINS.includes(dom)) return null
  let best: { d: string; dist: number } | null = null
  for (const cand of COMMON_EMAIL_DOMAINS) {
    const dist = levenshtein(dom, cand)
    if (dist <= 2 && (!best || dist < best.dist)) best = { d: cand, dist }
  }
  return best ? `${local}@${best.d}` : null
}

const Login = () => {
  const { t } = useTranslation(["auth"])
  const savedEmail = useRef<string>(localStorage.getItem("auth:lastEmail") || "")
  const [remember, setRemember] = useState<boolean>(
    () => localStorage.getItem("auth:remember") === "1"
  )
  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [emailMirror, setEmailMirror] = useState(savedEmail.current)

  const navigate = useNavigate()
  const { login, pendingMfa, submitMfaChallenge } = useAuth()
  const isMobile = useMediaQuery("(max-width:600px)")

  const emailRef = useRef<HTMLInputElement | null>(null)
  const passwordRef = useRef<HTMLInputElement | null>(null)

  const currentEmail = (emailRef.current?.value ?? emailMirror ?? "").trim()
  const emailValid = useMemo(
    () => currentEmail.length === 0 || emailRe.test(currentEmail),
    [currentEmail]
  )

  const [pendingEmail, setPendingEmail] = useState<string | null>(
    savedEmail.current ? savedEmail.current : null
  )
  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "webauthn" | "general" | null>(null)

  const loginChallenge = useMemo(
    () => (pendingMfa?.reason === "login" ? pendingMfa : null),
    [pendingMfa]
  )

  const otpMethods = useMemo<OtpMethod[]>(() => {
    if (!loginChallenge) return []
    const set = new Set<OtpMethod>()
    for (const entry of loginChallenge.methods) {
      if (entry.method === "totp" || entry.method === "recovery") {
        set.add(entry.method)
      }
    }
    return Array.from(set)
  }, [loginChallenge])

  const otpDefaultMethod = useMemo(() => {
    if (!loginChallenge) return null
    const preferred = loginChallenge.default_method
    if (preferred === "totp" || preferred === "recovery") return preferred
    if (otpMethods.includes("totp")) return "totp"
    if (otpMethods.includes("recovery")) return "recovery"
    return null
  }, [loginChallenge, otpMethods])

  const webAuthnChallenge = useMemo(
    () => loginChallenge?.methods.find((entry) => entry.method === "webauthn") ?? null,
    [loginChallenge]
  )

  useEffect(() => {
    if (!loginChallenge) {
      setMfaBusy(false)
      setMfaError(null)
      setMfaErrorSource(null)
    }
  }, [loginChallenge])

  useEffect(() => {
    const t1 = setTimeout(() => {
      if (emailRef.current && emailRef.current.value && !emailMirror)
        setEmailMirror(emailRef.current.value)
      if (passwordRef.current && passwordRef.current.value) setCaps(false)
    }, 250)
    const t2 = setTimeout(() => {
      if (emailRef.current && emailRef.current.value && !emailMirror)
        setEmailMirror(emailRef.current.value)
    }, 1000)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [])

  const applySuggestion = () => {
    if (emailSuggestion && emailRef.current) {
      emailRef.current.value = emailSuggestion
      setEmailMirror(emailSuggestion)
      setEmailSuggestion(null)
    }
  }

  const handleEmailBlur = () => {
    const val = (emailRef.current?.value || "").trim()
    const s = suggestEmailDomain(val)
    setEmailSuggestion(s && s !== val ? s : null)
  }
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const username = String(formData.get("username") ?? "").trim()
    const passwordValue = String(formData.get("password") ?? "")

    if (!emailRe.test(username)) {
      setSubmitError(t("auth:messages.invalidEmail"))
      emailRef.current?.focus()
      return
    }

    if (!passwordValue) {
      setSubmitError(t("auth:messages.passwordRequired"))
      passwordRef.current?.focus()
      return
    }

    setSubmitError(null)
    setSubmitting(true)
    setPendingEmail(username)
    try {
      const challenge = await login(username, passwordValue)

      if (remember) {
        localStorage.setItem("auth:lastEmail", username)
        savedEmail.current = username
      }
      localStorage.setItem("auth:remember", remember ? "1" : "0")

      if (challenge) {
        setMfaError(null)
        setMfaErrorSource(null)
        return
      }

      navigate("/dashboard")
    } catch (err) {
      const message = err instanceof Error && err.message ? err.message : t("auth:login.error")
      setSubmitError(message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleOtpVerify = useCallback(
    async (method: Extract<MfaMethod, "totp" | "recovery">, code: string) => {
      if (!loginChallenge) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }
      const challenge = loginChallenge.methods.find((entry) => entry.method === method)
      if (!challenge) {
        setMfaError(t("auth:mfa.errors.missingChallenge"))
        setMfaErrorSource("general")
        return
      }

      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)

      try {
        await submitMfaChallenge({
          method,
          code,
          challengeToken: challenge.challenge_token,
        })
        navigate("/dashboard")
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : t("auth:mfa.errors.generic")
        setMfaError(message)
        setMfaErrorSource("totp")
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, navigate, submitMfaChallenge, t]
  )

  const handleWebAuthnVerify = useCallback(
    async (credential: AuthenticationResponseJSON) => {
      if (!loginChallenge || !webAuthnChallenge) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }
      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)
      try {
        await submitMfaChallenge({
          method: "webauthn",
          credential: credential as unknown as Record<string, unknown>,
          challengeToken: webAuthnChallenge.challenge_token,
        })
        navigate("/dashboard")
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : t("auth:mfa.errors.generic")
        setMfaError(message)
        setMfaErrorSource("webauthn")
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, navigate, submitMfaChallenge, t, webAuthnChallenge]
  )

  const activeEmail = pendingEmail || currentEmail || savedEmail.current || ""
  const generalMfaError = mfaErrorSource === "general" ? mfaError : null

  if (loginChallenge) {
    return (
      <Box
        sx={{
          minHeight: "100dvh",
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
            maxWidth: 440,
            p: { xs: 2, sm: 4 },
            borderRadius: { xs: 3, sm: 5 },
            boxShadow: 8,
            bgcolor: "var(--card-bg)",
            transition: "background 0.22s, box-shadow 0.22s",
          }}
        >
          <Stack spacing={2.5}>
            <Typography variant={isMobile ? "h5" : "h4"} fontWeight={700} align="center">
              {t("auth:mfa.verifyTitle")}
            </Typography>
            <Typography
              variant="body2"
              align="center"
              sx={{ color: "color-mix(in srgb, var(--page-text) 72%, transparent)" }}
            >
              {t("auth:mfa.verifySubtitle", { email: activeEmail || t("auth:mfa.unknownEmail") })}
            </Typography>
            {generalMfaError ? (
              <Alert severity="error" variant="outlined">
                {generalMfaError}
              </Alert>
            ) : null}
            {otpMethods.length ? (
              <OtpEntry
                availableMethods={otpMethods}
                defaultMethod={otpDefaultMethod ?? undefined}
                loading={mfaBusy}
                error={mfaErrorSource === "totp" ? mfaError : null}
                helperText={t("auth:mfa.otpHint")}
                onSubmit={handleOtpVerify}
              />
            ) : null}
            {webAuthnChallenge ? (
              <WebAuthnPrompt
                options={webAuthnChallenge.options ?? null}
                autoStart
                loading={mfaBusy}
                error={mfaErrorSource === "webauthn" ? (mfaError ?? undefined) : undefined}
                onResolve={handleWebAuthnVerify}
              />
            ) : null}
            {!otpMethods.length && !webAuthnChallenge ? (
              <Alert severity="warning" variant="outlined">
                {t("auth:mfa.noMethods")}
              </Alert>
            ) : null}
            <Button
              variant="text"
              color="inherit"
              onClick={() => window.location.reload()}
              sx={{ mt: 1 }}
            >
              {t("auth:mfa.startOver")}
            </Button>
          </Stack>
        </Paper>
      </Box>
    )
  }

  return (
    <Box
      sx={{
        minHeight: "100dvh",
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
          maxWidth: 400,
          p: { xs: 2, sm: 4 },
          borderRadius: { xs: 3, sm: 5 },
          boxShadow: 8,
          bgcolor: "var(--card-bg)",
          transition: "background 0.22s, box-shadow 0.22s",
        }}
      >
        <form noValidate autoComplete="on" onSubmit={handleSubmit}>
          <Typography variant={isMobile ? "h5" : "h4"} fontWeight={700} align="center" mb={3}>
            {t("auth:login.title")}
          </Typography>
          <Stack spacing={2}>
            <TextField
              label={t("auth:fields.email")}
              name="username"
              type="email"
              fullWidth
              variant="outlined"
              defaultValue={savedEmail.current}
              inputRef={emailRef}
              onChange={(e) => setEmailMirror(e.target.value)}
              onBlur={handleEmailBlur}
              autoComplete="username"
              autoFocus
              disabled={submitting}
              error={!emailValid}
              helperText={!emailValid ? t("auth:messages.invalidFormat") : " "}
              inputProps={{
                inputMode: "email",
                autoCapitalize: "none",
                autoCorrect: "off",
                spellCheck: "false",
              }}
              required
            />
            {emailSuggestion && (
              <Box sx={{ mt: -1.5 }}>
                <Chip
                  size="small"
                  variant="outlined"
                  color="primary"
                  label={t("auth:messages.emailSuggestion", { suggestion: emailSuggestion })}
                  onClick={applySuggestion}
                />
              </Box>
            )}
            <TextField
              label={t("auth:fields.password")}
              name="password"
              type={showPassword ? "text" : "password"}
              fullWidth
              variant="outlined"
              inputRef={passwordRef}
              onKeyUp={(e) => setCaps((e as any).getModifierState?.("CapsLock"))}
              onKeyDown={(e) => setCaps((e as any).getModifierState?.("CapsLock"))}
              autoComplete="current-password"
              disabled={submitting}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title={t("auth:actions.holdReveal")}>
                      <IconButton
                        aria-label={t("auth:actions.showPassword")}
                        onMouseDown={() => setShowPassword(true)}
                        onMouseUp={() => setShowPassword(false)}
                        onMouseLeave={() => setShowPassword(false)}
                        onClick={() => setShowPassword((v) => !v)}
                        edge="end"
                        tabIndex={-1}
                        sx={{ color: "var(--page-text)" }}
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ),
              }}
              required
            />
            <Box sx={{ minHeight: 20, textAlign: "left" }}>
              {caps && (
                <Typography color="warning.main" fontSize={13}>
                  {t("auth:messages.capsLock")}
                </Typography>
              )}
            </Box>
            <Box
              sx={{
                minHeight: 22,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              aria-live="assertive"
            >
              {submitError && (
                <Typography color="error" fontSize={15}>
                  {submitError}
                </Typography>
              )}
            </Box>
            <FormControlLabel
              control={
                <Checkbox
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  disabled={submitting}
                />
              }
              label={t("auth:actions.rememberEmail")}
              sx={{ mt: -0.5 }}
            />
            <Button
              type="submit"
              variant="contained"
              size="large"
              fullWidth
              disabled={submitting}
              sx={{
                mt: 1,
                fontWeight: 600,
                borderRadius: 2,
                fontSize: 17,
                py: 1.2,
                bgcolor: "var(--nav-link)",
                color: "#fff",
                touchAction: "manipulation",
                "&:hover": { bgcolor: "var(--nav-link-hover)" },
              }}
            >
              {submitting ? (
                <CircularProgress size={26} color="inherit" />
              ) : (
                t("auth:actions.signIn")
              )}
            </Button>
          </Stack>
          <Box mt={1.5} textAlign="center" fontSize={15}>
            <Link
              to="/forgot-password"
              style={{ color: "var(--nav-link)", textDecoration: "underline" }}
            >
              {t("auth:login.forgot")}
            </Link>
          </Box>
          <Box mt={2} textAlign="center" fontSize={15}>
            {t("auth:login.noAccount")}{" "}
            <Link to="/register" style={{ color: "var(--nav-link)", textDecoration: "underline" }}>
              {t("auth:login.ctaRegister")}
            </Link>
          </Box>
        </form>
      </Paper>
    </Box>
  )
}

export default Login
