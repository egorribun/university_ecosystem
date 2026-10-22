import type { ButtonHTMLAttributes, ChangeEvent, HTMLAttributes, ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: <T,>(value: T) => value }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number; current?: number }) => {
      if (key === "common:statuses.error") return "Something went wrong"
      return values ? key + ":" + (values.count ?? values.current ?? "") : key
    },
  }),
}))
vi.mock("@/utils/date", () => ({
  formatDate: (value: string) => value,
  presets: { auditDate: "date", auditTime: "time" },
}))
vi.mock("@/components/settings", () => ({
  SectionCard: ({ children, ...props }: HTMLAttributes<HTMLElement> & { children?: ReactNode }) => (
    <section {...props}>{children}</section>
  ),
  TextField: ({
    id,
    label,
    value,
  }: {
    id: string
    label: string
    value: string
    onChange: (event: ChangeEvent<HTMLInputElement>) => void
  }) => (
    <label htmlFor={id}>
      {label}
      <input id={id} value={value} readOnly />
    </label>
  ),
  Button: ({
    children,
    disabled,
    onClick,
    id,
    "aria-label": ariaLabel,
    "aria-expanded": ariaExpanded,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement> & { children?: ReactNode }) => (
    <button
      type="button"
      id={id}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      aria-expanded={ariaExpanded}
      {...props}
    >
      {children}
    </button>
  ),
}))

const query = vi.hoisted(() => ({
  result: {
    data: undefined as { items: unknown[]; total: number } | undefined,
    isPending: false,
    isError: false,
  },
}))
vi.mock("@/api/hooks/adminAudit", () => ({
  useAdminAuditLogsQuery: () => query.result,
}))

import { AdminAuditFeature } from "@/features/admin/AdminAuditFeature"

describe("AUD-215 admin audit query state", () => {
  beforeEach(() => {
    query.result = { data: undefined, isPending: false, isError: false }
  })

  it("retains a distinct loading state before the first page arrives", () => {
    query.result = { data: undefined, isPending: true, isError: false }

    render(<AdminAuditFeature />)

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("shows a zero-row total for a successful empty audit response", () => {
    query.result = { data: { items: [], total: 0 }, isPending: false, isError: false }

    render(<AdminAuditFeature />)

    expect(screen.getByRole("table", { name: "audit.table.aria" })).toBeInTheDocument()
    expect(screen.getByText("audit.pagination.total:0")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does not represent a failed audit request as zero records", () => {
    query.result = { data: undefined, isPending: false, isError: true }

    render(<AdminAuditFeature />)

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong")
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.queryByText("audit.pagination.total:0")).not.toBeInTheDocument()
  })
  it("keeps cached audit rows, filters, and totals visible when a refresh fails", () => {
    const cachedLog = {
      id: 42,
      actor_user_id: 7,
      actor_name: "Cached audit actor",
      subject_user_id: 12,
      subject_name: "Cached subject",
      resource_type: "user",
      resource_id: "user-12",
      action: "user.update",
      context: { request_id: "cached-request" },
      ip_address: "127.0.0.1",
      user_agent: "Audit test browser",
      created_at: "2026-10-16T10:00:00Z",
      is_valid: true,
      signature_scheme: "canonical_v2",
      authenticated_fields: ["id", "actor_user_id", "action"],
      unauthenticated_fields: ["actor_name"],
    }
    query.result = {
      data: { items: [cachedLog], total: 75 },
      isPending: false,
      isError: true,
    }

    render(<AdminAuditFeature />)

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong")
    expect(screen.getByRole("table", { name: "audit.table.aria" })).toBeInTheDocument()
    expect(screen.getByText("Cached audit actor")).toBeInTheDocument()
    expect(screen.getByText("audit.pagination.total:75")).toBeInTheDocument()
    expect(screen.queryByText("audit.pagination.total:0")).not.toBeInTheDocument()
    expect(screen.getByLabelText("audit.filters.resourceType")).toBeInTheDocument()
    expect(screen.getByLabelText("audit.filters.action")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "audit.pagination.previous" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "audit.pagination.next" })).toBeEnabled()
  })
})
