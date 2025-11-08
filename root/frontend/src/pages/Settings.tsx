import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
  ChangeEvent,
  FocusEvent,
} from "react"
import { isAxiosError } from "axios"
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext"
import { useLanguage, type SupportedLanguage } from "@/contexts/LanguageContext"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { usePushPreferences } from "@/hooks/usePushPreferences"
import { nowPlayingQueryKey } from "@/hooks/useNowPlaying"
import api from "../api/client"
import {
  startTotpEnrollment,
  confirmTotpEnrollment,
  deleteTotpEnrollment,
  startWebAuthnAttestation,
  finishWebAuthnAttestation,
  deleteWebAuthnCredential,
  regenerateRecoveryCodes,
} from "@/api/mfa"
import TotpQrDisplay from "@/components/mfa/TotpQrDisplay"
import OtpEntry from "@/components/mfa/OtpEntry"
import RecoveryCodeList from "@/components/mfa/RecoveryCodeList"
import StepUpDialog from "@/components/mfa/StepUpDialog"
import {
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type RegistrationResponseJSON,
} from "@simplewebauthn/browser"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import type {
  MfaMethod,
  MfaTotpEnrollment,
  MfaWebAuthnCredential,
  TotpEnrollmentStartResponse,
} from "@/types/Mfa"
import { useTranslation } from "react-i18next"
import dayjs from "dayjs"
import { Settings as SettingsIcon, Moon, Sun, Monitor } from "lucide-react"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL
import spotifyLogo from "@/assets/spotify_icon.png"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { sanitizeSpotifyAuthorizeUrl } from "@/utils/spotify"

type ThemeMode = "system" | "light" | "dark"

const isCreationOptions = (
  value: Record<string, unknown> | PublicKeyCredentialCreationOptionsJSON | null | undefined
): value is PublicKeyCredentialCreationOptionsJSON => {
  if (!value || typeof value !== "object") return false
  const candidate = value as {
    challenge?: unknown
    pubKeyCredParams?: unknown
  }
  return typeof candidate.challenge === "string" && Array.isArray(candidate.pubKeyCredParams)
}

const DEFAULT_DND_START = "22:00"
const DEFAULT_DND_END = "07:00"

const toInputTime = (value: unknown): string => {
  if (!value) return ""
  const str = String(value)
  const match = str.match(/^(\d{2}:\d{2})/)
  return match ? match[1] : ""
}

const toServerTime = (value: string | null): string | null => {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (/^\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00`
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) return trimmed
  return trimmed
}

// Tailwind CSS components

function SectionCard({
  children,
  className = "",
  component = "div",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  return (
    <Component
      className={`bg-card rounded-[20px] px-6 py-[22px] border border-glass-border flex flex-col gap-3 ${className}`}
      {...props}
    >
      {children}
    </Component>
  )
}

function SectionTitle({
  children,
  className = "",
  component = "h2",
  variant = "subtitle1",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
  variant?: string
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  const sizeClasses =
    variant === "subtitle1"
      ? "text-base"
      : variant === "subtitle2"
        ? "text-sm"
        : variant === "h6"
          ? "text-lg"
          : "text-base"
  return (
    <Component className={`font-semibold text-page-text ${sizeClasses} ${className}`} {...props}>
      {children}
    </Component>
  )
}

function SectionSubtitle({
  children,
  className = "",
  variant = "body2",
  ...props
}: {
  children: React.ReactNode
  className?: string
  variant?: string
} & React.HTMLAttributes<HTMLParagraphElement>) {
  const sizeClasses =
    variant === "body2" ? "text-sm" : variant === "caption" ? "text-xs" : "text-sm"
  return (
    <p className={`text-page-text/70 ${sizeClasses} ${className}`} {...props}>
      {children}
    </p>
  )
}

function SessionItem({
  children,
  className = "",
  ...props
}: {
  children: React.ReactNode
  className?: string
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`
        flex items-stretch justify-between gap-3 p-3 rounded-[18px]
        border border-glass-border bg-black/[0.03] dark:bg-white/[0.04]
        transition-all duration-200 ease-in-out
        max-sm:flex-col max-sm:items-start
        hover:border-primary/35 hover:shadow-card-hover hover:bg-primary/8 dark:hover:bg-primary/18
        data-[revoked=true]:opacity-70 data-[revoked=true]:border-dashed
        data-[revoked=true]:border-page-text/20 data-[revoked=true]:bg-page-text/[0.04] dark:data-[revoked=true]:bg-page-text/[0.06]
        data-[revoked=true]:hover:shadow-none data-[revoked=true]:hover:border-page-text/20
        data-[revoked=true]:hover:bg-page-text/[0.04] dark:data-[revoked=true]:hover:bg-page-text/[0.06]
        ${className}
      `}
      {...props}
    >
      {children}
    </div>
  )
}

// Additional Tailwind helper components

function Button({
  children,
  variant = "contained",
  color = "primary",
  size = "medium",
  disabled = false,
  startIcon,
  onClick,
  type = "button",
  className = "",
  ...props
}: {
  children: React.ReactNode
  variant?: "contained" | "outlined" | "text"
  color?: "primary" | "error" | "inherit" | "success"
  size?: "small" | "medium"
  disabled?: boolean
  startIcon?: React.ReactNode
  onClick?: () => void
  type?: "button" | "submit"
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const baseClasses =
    "inline-flex items-center justify-center gap-2 font-bold rounded-lg transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
  const sizeClasses = size === "small" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-base"

  let variantClasses = ""
  if (variant === "contained") {
    if (color === "primary") {
      variantClasses = "bg-primary text-white hover:bg-primary/90 shadow-md hover:shadow-lg"
    } else if (color === "error") {
      variantClasses = "bg-red-500 text-white hover:bg-red-600 shadow-md hover:shadow-lg"
    }
  } else if (variant === "outlined") {
    if (color === "primary") {
      variantClasses =
        "border-2 border-primary text-primary hover:bg-primary/10 dark:hover:bg-primary/20"
    } else if (color === "error") {
      variantClasses = "border-2 border-red-500 text-red-500 hover:bg-red-500/10"
    }
  } else if (variant === "text") {
    if (color === "error") {
      variantClasses = "text-red-500 hover:bg-red-500/10"
    } else if (color === "inherit") {
      variantClasses = "text-page-text hover:bg-page-text/10"
    }
  }

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`${baseClasses} ${sizeClasses} ${variantClasses} ${className}`}
      {...props}
    >
      {startIcon && <span className="flex items-center">{startIcon}</span>}
      {children}
    </button>
  )
}

function TextField({
  label,
  value,
  onChange,
  onBlur,
  type = "text",
  disabled = false,
  error = false,
  helperText,
  placeholder,
  size = "medium",
  fullWidth = false,
  autoComplete,
  className = "",
  ...props
}: {
  label?: string
  value: string
  onChange: (e: ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void
  type?: string
  disabled?: boolean
  error?: boolean
  helperText?: string
  placeholder?: string
  size?: "small" | "medium"
  fullWidth?: boolean
  autoComplete?: string
  className?: string
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "size" | "onChange" | "onBlur">) {
  const sizeClasses = size === "small" ? "px-3 py-1.5 text-sm" : "px-4 py-2"
  const widthClass = fullWidth ? "w-full" : ""
  const timeInputClasses =
    type === "time" ? "max-w-full sm:max-w-[200px] text-center tabular-nums" : ""

  return (
    <div className={`${widthClass} ${className}`}>
      {label && (
        <label className="block text-sm font-medium text-page-text mb-1 px-1 bg-card">
          {label}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        onBlur={onBlur}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className={`
          ${widthClass} ${sizeClasses} ${timeInputClasses}
          rounded-lg border bg-card text-page-text
          ${error ? "border-red-500" : "border-page-text/25"}
          hover:border-page-text/35
          focus:outline-none focus:ring-3 focus:ring-primary/25 focus:border-primary
          disabled:bg-page-text/[0.06] disabled:border-page-text/20 disabled:cursor-not-allowed
          transition-all duration-200
        `}
        {...props}
      />
      {helperText && (
        <p className={`text-xs mt-1 ${error ? "text-red-500" : "text-page-text/60"}`}>
          {helperText}
        </p>
      )}
    </div>
  )
}

function RadioGroup({
  children,
  value,
  onChange,
  row = false,
  "aria-label": ariaLabel,
}: {
  children: React.ReactNode
  value: string
  onChange: (e: ChangeEvent<HTMLInputElement>, value: string) => void
  row?: boolean
  "aria-label"?: string
}) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    onChange(e, e.target.value)
  }

  return (
    <div
      className={`${row ? "flex flex-wrap gap-4" : "flex flex-col gap-2"}`}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(
            child as React.ReactElement<{ groupValue?: string; groupOnChange?: (e: ChangeEvent<HTMLInputElement>) => void }>,
            { 
              groupValue: value,
              groupOnChange: handleChange
            }
          )
        }
        return child
      })}
    </div>
  )
}

function FormControlLabel({
  value,
  control,
  label,
  className = "",
  groupValue,
  groupOnChange,
}: {
  value: string
  control: React.ReactNode
  label: React.ReactNode
  className?: string
  groupValue?: string
  groupOnChange?: (e: ChangeEvent<HTMLInputElement>) => void
}) {
  const inputId = useMemo(() => `radio-${value}-${Math.random().toString(36).substr(2, 9)}`, [value])
  
  return (
    <label htmlFor={inputId} className={`inline-flex items-center gap-2 cursor-pointer ${className}`}>
      {React.isValidElement(control)
        ? React.cloneElement(
            control as React.ReactElement<{ 
              checked?: boolean
              value?: string
              name?: string
              id?: string
              onChange?: (e: ChangeEvent<HTMLInputElement>) => void
            }>,
            {
              checked: groupValue === value,
              value: value,
              name: "radio-group",
              id: inputId,
              onChange: groupOnChange,
            }
          )
        : control}
      <span className="text-page-text">{label}</span>
    </label>
  )
}

function Radio({
  checked,
  onChange,
  value,
  name,
  id,
}: {
  checked?: boolean
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  value?: string
  name?: string
  id?: string
}) {
  return (
    <input
      type="radio"
      checked={checked}
      onChange={onChange}
      value={value}
      name={name}
      id={id}
      className="w-4 h-4 text-primary border-page-text/30 focus:ring-2 focus:ring-primary/30 cursor-pointer"
    />
  )
}

function Alert({
  severity = "info",
  variant = "filled",
  children,
  onClose,
  className = "",
}: {
  severity?: "info" | "error" | "warning" | "success"
  variant?: "filled" | "outlined"
  children: React.ReactNode
  onClose?: () => void
  className?: string
}) {
  const severityClasses = {
    info: variant === "outlined" ? "border-blue-500 text-blue-500" : "bg-blue-500 text-white",
    error: variant === "outlined" ? "border-red-500 text-red-500" : "bg-red-500 text-white",
    warning:
      variant === "outlined" ? "border-yellow-500 text-yellow-500" : "bg-yellow-500 text-black",
    success: variant === "outlined" ? "border-green-500 text-green-500" : "bg-green-500 text-white",
  }

  return (
    <div
      className={`
        flex items-center gap-2 px-4 py-2 rounded-lg
        ${variant === "outlined" ? "border-2 bg-transparent" : ""}
        ${severityClasses[severity]}
        ${className}
      `}
    >
      <span className="flex-1">{children}</span>
      {onClose && (
        <button onClick={onClose} className="ml-2 hover:opacity-70 transition-opacity">
          ×
        </button>
      )}
    </div>
  )
}

function Chip({
  label,
  size = "medium",
  color = "default",
  variant = "filled",
  className = "",
}: {
  label: string
  size?: "small" | "medium"
  color?: "default" | "success" | "primary"
  variant?: "filled" | "outlined"
  className?: string
}) {
  const sizeClasses = size === "small" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"
  let colorClasses = ""

  if (color === "success") {
    colorClasses =
      variant === "outlined"
        ? "border border-green-500 text-green-500"
        : "bg-green-500/20 text-green-500 border border-green-500/30"
  } else if (color === "primary") {
    colorClasses =
      variant === "outlined"
        ? "border border-primary text-primary"
        : "bg-primary/20 text-primary border border-primary/30"
  } else {
    colorClasses =
      variant === "outlined"
        ? "border border-page-text/30 text-page-text/70"
        : "bg-page-text/10 text-page-text/70 border border-page-text/20"
  }

  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold ${sizeClasses} ${colorClasses} ${className}`}
    >
      {label}
    </span>
  )
}

function Divider({
  className = "",
  flexItem,
  component,
}: {
  className?: string
  flexItem?: boolean
  component?: React.ElementType
}) {
  const Component = component || "hr"
  return (
    <Component
      className={`border-t border-glass-border ${flexItem ? "self-stretch" : ""} ${className}`}
    />
  )
}

function Avatar({
  src,
  alt,
  imgProps,
  className = "",
}: {
  src: string
  alt: string
  imgProps?: React.ImgHTMLAttributes<HTMLImageElement>
  className?: string
}) {
  return (
    <div className={`rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700 ${className}`}>
      <img src={src} alt={alt} className="w-full h-full object-cover" {...imgProps} />
    </div>
  )
}

function CircularProgress({
  size = 24,
  color = "primary",
  className = "",
}: {
  size?: number
  color?: string
  className?: string
}) {
  return (
    <svg
      className={`animate-spin ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}

function Dialog({
  open,
  onClose,
  maxWidth = "md",
  fullWidth = false,
  children,
}: {
  open: boolean
  onClose: () => void
  maxWidth?: string
  fullWidth?: boolean
  children: React.ReactNode
}) {
  if (!open) return null

  const maxWidthClasses =
    {
      xs: "max-w-xs",
      sm: "max-w-sm",
      md: "max-w-md",
      lg: "max-w-lg",
      xl: "max-w-xl",
    }[maxWidth] || "max-w-md"

  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={`bg-card rounded-2xl shadow-2xl ${fullWidth ? "w-full" : ""} ${maxWidthClasses}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

function DialogTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-bold text-page-text px-6 pt-6 pb-2">{children}</h2>
}

function DialogContent({ children }: { children: React.ReactNode }) {
  return <div className="px-6 py-4 text-page-text/80">{children}</div>
}

function DialogActions({ children }: { children: React.ReactNode }) {
  return <div className="flex gap-2 justify-end px-6 pb-6 pt-2">{children}</div>
}

function Snackbar({
  open,
  onClose,
  autoHideDuration,
  anchorOrigin,
  children,
}: {
  open: boolean
  onClose: () => void
  autoHideDuration?: number
  anchorOrigin?: { vertical: string; horizontal: string }
  children: React.ReactNode
}) {
  useEffect(() => {
    if (open && autoHideDuration) {
      const timer = setTimeout(onClose, autoHideDuration)
      return () => clearTimeout(timer)
    }
  }, [open, autoHideDuration, onClose])

  if (!open) return null

  const positionClasses =
    anchorOrigin?.vertical === "bottom"
      ? "bottom-4"
      : anchorOrigin?.vertical === "top"
        ? "top-4"
        : "top-1/2 -translate-y-1/2"
  const horizontalClasses =
    anchorOrigin?.horizontal === "center"
      ? "left-1/2 -translate-x-1/2"
      : anchorOrigin?.horizontal === "right"
        ? "right-4"
        : "left-4"

  return <div className={`fixed z-50 ${positionClasses} ${horizontalClasses}`}>{children}</div>
}

function Tabs({
  value,
  onChange,
  variant,
  scrollButtons,
  children,
  className = "",
}: {
  value: number
  onChange: (e: unknown, value: number) => void
  variant?: string
  scrollButtons?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      role="tablist"
      className={`flex gap-1 border-b border-glass-border overflow-x-auto ${className}`}
    >
      {React.Children.map(children, (child, index) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(
            child as React.ReactElement<{ selected?: boolean; onClick?: () => void }>,
            {
              selected: value === index,
              onClick: () => onChange(null, index),
            }
          )
        }
        return child
      })}
    </div>
  )
}

function Tab({
  label,
  selected,
  onClick,
}: {
  label: string
  selected?: boolean
  onClick?: () => void
}) {
  return (
    <button
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={`
        px-4 py-2.5 text-sm font-bold transition-colors min-h-[42px]
        ${selected ? "text-primary border-b-2 border-primary" : "text-page-text hover:text-primary"}
      `}
    >
      {label}
    </button>
  )
}

function SwitchControl({
  checked,
  disabled,
  onChange,
  inputId,
  "aria-label": ariaLabel,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (e: ChangeEvent<HTMLInputElement>, checked: boolean) => void
  inputId?: string
  "aria-label"?: string
}) {
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)

  return (
    <span
      className={`
        relative inline-flex items-center w-[52px] h-7 p-0.5 rounded-full cursor-pointer
        touch-manipulation select-none
        ${disabled ? "opacity-60 cursor-not-allowed" : ""}
      `}
      onMouseEnter={() => !disabled && setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Focus ring */}
      <span
        className={`
          absolute -inset-0.5 rounded-full pointer-events-none transition-all duration-200
          ${focus && !disabled ? "shadow-[0_0_0_3px_rgba(var(--primary-rgb),0.35)] opacity-100 scale-100" : "opacity-0 scale-95"}
        `}
      />
      {/* Track */}
      <span
        className={`
          absolute inset-0 rounded-full border transition-all duration-200
          ${
            checked
              ? "bg-primary/20 dark:bg-primary/55 border-primary/60"
              : hover && !disabled
                ? "bg-black/10 dark:bg-white/16 border-black/12 dark:border-white/24"
                : "bg-black/8 dark:bg-white/12 border-black/12 dark:border-white/24"
          }
        `}
      />
      {/* Thumb */}
      <span
        className={`
          relative z-10 w-[22px] h-[22px] rounded-full bg-white
          shadow-[0_1px_2px_rgba(0,0,0,0.25),0_0_0_1px_rgba(0,0,0,0.06)_inset]
          dark:shadow-[0_1px_2px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.08)_inset]
          transition-transform duration-200 ease-[cubic-bezier(0.2,0.9,0.22,1)]
          ${checked ? "translate-x-6" : "translate-x-0"}
        `}
      />
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e, e.target.checked)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        className="absolute opacity-0 w-0 h-0"
      />
    </span>
  )
}

export default function Settings() {
  const navigate = useNavigate()
  const { user, setUser, logout } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState(0)
  const [snack, setSnack] = useState<{
    text: string
    sev?: "success" | "info" | "warning" | "error"
  } | null>(null)
  const { language, setLanguage, available: availableLanguages } = useLanguage()
  const { t } = useTranslation(["settings", "common", "notifications", "profile"])

  // Theme management
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem("theme-mode")
    return (stored as ThemeMode) || "system"
  })

  const setMode = useCallback((value: ThemeMode) => {
    setTheme(value)
    localStorage.setItem("theme-mode", value)

    // Apply theme to document
    const root = document.documentElement
    if (value === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      root.classList.toggle("dark", prefersDark)
    } else {
      root.classList.toggle("dark", value === "dark")
    }
  }, [])

  const {
    pushSupported,
    notificationPermission,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
    disableNotifications,
  } = usePushPreferences({ onNotify: setSnack })

  const [dndEnabled, setDndEnabled] = useState(false)
  const [dndStart, setDndStart] = useState("")
  const [dndEnd, setDndEnd] = useState("")
  const [dndSaving, setDndSaving] = useState(false)

  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const sessionsKey = useMemo(() => ["auth", "sessions", user?.id ?? "me"], [user?.id])

  const fetchSessions = useCallback(async () => {
    const { data } = await api.get<ActiveSession[]>("/auth/sessions")
    return data
  }, [])

  const {
    data: sessionsData,
    isFetching: sessionsFetching,
    isError: sessionsIsError,
    error: sessionsError,
  } = useQuery<ActiveSession[], unknown>({
    queryKey: sessionsKey,
    queryFn: fetchSessions,
    enabled: tab === 1 && Boolean(user),
    staleTime: 30_000,
  })

  const sessions = Array.isArray(sessionsData) ? sessionsData : []

  const sortedSessions = useMemo(() => {
    const weight = (session: ActiveSession) => {
      if (session.is_current) return 0
      if (session.revoked_at) return 2
      return 1
    }

    const timeValue = (session: ActiveSession) => {
      const source = session.last_seen_at ?? session.created_at ?? null
      if (!source) return 0
      const parsed = dayjs(source)
      return parsed.isValid() ? parsed.valueOf() : 0
    }

    if (!Array.isArray(sessions)) return []

    return [...sessions].sort((a, b) => {
      const weightDiff = weight(a) - weight(b)
      if (weightDiff !== 0) return weightDiff
      return timeValue(b) - timeValue(a)
    })
  }, [sessions])

  const revokeSessionMutation = useMutation({
    mutationFn: async (sessionId: number) => {
      const { data } = await api.delete<ActiveSession>(`/auth/sessions/${sessionId}`)
      return data
    },
  })

  const revokeAllSessionsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ revoked: number }>("/auth/sessions/revoke-others")
      return data
    },
  })

  const syncDndFromUser = useCallback((value: User | null) => {
    const enabled = Boolean(value?.dnd_enabled)
    const start = toInputTime(value?.dnd_start)
    const end = toInputTime(value?.dnd_end)
    setDndEnabled(enabled)
    setDndStart(start || (enabled ? DEFAULT_DND_START : ""))
    setDndEnd(end || (enabled ? DEFAULT_DND_END : ""))
  }, [])

  const persistDnd = useCallback(
    async (nextEnabled: boolean, nextStart: string | null, nextEnd: string | null) => {
      if (dndSaving) return
      const normalizedStart = nextStart ? nextStart.trim() : null
      const normalizedEnd = nextEnd ? nextEnd.trim() : null
      const prevEnabled = Boolean(user?.dnd_enabled)
      const prevStart = toInputTime(user?.dnd_start)
      const prevEnd = toInputTime(user?.dnd_end)
      if (
        nextEnabled === prevEnabled &&
        (!nextEnabled ||
          (normalizedStart &&
            normalizedEnd &&
            normalizedStart === prevStart &&
            normalizedEnd === prevEnd))
      ) {
        return
      }
      if (nextEnabled && (!normalizedStart || !normalizedEnd)) {
        setSnack({ text: t("settings:dnd.validation.missingRange"), sev: "warning" })
        syncDndFromUser(user)
        return
      }
      setDndSaving(true)
      try {
        const payload: Record<string, unknown> = { dnd_enabled: nextEnabled }
        if (nextEnabled) {
          payload.dnd_start = toServerTime(normalizedStart)
          payload.dnd_end = toServerTime(normalizedEnd)
        } else {
          payload.dnd_start = null
          payload.dnd_end = null
        }
        const res = await api.put<User>("/users/me", payload)
        setUser(res.data)
        syncDndFromUser(res.data)
        const wasEnabled = prevEnabled
        let message: string
        if (nextEnabled && !wasEnabled) message = t("settings:dnd.snackbar.enabled")
        else if (!nextEnabled && wasEnabled) message = t("settings:dnd.snackbar.disabled")
        else message = t("settings:dnd.snackbar.updated")
        setSnack({ text: message, sev: "success" })
      } catch (error: unknown) {
        let message = t("settings:dnd.snackbar.updateFailed")
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") message = detail
          else if (Array.isArray(detail)) {
            const collected = detail
              .map((item: unknown) =>
                item && typeof item === "object" && "msg" in item
                  ? String((item as { msg?: unknown }).msg)
                  : ""
              )
              .filter(Boolean)
              .join("; ")
            if (collected) message = collected
          }
        }
        setSnack({ text: message, sev: "error" })
        syncDndFromUser(user)
      } finally {
        setDndSaving(false)
      }
    },
    [dndSaving, setUser, setSnack, syncDndFromUser, t, user]
  )

  const handleDndToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (dndSaving) return
      const nextStart = checked ? dndStart || DEFAULT_DND_START : dndStart
      const nextEnd = checked ? dndEnd || DEFAULT_DND_END : dndEnd
      if (checked) {
        setDndStart(nextStart)
        setDndEnd(nextEnd)
      }
      setDndEnabled(checked)
      void persistDnd(checked, checked ? nextStart : null, checked ? nextEnd : null)
    },
    [dndSaving, dndEnd, dndStart, persistDnd]
  )

  const handleDndStartChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndStart(event.target.value)
  }, [])

  const handleDndStartBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndStart(value)
      void persistDnd(true, value || null, dndEnd || null)
    },
    [dndEnabled, dndEnd, dndSaving, persistDnd]
  )

  const handleDndEndChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndEnd(event.target.value)
  }, [])

  const handleDndEndBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndEnd(value)
      void persistDnd(true, dndStart || null, value || null)
    },
    [dndEnabled, dndSaving, dndStart, persistDnd]
  )

  useEffect(() => {
    syncDndFromUser(user)
  }, [syncDndFromUser, user])

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search)
    const s = sp.get("spotify")
    if (s) {
      if (s === "connected")
        setSnack({ text: t("settings:integrations.spotify.snackbar.connected"), sev: "success" })
      if (s === "error")
        setSnack({ text: t("settings:integrations.spotify.snackbar.connectFailed"), sev: "error" })
      sp.delete("spotify")
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "")
      window.history.replaceState({}, "", next)
    }
  }, [setSnack, t])

  const handleThemeChange = useCallback(
    (_: ChangeEvent<HTMLInputElement>, value: string) => {
      setMode(value as ThemeMode)
    },
    [setMode]
  )

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return
      if (checked) void enableNotifications()
      else void disableNotifications()
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  )

  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const spotifyName = user?.spotify_display_name ?? ""

  const connectSpotify = async () => {
    try {
      const { data } = await api.get<{ url?: string }>("/spotify/auth-url")
      const safeUrl = sanitizeSpotifyAuthorizeUrl(data?.url)
      if (!safeUrl) throw new Error("Received unsafe Spotify authorization URL")
      window.location.assign(safeUrl)
    } catch (error) {
      setSnack({ text: t("settings:integrations.spotify.snackbar.openFailed"), sev: "error" })
    }
  }

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect")
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: currentUserQueryKey }),
        queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey }),
      ])
      try {
        const profile = await fetchCurrentUser()
        setUser(profile)
      } catch {
        setUser((prev) =>
          prev
            ? {
                ...prev,
                spotify_connected: false,
                spotify_is_connected: false,
                spotify_display_name: null,
              }
            : prev
        )
      }
      setSnack({ text: t("settings:integrations.spotify.snackbar.disconnected"), sev: "success" })
    } catch {
      setSnack({ text: t("settings:integrations.spotify.snackbar.disconnectFailed"), sev: "error" })
    }
  }

  const isImage = (f: File) => /^image\/(png|jpe?g|webp|gif|avif)$/i.test(f.type)
  const withinSize = (f: File, maxMB = 12) => f.size / (1024 * 1024) <= maxMB

  const avatarInputRef = useRef<HTMLInputElement | null>(null)
  const coverInputRef = useRef<HTMLInputElement | null>(null)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [coverBusy, setCoverBusy] = useState(false)

  const avatarUrl = user?.avatar_url ?? undefined
  const coverUrl = user?.cover_url ?? undefined

  const avatarSrc = useMemo(() => {
    const resolved = resolveMediaUrl(avatarUrl)
    return resolved ? addVersionParam(resolved, avatarVersion) : DEFAULT_AVATAR
  }, [avatarUrl, avatarVersion])

  const coverSrc = useMemo(() => {
    const resolved = resolveMediaUrl(coverUrl)
    return resolved ? addVersionParam(resolved, coverVersion) : ""
  }, [coverUrl, coverVersion])

  const handleAvatarError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget
    img.onerror = null
    img.src = DEFAULT_AVATAR
  }, [])

  const triggerAvatarPick = () => avatarInputRef.current?.click()
  const triggerCoverPick = () => coverInputRef.current?.click()

  const refreshMe = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const [totpDraft, setTotpDraft] = useState<TotpEnrollmentStartResponse | null>(null)
  const [totpBusy, setTotpBusy] = useState(false)
  const [totpError, setTotpError] = useState<string | null>(null)
  const [webAuthnBusy, setWebAuthnBusy] = useState(false)
  const [webAuthnName, setWebAuthnName] = useState("")
  const [generatedRecoveryCodes, setGeneratedRecoveryCodes] = useState<string[]>([])
  const [recoveryBusy, setRecoveryBusy] = useState(false)
  const [pendingEmail, setPendingEmail] = useState<string | null>(user?.pending_email ?? null)
  const [emailValue, setEmailValue] = useState(user?.email ?? "")
  const [emailPassword, setEmailPassword] = useState("")
  const [emailBusy, setEmailBusy] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [emailPasswordError, setEmailPasswordError] = useState<string | null>(null)
  const [currentPasswordValue, setCurrentPasswordValue] = useState("")
  const [newPasswordValue, setNewPasswordValue] = useState("")
  const [confirmPasswordValue, setConfirmPasswordValue] = useState("")
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [currentPasswordError, setCurrentPasswordError] = useState<string | null>(null)
  const [stepUpOpen, setStepUpOpen] = useState(false)
  const stepUpActionRef = useRef<(() => Promise<void>) | null>(null)

  useEffect(() => {
    setEmailValue(user?.email ?? "")
  }, [user?.email])

  useEffect(() => {
    setPendingEmail(user?.pending_email ?? null)
  }, [user?.pending_email])

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    if (isAxiosError(error)) {
      const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
      if (typeof detail === "string") return detail
      if (Array.isArray(detail)) {
        const combined = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg?: unknown }).msg)
              : ""
          )
          .filter(Boolean)
          .join("; ")
        if (combined) return combined
      }
    }
    return fallback
  }, [])

  const isStepUpError = useCallback(
    (error: unknown) => isAxiosError(error) && error.response?.status === 428,
    []
  )

  const methodLabels = useMemo<Record<MfaMethod, string>>(
    () => ({
      totp: t("settings:security.method.totp"),
      webauthn: t("settings:security.method.webauthn"),
      recovery: t("settings:security.method.recovery"),
    }),
    [t]
  )

  const formatDateTime = useCallback((value: string | null) => {
    if (!value) return null
    const parsed = dayjs(value)
    if (!parsed.isValid()) return null
    return parsed.format("DD MMM YYYY HH:mm")
  }, [])

  const activeTotp = useMemo(
    () => (user?.totp_enrollments ?? []).filter((entry) => entry.is_active),
    [user?.totp_enrollments]
  )

  const activeWebAuthn = useMemo(
    () => (user?.webauthn_credentials ?? []).filter((entry) => entry.is_active),
    [user?.webauthn_credentials]
  )

  const defaultMethodText = useMemo(() => {
    const key = user?.mfa_default_method
    if (!key) return t("settings:security.status.noDefault")
    if (!(key in methodLabels)) {
      return t("settings:security.status.noDefault")
    }
    return t("settings:security.status.defaultMethod", {
      method: methodLabels[key as MfaMethod],
    })
  }, [methodLabels, t, user?.mfa_default_method])

  const lastVerifiedText = useMemo(() => {
    if (!user?.mfa_last_verified_at) {
      return t("settings:security.status.notVerified")
    }
    const formatted = formatDateTime(user.mfa_last_verified_at)
    return formatted
      ? t("settings:security.status.lastVerified", { value: formatted })
      : t("settings:security.status.notVerified")
  }, [formatDateTime, t, user?.mfa_last_verified_at])

  const recoveryStatusText = useMemo(() => {
    const generatedAt = user?.mfa_recovery_codes_generated_at
    if (!generatedAt) {
      return t("settings:security.recovery.neverGenerated")
    }
    const formatted = formatDateTime(generatedAt)
    return formatted
      ? t("settings:security.recovery.generatedAt", { value: formatted })
      : t("settings:security.recovery.neverGenerated")
  }, [formatDateTime, t, user?.mfa_recovery_codes_generated_at])

  const isNewPasswordError = useMemo(() => {
    if (!passwordError) return false
    return [
      t("settings:security.password.errors.newRequired"),
      t("settings:security.password.errors.same"),
    ].includes(passwordError)
  }, [passwordError, t])

  const confirmPasswordMessage = useMemo(() => {
    if (!passwordError) return null
    if (
      [
        t("settings:security.password.errors.newRequired"),
        t("settings:security.password.errors.same"),
      ].includes(passwordError)
    ) {
      return null
    }
    return passwordError
  }, [passwordError, t])

  const openStepUpFor = useCallback((action: () => Promise<void>) => {
    stepUpActionRef.current = action
    setStepUpOpen(true)
  }, [])

  const handleStepUpClose = useCallback(() => {
    setStepUpOpen(false)
    stepUpActionRef.current = null
  }, [])

  const handleStepUpCompleted = useCallback(async () => {
    const action = stepUpActionRef.current
    stepUpActionRef.current = null
    setStepUpOpen(false)
    if (action) {
      await action()
    }
  }, [])

  const handleRevokeSession = useCallback(
    async (sessionId: number, options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeSessionMutation.mutateAsync(sessionId)
        setSnack({ text: t("settings:sessions.snackbar.revoked"), sev: "success" })
        queryClient.setQueryData<ActiveSession[] | undefined>(sessionsKey, (prev) => {
          if (!Array.isArray(prev)) return [result]
          return prev.map((session) => (session.id === result.id ? result : session))
        })
        if (result?.is_current) {
          await logout()
        }
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleRevokeSession(sessionId, { skipStepUp: true })
          })
          return
        }
        setSnack({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.failed")),
          sev: "error",
        })
      }
    },
    [
      isStepUpError,
      logout,
      openStepUpFor,
      queryClient,
      resolveDetailMessage,
      revokeSessionMutation,
      sessionsKey,
      t,
    ]
  )

  const handleRevokeAllSessions = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      try {
        const result = await revokeAllSessionsMutation.mutateAsync()
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
        setSnack({
          text: t("settings:sessions.snackbar.revokedAll", {
            count: result?.revoked ?? 0,
          }),
          sev: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleRevokeAllSessions({ skipStepUp: true })
          })
          return
        }
        setSnack({
          text: resolveDetailMessage(error, t("settings:sessions.snackbar.revokeAllFailed")),
          sev: "error",
        })
      }
    },
    [
      isStepUpError,
      openStepUpFor,
      queryClient,
      resolveDetailMessage,
      revokeAllSessionsMutation,
      sessionsKey,
      t,
    ]
  )

  const handleEmailSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (emailBusy) return
      let hasError = false
      const trimmedEmail = emailValue.trim()
      setEmailError(null)
      setEmailPasswordError(null)
      if (!trimmedEmail) {
        setEmailError(t("settings:security.email.errors.required"))
        hasError = true
      } else if (user?.email && trimmedEmail.toLowerCase() === user.email.toLowerCase()) {
        setEmailError(t("settings:security.email.noChange"))
        hasError = true
      } else if (pendingEmail && trimmedEmail.toLowerCase() === pendingEmail.toLowerCase()) {
        setEmailError(t("settings:security.email.pendingSame", { email: pendingEmail }))
        hasError = true
      }
      if (!emailPassword) {
        setEmailPasswordError(t("settings:security.email.errors.passwordRequired"))
        hasError = true
      }
      if (hasError) return

      setEmailBusy(true)
      try {
        await api.post<User>("/users/me/email", {
          email: trimmedEmail,
          password: emailPassword,
        })
        setPendingEmail(trimmedEmail.toLowerCase())
        await refreshMe()
        setEmailPassword("")
        setSnack({
          text: t("settings:security.email.confirmationSent", { email: trimmedEmail }),
          sev: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleEmailSubmit({ skipStepUp: true })
          })
          return
        }
        let handled = false
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.email.errors.invalidPassword")) {
              setEmailPasswordError(detail)
              handled = true
            } else {
              setEmailError(detail)
              handled = true
            }
          }
        }
        if (!handled) {
          const message = resolveDetailMessage(error, t("settings:security.email.failed"))
          setEmailError(message)
          setSnack({ text: message, sev: "error" })
        }
      } finally {
        setEmailBusy(false)
      }
    },
    [
      emailBusy,
      emailPassword,
      emailValue,
      isStepUpError,
      openStepUpFor,
      refreshMe,
      resolveDetailMessage,
      pendingEmail,
      setSnack,
      t,
      user?.email,
    ]
  )

  const handlePasswordSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (passwordBusy) return
      setCurrentPasswordError(null)
      setPasswordError(null)
      let hasError = false
      if (!currentPasswordValue) {
        setCurrentPasswordError(t("settings:security.password.errors.currentRequired"))
        hasError = true
      }
      let derivedError: string | null = null
      if (!newPasswordValue) {
        derivedError = t("settings:security.password.errors.newRequired")
      } else if (!confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.confirmRequired")
      } else if (newPasswordValue !== confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.mismatch")
      }
      if (derivedError) {
        setPasswordError(derivedError)
        hasError = true
      }
      if (hasError) return

      setPasswordBusy(true)
      try {
        const { data } = await api.post<{
          ok: boolean
          revoked_sessions: number
        }>("/users/me/password", {
          current_password: currentPasswordValue,
          new_password: newPasswordValue,
        })
        if (data?.ok) {
          setSnack({
            text: t("settings:security.password.updated", {
              count: data.revoked_sessions ?? 0,
            }),
            sev: "success",
          })
        }
        setCurrentPasswordValue("")
        setNewPasswordValue("")
        setConfirmPasswordValue("")
        await queryClient.invalidateQueries({ queryKey: sessionsKey })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handlePasswordSubmit({ skipStepUp: true })
          })
          return
        }
        const message = resolveDetailMessage(error, t("settings:security.password.failed"))
        let handled = false
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.password.errors.currentInvalid")) {
              setCurrentPasswordError(detail)
              handled = true
            } else if (detail === t("settings:security.password.errors.same")) {
              setPasswordError(detail)
              handled = true
            } else {
              setPasswordError(detail)
              handled = true
            }
          }
        }
        if (!handled) {
          setPasswordError(message)
          setSnack({ text: message, sev: "error" })
        }
      } finally {
        setPasswordBusy(false)
      }
    },
    [
      confirmPasswordValue,
      currentPasswordValue,
      isStepUpError,
      newPasswordValue,
      openStepUpFor,
      passwordBusy,
      queryClient,
      resolveDetailMessage,
      sessionsKey,
      setSnack,
      t,
    ]
  )

  const handleStartTotp = useCallback(async () => {
    if (totpBusy) return
    setTotpBusy(true)
    setTotpError(null)
    try {
      const { data } = await startTotpEnrollment()
      setTotpDraft(data)
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:security.snackbar.totpStartFailed")),
        sev: "error",
      })
    } finally {
      setTotpBusy(false)
    }
  }, [resolveDetailMessage, setSnack, t, totpBusy])

  const handleConfirmTotp = useCallback(
    async (_method: Extract<MfaMethod, "totp" | "recovery">, code: string) => {
      if (!totpDraft) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        await confirmTotpEnrollment({ enrollment_id: totpDraft.enrollment.id, code })
        setTotpDraft(null)
        setGeneratedRecoveryCodes([])
        await refreshMe()
        setSnack({ text: t("settings:security.snackbar.totpEnabled"), sev: "success" })
      } catch (error) {
        setTotpError(resolveDetailMessage(error, t("settings:security.snackbar.totpConfirmFailed")))
      } finally {
        setTotpBusy(false)
      }
    },
    [refreshMe, resolveDetailMessage, t, totpDraft, setSnack]
  )

  const handleCancelTotp = useCallback(() => {
    setTotpDraft(null)
    setTotpError(null)
  }, [])

  const handleDisableTotp = useCallback(
    (enrollmentId: number) => {
      const action = async () => {
        try {
          await deleteTotpEnrollment(enrollmentId)
          await refreshMe()
          setSnack({ text: t("settings:security.snackbar.totpDisabled"), sev: "success" })
        } catch (error) {
          setSnack({
            text: resolveDetailMessage(error, t("settings:security.snackbar.totpDisableFailed")),
            sev: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t]
  )

  const handleRegisterWebAuthn = useCallback(async () => {
    if (webAuthnBusy) return
    setWebAuthnBusy(true)
    try {
      const { data } = await startWebAuthnAttestation()
      const rawOptions = data.options ?? null
      if (!isCreationOptions(rawOptions)) {
        throw new Error("Invalid WebAuthn attestation options")
      }
      const credential: RegistrationResponseJSON = await startRegistration({
        optionsJSON: rawOptions,
      })
      await finishWebAuthnAttestation({
        challenge_token: data.challenge_token,
        credential: credential as unknown as Record<string, unknown>,
        device_name: webAuthnName.trim() || undefined,
      })
      setWebAuthnName("")
      await refreshMe()
      setSnack({ text: t("settings:security.snackbar.webauthnAdded"), sev: "success" })
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotAllowedError") {
        setSnack({ text: t("settings:security.snackbar.webauthnCancelled"), sev: "info" })
      } else {
        setSnack({
          text: resolveDetailMessage(error, t("settings:security.snackbar.webauthnAddFailed")),
          sev: "error",
        })
      }
    } finally {
      setWebAuthnBusy(false)
    }
  }, [refreshMe, resolveDetailMessage, setSnack, t, webAuthnBusy, webAuthnName])

  const handleRemoveWebAuthn = useCallback(
    (credentialId: string) => {
      const action = async () => {
        try {
          await deleteWebAuthnCredential(credentialId)
          await refreshMe()
          setSnack({ text: t("settings:security.snackbar.webauthnRemoved"), sev: "success" })
        } catch (error) {
          setSnack({
            text: resolveDetailMessage(error, t("settings:security.snackbar.webauthnRemoveFailed")),
            sev: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t]
  )

  const handleGenerateRecoveryCodes = useCallback(() => {
    const action = async () => {
      setRecoveryBusy(true)
      try {
        const { data } = await regenerateRecoveryCodes()
        const codes = Array.isArray(data?.codes) ? data.codes.map((code) => String(code)) : []
        setGeneratedRecoveryCodes(codes)
        await refreshMe()
        setSnack({ text: t("settings:security.snackbar.recoveryGenerated"), sev: "success" })
      } catch (error) {
        setSnack({
          text: resolveDetailMessage(error, t("settings:security.snackbar.recoveryFailed")),
          sev: "error",
        })
      } finally {
        setRecoveryBusy(false)
      }
    }
    openStepUpFor(action)
  }, [openStepUpFor, refreshMe, resolveDetailMessage, setSnack, t])

  const formatSessionTimestamp = useCallback(
    (value: string | null) => {
      if (!value) return t("settings:sessions.lastSeen.never")
      const parsed = dayjs(value)
      if (!parsed.isValid()) return t("settings:sessions.lastSeen.never")
      return parsed.format("DD MMM YYYY HH:mm")
    },
    [t]
  )

  const sessionsErrorMessage = useMemo(
    () =>
      sessionsIsError
        ? resolveDetailMessage(sessionsError, t("settings:sessions.loadFailed"))
        : null,
    [resolveDetailMessage, sessionsError, sessionsIsError, t]
  )

  const uploadAvatar = async (file: File) => {
    if (!isImage(file))
      return setSnack({ text: t("settings:media.validation.supportedFormats"), sev: "warning" })
    if (!withinSize(file))
      return setSnack({ text: t("settings:media.validation.fileTooLarge"), sev: "warning" })
    try {
      setAvatarBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setAvatarVersion(Date.now())
      setSnack({ text: t("settings:media.avatar.updated"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.avatar.uploadFailed")),
        sev: "error",
      })
    } finally {
      setAvatarBusy(false)
      if (avatarInputRef.current) avatarInputRef.current.value = ""
    }
  }

  const removeAvatar = async () => {
    try {
      setAvatarBusy(true)
      await api.delete("/users/me/avatar")
      await refreshMe()
      setAvatarVersion(Date.now())
      setSnack({ text: t("settings:media.avatar.deleted"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.avatar.deleteFailed")),
        sev: "error",
      })
    } finally {
      setAvatarBusy(false)
    }
  }

  const uploadCover = async (file: File) => {
    if (!isImage(file))
      return setSnack({ text: t("settings:media.validation.supportedFormats"), sev: "warning" })
    if (!withinSize(file))
      return setSnack({ text: t("settings:media.validation.fileTooLarge"), sev: "warning" })
    try {
      setCoverBusy(true)
      const fd = new FormData()
      fd.append("file", file)
      await api.post("/users/me/cover", fd, { headers: { "Content-Type": "multipart/form-data" } })
      await refreshMe()
      setCoverVersion(Date.now())
      setSnack({ text: t("settings:media.cover.updated"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.cover.uploadFailed")),
        sev: "error",
      })
    } finally {
      setCoverBusy(false)
      if (coverInputRef.current) coverInputRef.current.value = ""
    }
  }

  const removeCover = async () => {
    try {
      setCoverBusy(true)
      await api.delete("/users/me/cover")
      await refreshMe()
      setCoverVersion(Date.now())
      setSnack({ text: t("settings:media.cover.deleted"), sev: "success" })
    } catch (error) {
      setSnack({
        text: resolveDetailMessage(error, t("settings:media.cover.deleteFailed")),
        sev: "error",
      })
    } finally {
      setCoverBusy(false)
    }
  }

  const [confirmLogout, setConfirmLogout] = useState(false)

  return (
    <div className="max-w-full w-full min-h-screen mx-0 mt-0 px-0">
      <div className="glass glass--panel p-4 md:p-8 lg:p-12 rounded-none w-full min-h-screen text-page-text bg-card">
        <div className="flex flex-row items-center gap-3 mb-3 md:mb-4">
          <SettingsIcon className="w-6 h-6" />
          <h1 className="text-3xl font-extrabold text-page-text">{t("settings:page.title")}</h1>
        </div>

        <div className="glass--segmented border border-glass-border rounded-lg mb-6 bg-card">
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label={t("settings:tabs.general")} />
            <Tab label={t("settings:tabs.account")} />
            <Tab label={t("settings:tabs.integrations")} />
          </Tabs>
        </div>

        {tab === 0 && (
          <div className="flex flex-col gap-6">
            <div>
              <h2 className="text-lg font-semibold text-page-text mb-2.5">
                {t("settings:appearance.theme.title")}
              </h2>
              <RadioGroup row value={theme} onChange={handleThemeChange}>
                <FormControlLabel
                  value="system"
                  control={<Radio />}
                  label={
                    <span className="flex flex-row items-center gap-2 text-page-text">
                      <Monitor className="w-5 h-5" />
                      <span>{t("settings:appearance.theme.options.system")}</span>
                    </span>
                  }
                />
                <FormControlLabel
                  value="light"
                  control={<Radio />}
                  label={
                    <span className="flex flex-row items-center gap-2 text-page-text">
                      <Sun className="w-5 h-5" />
                      <span>{t("settings:appearance.theme.options.light")}</span>
                    </span>
                  }
                />
                <FormControlLabel
                  value="dark"
                  control={<Radio />}
                  label={
                    <span className="flex flex-row items-center gap-2 text-page-text">
                      <Moon className="w-5 h-5" />
                      <span>{t("settings:appearance.theme.options.dark")}</span>
                    </span>
                  }
                />
              </RadioGroup>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-page-text mb-2.5">
                {t("settings:language.title")}
              </h2>
              <RadioGroup
                row
                value={language}
                onChange={(_, value) => setLanguage(value as SupportedLanguage)}
                aria-label={t("settings:language.aria")}
              >
                {availableLanguages.map((code) => (
                  <FormControlLabel
                    key={code}
                    value={code}
                    control={<Radio />}
                    label={t(`settings:language.options.${code}`)}
                  />
                ))}
              </RadioGroup>
              <p className="text-sm text-page-text mt-1">{t("settings:language.description")}</p>
            </div>

            <Divider />

            <div>
              <h2 className="text-lg font-semibold text-page-text mb-2.5">
                {t("settings:notifications.title")}
              </h2>
              {!pushSupported ? (
                <Alert severity="warning" variant="outlined">
                  {t("settings:notifications.unsupported")}
                </Alert>
              ) : (
                <div className="flex flex-col gap-4">
                  {notificationPermission === "denied" ? (
                    <div className="flex flex-col gap-3">
                      <Alert severity="error" variant="outlined">
                        {t("settings:notifications.blocked.description")}
                      </Alert>
                      <p className="text-sm text-page-text">
                        {t("settings:notifications.blocked.hint")}
                      </p>
                      <div className="flex flex-col sm:flex-row gap-2.5 sm:items-center">
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy}
                          startIcon={
                            pushBusy ? <CircularProgress size={18} color="inherit" /> : undefined
                          }
                        >
                          {t("settings:notifications.cta.checkPermission")}
                        </Button>
                        <p className="text-sm text-page-text">
                          {t("settings:notifications.status", { status: permissionText })}
                        </p>
                      </div>
                    </div>
                  ) : notificationPermission === "default" ? (
                    <div className="flex flex-col gap-3">
                      <p className="text-sm text-page-text">
                        {t("settings:notifications.cta.prompt")}
                      </p>
                      <div className="flex flex-col sm:flex-row gap-2.5 sm:items-center">
                        <Button
                          variant="contained"
                          onClick={() => void enableNotifications()}
                          disabled={pushBusy || pushInitializing}
                          startIcon={
                            pushBusy || pushInitializing ? (
                              <CircularProgress size={18} color="inherit" />
                            ) : undefined
                          }
                        >
                          {t("settings:notifications.cta.allow")}
                        </Button>
                        <p className="text-sm text-page-text">
                          {t("settings:notifications.status", { status: permissionText })}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <>
                      <label className="min-h-[44px] flex items-center gap-2.5 m-0 cursor-pointer">
                        <SwitchControl
                          checked={notificationsEnabled}
                          onChange={handleNotificationsToggle}
                          disabled={pushBusy || pushInitializing}
                          aria-label={t("settings:notifications.toggles.notifications.aria")}
                        />
                        <span className="text-page-text font-bold">
                          {t("settings:notifications.toggles.notifications.label")}
                        </span>
                      </label>

                      <label className="min-h-[44px] flex items-center gap-2.5 m-0 cursor-pointer">
                        <SwitchControl
                          checked={dndEnabled}
                          onChange={handleDndToggle}
                          disabled={dndSaving}
                          aria-label={t("settings:notifications.toggles.dnd.aria")}
                        />
                        <span className="text-page-text font-bold">
                          {t("settings:notifications.toggles.dnd.label")}
                        </span>
                      </label>

                      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
                        <TextField
                          type="time"
                          label={t("settings:dnd.start")}
                          value={dndStart}
                          onChange={handleDndStartChange}
                          onBlur={handleDndStartBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                        />
                        <TextField
                          type="time"
                          label={t("settings:dnd.end")}
                          value={dndEnd}
                          onChange={handleDndEndChange}
                          onBlur={handleDndEndBlur}
                          disabled={!dndEnabled || dndSaving}
                          size="small"
                        />
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 1 && (
          <div className="flex flex-col gap-5 w-full max-w-full sm:max-w-[640px] md:max-w-[760px] lg:max-w-[880px]">
            <SectionCard component="section">
              <ul className="flex flex-col gap-5 w-full list-none p-0 m-0">
                <li className="flex flex-col sm:flex-row gap-3 sm:gap-5 items-start sm:items-center justify-between list-none">
                  <div className="flex flex-row gap-3 sm:gap-5 items-center min-w-0 flex-1">
                    <Avatar
                      src={avatarSrc}
                      alt={user?.full_name || "avatar"}
                      className="w-[72px] h-[72px]"
                      imgProps={{
                        onError: handleAvatarError,
                        loading: "lazy",
                        decoding: "async",
                        referrerPolicy: "no-referrer",
                      }}
                    />
                    <div className="flex flex-col gap-1 min-w-0">
                      <SectionTitle variant="subtitle1">
                        {t("settings:media.avatar.title")}
                      </SectionTitle>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center justify-start sm:justify-end flex-wrap w-full sm:w-auto">
                    <Button
                      size="small"
                      variant="contained"
                      onClick={triggerAvatarPick}
                      disabled={avatarBusy}
                      className="sm:min-w-[140px] w-full sm:w-auto"
                    >
                      {t("settings:media.avatar.change")}
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      onClick={removeAvatar}
                      disabled={avatarBusy}
                      className="sm:min-w-[140px] w-full sm:w-auto"
                    >
                      {t("settings:media.avatar.delete")}
                    </Button>
                  </div>
                </li>

                <Divider component="li" flexItem className="border-glass-border list-none" />

                <li className="flex flex-col sm:flex-row gap-3 sm:gap-5 items-start sm:items-center justify-between list-none">
                  <div className="flex flex-row gap-3 sm:gap-5 items-center min-w-0 flex-1">
                    <div
                      data-testid="settings-cover-preview"
                      className="w-40 h-[72px] rounded-xl border border-glass-border"
                      style={{
                        background: coverSrc
                          ? `url(${coverSrc}) center/cover no-repeat`
                          : "color-mix(in srgb, var(--page-text) 6%, transparent)",
                      }}
                    />
                    <SectionTitle variant="subtitle1">
                      {t("settings:media.cover.title")}
                    </SectionTitle>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center justify-start sm:justify-end flex-wrap w-full sm:w-auto">
                    <Button
                      size="small"
                      variant="contained"
                      onClick={triggerCoverPick}
                      disabled={coverBusy}
                      className="sm:min-w-[140px] w-full sm:w-auto"
                    >
                      {t("settings:media.cover.change")}
                    </Button>
                    {coverUrl && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        onClick={removeCover}
                        disabled={coverBusy}
                        className="sm:min-w-[140px] w-full sm:w-auto"
                      >
                        {t("settings:media.cover.remove")}
                      </Button>
                    )}
                  </div>
                </li>
              </ul>
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const f = e.currentTarget.files?.[0]
                  if (f) uploadAvatar(f)
                }}
              />
              <input
                ref={coverInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const f = e.currentTarget.files?.[0]
                  if (f) uploadCover(f)
                }}
              />
            </SectionCard>

            <SectionCard component="section">
              <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                <SectionTitle variant="subtitle1" className="min-w-0">
                  {t("settings:account.profile.title")}
                </SectionTitle>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
                >
                  {t("common:buttons.edit")}
                </Button>
              </div>
            </SectionCard>

            <SectionCard component="section">
              <div className="flex flex-col gap-2">
                <SectionTitle variant="subtitle1">
                  {t("settings:account.logout.title")}
                </SectionTitle>
                <SectionSubtitle variant="body2">
                  {t("settings:account.logout.subtitle")}
                </SectionSubtitle>
              </div>
              <Button
                size="small"
                variant="outlined"
                color="error"
                onClick={() => setConfirmLogout(true)}
                className="self-start sm:self-end"
              >
                {t("settings:account.logout.button")}
              </Button>
            </SectionCard>
            <SectionCard component="section">
              <div className="flex flex-col gap-2">
                <SectionTitle variant="subtitle1">
                  {t("settings:security.account.title")}
                </SectionTitle>
                <SectionSubtitle variant="body2">
                  {t("settings:security.account.subtitle")}
                </SectionSubtitle>
              </div>

              <form
                className="flex flex-col gap-3 mt-4"
                onSubmit={(event) => {
                  event.preventDefault()
                  void handleEmailSubmit()
                }}
              >
                <div className="flex flex-col gap-2">
                  <SectionTitle component="h3" variant="subtitle2">
                    {t("settings:security.email.title")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.email.subtitle")}
                  </SectionSubtitle>
                </div>
                {pendingEmail ? (
                  <Alert severity="info" variant="outlined">
                    {t("settings:security.email.pendingNotice", { email: pendingEmail })}
                  </Alert>
                ) : null}
                <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-end">
                  <TextField
                    fullWidth
                    type="email"
                    size="small"
                    label={t("settings:security.email.label")}
                    value={emailValue}
                    onChange={(event) => {
                      setEmailValue(event.target.value)
                      setEmailError(null)
                    }}
                    error={Boolean(emailError)}
                    helperText={emailError ?? undefined}
                    autoComplete="email"
                  />
                  <TextField
                    fullWidth
                    type="password"
                    size="small"
                    label={t("settings:security.email.passwordLabel")}
                    value={emailPassword}
                    onChange={(event) => {
                      setEmailPassword(event.target.value)
                      setEmailPasswordError(null)
                    }}
                    error={Boolean(emailPasswordError)}
                    helperText={emailPasswordError ?? undefined}
                    autoComplete="current-password"
                  />
                </div>
                <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center">
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={emailBusy}
                    startIcon={
                      emailBusy ? <CircularProgress size={18} color="inherit" /> : undefined
                    }
                  >
                    {t("settings:security.email.updateButton")}
                  </Button>
                  <p className="text-sm text-page-text/70">{t("settings:security.email.helper")}</p>
                </div>
              </form>

              <Divider className="my-5" />

              <form
                className="flex flex-col gap-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  void handlePasswordSubmit()
                }}
              >
                <div className="flex flex-col gap-2">
                  <SectionTitle component="h3" variant="subtitle2">
                    {t("settings:security.password.title")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.password.subtitle")}
                  </SectionSubtitle>
                </div>
                <div className="flex flex-col sm:flex-row gap-2.5">
                  <TextField
                    fullWidth
                    type="password"
                    size="small"
                    label={t("settings:security.password.currentLabel")}
                    value={currentPasswordValue}
                    onChange={(event) => {
                      setCurrentPasswordValue(event.target.value)
                      setCurrentPasswordError(null)
                    }}
                    error={Boolean(currentPasswordError)}
                    helperText={currentPasswordError ?? undefined}
                    autoComplete="current-password"
                  />
                  <TextField
                    fullWidth
                    type="password"
                    size="small"
                    label={t("settings:security.password.newLabel")}
                    value={newPasswordValue}
                    onChange={(event) => {
                      setNewPasswordValue(event.target.value)
                      if (passwordError) setPasswordError(null)
                    }}
                    error={isNewPasswordError}
                    helperText={isNewPasswordError ? (passwordError ?? undefined) : undefined}
                    autoComplete="new-password"
                  />
                </div>
                <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center">
                  <TextField
                    fullWidth
                    type="password"
                    size="small"
                    label={t("settings:security.password.confirmLabel")}
                    value={confirmPasswordValue}
                    onChange={(event) => {
                      setConfirmPasswordValue(event.target.value)
                      if (passwordError) setPasswordError(null)
                    }}
                    error={Boolean(confirmPasswordMessage)}
                    helperText={confirmPasswordMessage ?? undefined}
                    autoComplete="new-password"
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={passwordBusy}
                    startIcon={
                      passwordBusy ? <CircularProgress size={18} color="inherit" /> : undefined
                    }
                  >
                    {passwordBusy
                      ? t("settings:security.password.updating")
                      : t("settings:security.password.updateButton")}
                  </Button>
                </div>
              </form>
            </SectionCard>

            <SectionCard component="section">
              <div className="flex flex-col gap-2">
                <SectionTitle variant="subtitle1">{t("settings:sessions.title")}</SectionTitle>
                <SectionSubtitle variant="body2">{t("settings:sessions.subtitle")}</SectionSubtitle>
              </div>

              <div className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center sm:justify-between mt-3">
                <Button
                  variant="outlined"
                  color="error"
                  disabled={revokeAllSessionsMutation.isPending}
                  onClick={() => void handleRevokeAllSessions()}
                  startIcon={
                    revokeAllSessionsMutation.isPending ? (
                      <CircularProgress size={18} color="inherit" />
                    ) : undefined
                  }
                >
                  {t("settings:sessions.revokeAll")}
                </Button>
                <p className="text-sm text-page-text/70">{t("settings:sessions.revokeAllHint")}</p>
              </div>

              {sessionsFetching ? (
                <div className="flex flex-row gap-2.5 items-center mt-3">
                  <CircularProgress size={18} />
                  <p className="text-sm text-page-text">{t("settings:sessions.loading")}</p>
                </div>
              ) : sessionsErrorMessage ? (
                <Alert severity="error" variant="outlined" className="mt-3">
                  {sessionsErrorMessage}
                </Alert>
              ) : sessions.length === 0 ? (
                <p className="text-sm text-page-text mt-3">{t("settings:sessions.empty")}</p>
              ) : (
                <div className="flex flex-col gap-3 mt-3">
                  {sortedSessions.map((session) => {
                    const isRevoked = Boolean(session.revoked_at)
                    const lastSeen = session.last_seen_at ?? session.created_at
                    const timelineSource = session.revoked_at ?? lastSeen
                    const timeline = t("settings:sessions.lastSeen.value", {
                      value: formatSessionTimestamp(timelineSource),
                    })
                    const ipLabel = session.ip_address
                      ? t("settings:sessions.ipAddress", { ip: session.ip_address })
                      : t("settings:sessions.ipUnknown")
                    const meta = [ipLabel, timeline]
                    if (isRevoked) meta.push(t("settings:sessions.status.revoked"))
                    const details = meta.join(" • ")
                    const statusLabel = session.is_current
                      ? t("settings:sessions.status.current")
                      : isRevoked
                        ? t("settings:sessions.status.revoked")
                        : t("settings:sessions.status.active")
                    const disableRevoke =
                      session.is_current || isRevoked || revokeSessionMutation.isPending

                    return (
                      <SessionItem key={session.id} data-revoked={isRevoked ? "true" : undefined}>
                        <div className="min-w-0">
                          <p
                            className={`text-sm break-words ${
                              isRevoked ? "text-page-text/65" : "text-page-text"
                            } ${session.is_current ? "font-semibold" : "font-medium"}`}
                          >
                            {session.user_agent || t("settings:sessions.unknownDevice")}
                          </p>
                          <p
                            className={`text-xs ${
                              isRevoked ? "text-page-text/60 italic" : "text-page-text/70"
                            }`}
                          >
                            {details}
                          </p>
                        </div>
                        <div className="flex flex-row gap-2 items-center justify-start sm:justify-end flex-wrap gap-y-1.5 shrink-0">
                          <Chip
                            size="small"
                            label={statusLabel}
                            className={`font-semibold ${
                              session.is_current
                                ? "text-link-color bg-primary/[0.12] border-primary/[0.32]"
                                : isRevoked
                                  ? "text-page-text/60 bg-transparent border-page-text/[0.16]"
                                  : "text-page-text/[0.72] bg-page-text/[0.06] border-page-text/[0.12]"
                            }`}
                            variant="outlined"
                          />
                          {!session.is_current && !isRevoked && (
                            <Button
                              size="small"
                              variant="text"
                              color="error"
                              disabled={disableRevoke}
                              onClick={() => void handleRevokeSession(session.id)}
                            >
                              {t("settings:sessions.revoke")}
                            </Button>
                          )}
                        </div>
                      </SessionItem>
                    )
                  })}
                </div>
              )}
            </SectionCard>

            <SectionCard component="section">
              <div className="flex flex-col gap-2 mb-3">
                <SectionTitle variant="subtitle1">{t("settings:security.title")}</SectionTitle>
                <SectionSubtitle variant="body2">{t("settings:security.subtitle")}</SectionSubtitle>
              </div>

              <div className="flex flex-col sm:flex-row gap-2 mb-4">
                <Chip size="small" label={defaultMethodText} className="font-semibold" />
                <Chip size="small" label={lastVerifiedText} className="font-semibold" />
              </div>

              <div className="flex flex-col gap-5 mt-3">
                <div className="flex flex-col gap-2">
                  <SectionTitle component="h3" variant="subtitle2">
                    {t("settings:security.method.totp")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.totp.description")}
                  </SectionSubtitle>
                </div>

                {totpDraft ? (
                  <div className="flex flex-col gap-4">
                    <h4 className="text-sm font-semibold">
                      {t("settings:security.totp.pendingTitle")}
                    </h4>
                    <p className="text-sm text-page-text/70">
                      {t("settings:security.totp.pendingDescription")}
                    </p>
                    <TotpQrDisplay
                      otpauthUrl={totpDraft.otpauth_url}
                      secret={totpDraft.secret}
                      label={totpDraft.enrollment.label}
                    />
                    <OtpEntry
                      availableMethods={["totp"]}
                      loading={totpBusy}
                      error={totpError}
                      onSubmit={handleConfirmTotp}
                    />
                    <Button
                      variant="text"
                      color="inherit"
                      disabled={totpBusy}
                      onClick={handleCancelTotp}
                    >
                      {t("settings:security.totp.cancel")}
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {activeTotp.length ? (
                      <div className="flex flex-col gap-2.5">
                        {activeTotp.map((enrollment: MfaTotpEnrollment, index: number) => (
                          <div
                            key={enrollment.id}
                            className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center justify-between border border-glass-border rounded-lg p-3"
                          >
                            <div className="flex flex-col gap-1 min-w-0">
                              <p className="font-semibold text-page-text">
                                {enrollment.label ||
                                  t("settings:security.totp.unnamed", { index: index + 1 })}
                              </p>
                              <p className="text-sm text-page-text/70">
                                {t("settings:security.totp.added", {
                                  value: formatDateTime(enrollment.created_at) ?? "—",
                                })}
                              </p>
                            </div>
                            <Button
                              variant="outlined"
                              color="error"
                              size="small"
                              onClick={() => handleDisableTotp(enrollment.id)}
                            >
                              {t("settings:security.totp.remove")}
                            </Button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-page-text/70">
                        {t("settings:security.totp.empty")}
                      </p>
                    )}
                    <Button
                      variant="contained"
                      onClick={() => void handleStartTotp()}
                      disabled={totpBusy}
                    >
                      {t("settings:security.totp.add")}
                    </Button>
                  </div>
                )}

                <Divider className="my-2" />

                <div className="flex flex-col gap-2">
                  <SectionTitle component="h3" variant="subtitle2">
                    {t("settings:security.method.webauthn")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.webauthn.description")}
                  </SectionSubtitle>
                </div>

                <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center max-w-[420px]">
                  <TextField
                    fullWidth
                    size="small"
                    label={t("settings:security.webauthn.nameLabel")}
                    placeholder={t("settings:security.webauthn.namePlaceholder")}
                    value={webAuthnName}
                    onChange={(event) => setWebAuthnName(event.target.value)}
                  />
                  <Button
                    variant="contained"
                    onClick={() => void handleRegisterWebAuthn()}
                    disabled={webAuthnBusy}
                  >
                    {webAuthnBusy
                      ? t("settings:security.webauthn.registering")
                      : t("settings:security.webauthn.cta")}
                  </Button>
                </div>

                {activeWebAuthn.length ? (
                  <div className="flex flex-col gap-2.5">
                    {activeWebAuthn.map((credential: MfaWebAuthnCredential, index: number) => {
                      const added = formatDateTime(credential.created_at)
                      const lastUsed = formatDateTime(credential.last_used_at ?? null)
                      return (
                        <div
                          key={credential.credential_id}
                          className="flex flex-col sm:flex-row gap-2.5 items-start sm:items-center justify-between border border-glass-border rounded-lg p-3"
                        >
                          <div className="flex flex-col gap-1 min-w-0">
                            <p className="font-semibold text-page-text">
                              {credential.device_name ||
                                t("settings:security.webauthn.unnamed", { index: index + 1 })}
                            </p>
                            <p className="text-sm text-page-text/70">
                              {added
                                ? t("settings:security.webauthn.added", { value: added })
                                : null}
                            </p>
                            {lastUsed ? (
                              <p className="text-sm text-page-text/60">
                                {t("settings:security.webauthn.lastUsed", { value: lastUsed })}
                              </p>
                            ) : null}
                          </div>
                          <Button
                            variant="outlined"
                            color="error"
                            size="small"
                            onClick={() => handleRemoveWebAuthn(credential.credential_id)}
                          >
                            {t("settings:security.webauthn.remove")}
                          </Button>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-page-text/70">
                    {t("settings:security.webauthn.empty")}
                  </p>
                )}

                <Divider className="my-2" />

                <div className="flex flex-col gap-2">
                  <SectionTitle component="h3" variant="subtitle2">
                    {t("settings:security.method.recovery")}
                  </SectionTitle>
                  <SectionSubtitle variant="body2">
                    {t("settings:security.recovery.description")}
                  </SectionSubtitle>
                </div>

                <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
                  <Button
                    variant="outlined"
                    onClick={handleGenerateRecoveryCodes}
                    disabled={recoveryBusy}
                  >
                    {recoveryBusy
                      ? t("settings:security.recovery.generating")
                      : t("settings:security.recovery.generate")}
                  </Button>
                  <p className="text-sm text-page-text/70">{recoveryStatusText}</p>
                </div>

                {generatedRecoveryCodes.length ? (
                  <RecoveryCodeList
                    codes={generatedRecoveryCodes.map((code) => ({ code }))}
                    allowCopy
                  />
                ) : null}
              </div>
            </SectionCard>
          </div>
        )}

        {tab === 2 && (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-4">
              <div className="flex flex-row items-center gap-2">
                <img
                  src={spotifyLogo}
                  alt={t("settings:integrations.spotify.alt")}
                  width={22}
                  height={22}
                  style={{ display: "block", borderRadius: "50%" }}
                  loading="lazy"
                  decoding="async"
                />
                <h3 className="text-lg font-semibold text-page-text">
                  {t("settings:integrations.spotify.title")}
                </h3>
              </div>
              <div className="flex flex-row items-center gap-2.5 flex-wrap">
                <Chip
                  size="small"
                  className="glass--chip"
                  label={
                    spotifyConnected
                      ? t("settings:integrations.spotify.status.connected")
                      : t("settings:integrations.spotify.status.disconnected")
                  }
                  color={spotifyConnected ? "success" : "default"}
                  variant="outlined"
                />
                {spotifyConnected && !!spotifyName && (
                  <Chip size="small" variant="outlined" label={spotifyName} />
                )}
              </div>
              {!spotifyConnected ? (
                <Button variant="contained" onClick={connectSpotify} className="self-start">
                  {t("settings:integrations.spotify.connect")}
                </Button>
              ) : (
                <Button
                  variant="outlined"
                  color="error"
                  onClick={disconnectSpotify}
                  className="self-start"
                >
                  {t("settings:integrations.spotify.disconnect")}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("settings:account.logout.dialogTitle")}</DialogTitle>
        <DialogContent>
          <p className="text-sm">{t("settings:account.logout.dialogDescription")}</p>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)}>{t("common:buttons.cancel")}</Button>
          <Button
            color="error"
            onClick={async () => {
              setConfirmLogout(false)
              await logout()
            }}
          >
            {t("settings:account.logout.confirm")}
          </Button>
        </DialogActions>
      </Dialog>

      <StepUpDialog
        open={stepUpOpen}
        onClose={handleStepUpClose}
        onCompleted={handleStepUpCompleted}
        description={t("settings:security.stepUp.description")}
      />

      <Snackbar
        open={!!snack}
        autoHideDuration={2600}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={() => setSnack(null)}
          severity={snack?.sev || "info"}
          variant="filled"
          className="w-full"
        >
          {snack?.text}
        </Alert>
      </Snackbar>
    </div>
  )
}
