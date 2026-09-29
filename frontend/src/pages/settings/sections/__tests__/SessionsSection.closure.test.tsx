import { fireEvent, render, screen } from "@testing-library/react"
import { forwardRef, type ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ActiveSessionOut } from "@/api/generated"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { value?: string }) =>
      options?.value ? `${key}:${options.value}` : key,
  }),
}))

vi.mock("@/components/settings", () => ({
  Button: forwardRef<
    HTMLButtonElement,
    {
      children?: ReactNode
      onClick?: () => void
      disabled?: boolean
      leadingIcon?: ReactNode
      startIcon?: ReactNode
      color?: string
      variant?: string
      "data-testid"?: string
    }
  >(function MockButton(
    {
      children,
      onClick,
      disabled,
      leadingIcon: _leadingIcon,
      startIcon: _startIcon,
      color: _color,
      variant: _variant,
      ...props
    },
    ref
  ) {
    return (
      <button ref={ref} type="button" onClick={onClick} disabled={disabled} {...props}>
        {children}
      </button>
    )
  }),
  Chip: ({ label, ...props }: { label: string; [key: string]: unknown }) => (
    <span {...props}>{label}</span>
  ),
  Alert: ({ children }: { children?: ReactNode }) => <div role="alert">{children}</div>,
  CircularProgress: ({ size }: { size?: number }) => (
    <span data-testid={`progress-${size ?? "default"}`} />
  ),
  SectionSubtitle: ({ children }: { children?: ReactNode }) => <p>{children}</p>,
  AccordionSection: ({ children, title }: { children?: ReactNode; title: string }) => (
    <section aria-label={title}>{children}</section>
  ),
  SessionItem: ({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) => (
    <article {...props}>{children}</article>
  ),
}))

import { SessionsSection } from "../SessionsSection"

const baseProps = {
  setSnackbar: vi.fn(),
  sessions: [],
  sortedSessions: [],
  sessionsFetching: false,
  sessionsErrorMessage: null,
  revokeAllPending: false,
  revokeSessionPending: false,
  onRevokeSession: vi.fn(async () => undefined),
  onRevokeAllSessions: vi.fn(async () => undefined),
  formatSessionTimestamp: (value: string) => `formatted:${value}`,
}

const session = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "session-1",
    user_agent: "Firefox",
    ip_address: "127.0.0.1",
    created_at: "2026-01-01T00:00:00Z",
    last_seen_at: "2026-01-02T00:00:00Z",
    revoked_at: null,
    is_current: false,
    ...overrides,
  }) as unknown as ActiveSessionOut

afterEach(() => {
  vi.clearAllMocks()
})

describe("SessionsSection closure paths", () => {
  it("renders loading, error, and empty states", () => {
    const { rerender } = render(
      <SessionsSection {...baseProps} sessionsFetching revokeAllPending />
    )
    expect(screen.getByText("settings:sessions.loading")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "settings:sessions.revokeAll" })).toBeDisabled()

    rerender(<SessionsSection {...baseProps} sessionsErrorMessage="Session service failed" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Session service failed")

    rerender(<SessionsSection {...baseProps} />)
    expect(screen.getByText("settings:sessions.empty")).toBeInTheDocument()
  })

  it("renders current, revoked, and active sessions with their action branches", () => {
    const onRevokeSession = vi.fn(async () => undefined)
    const onRevokeAllSessions = vi.fn(async () => undefined)
    const sessions = [
      session({ id: "current", is_current: true, user_agent: "Chrome" }),
      session({
        id: "revoked",
        user_agent: null,
        ip_address: null,
        last_seen_at: null,
        revoked_at: "2026-02-01T00:00:00Z",
      }),
      session({ id: "active", last_seen_at: null }),
    ]

    render(
      <SessionsSection
        {...baseProps}
        sessions={sessions}
        sortedSessions={sessions}
        onRevokeSession={onRevokeSession}
        onRevokeAllSessions={onRevokeAllSessions}
      />
    )

    expect(screen.getByTestId("session-status-current")).toHaveTextContent(
      "settings:sessions.status.current"
    )
    expect(screen.getByTestId("session-status-revoked")).toHaveTextContent(
      "settings:sessions.status.revoked"
    )
    expect(screen.getByTestId("session-status-active")).toHaveTextContent(
      "settings:sessions.status.active"
    )
    expect(screen.getByText("settings:sessions.unknownDevice")).toBeInTheDocument()
    expect(screen.getByText(/settings:sessions\.ipUnknown/)).toBeInTheDocument()
    expect(screen.queryByTestId("session-revoke-current")).not.toBeInTheDocument()
    expect(screen.queryByTestId("session-revoke-revoked")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("session-revoke-active"))
    fireEvent.click(screen.getByRole("button", { name: "settings:sessions.revokeAll" }))
    expect(onRevokeSession).toHaveBeenCalledWith("active")
    expect(onRevokeAllSessions).toHaveBeenCalledOnce()
  })
})
