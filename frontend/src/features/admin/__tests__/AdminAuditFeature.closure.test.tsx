import type { ButtonHTMLAttributes, ChangeEvent, HTMLAttributes, ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { AuditLog } from "@/types/Admin"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const motion = vi.hoisted(() => ({ reduced: false }))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => motion.reduced,
}))

vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T) => value,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number; current?: number }) =>
      values ? `${key}:${values.count ?? values.current ?? ""}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
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
    onChange,
  }: {
    id: string
    label: string
    value: string
    onChange: (event: ChangeEvent<HTMLInputElement>) => void
  }) => (
    <label htmlFor={id}>
      {label}
      <input id={id} value={value} onChange={onChange} />
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

const auditQuery = vi.hoisted(() => ({
  result: {
    data: undefined as { items: AuditLog[]; total: number } | undefined,
    isPending: false,
  },
  calls: [] as Array<{
    filters: { resource_type: string; action: string }
    pagination: { page: number; rowsPerPage: number }
  }>,
}))

vi.mock("@/api/hooks/adminAudit", () => ({
  useAdminAuditLogsQuery: vi.fn(
    (
      filters: { resource_type: string; action: string },
      pagination: { page: number; rowsPerPage: number }
    ) => {
      auditQuery.calls.push({ filters, pagination })
      return auditQuery.result
    }
  ),
}))

import { AdminAuditFeature } from "@/features/admin/AdminAuditFeature"

const makeLog = (overrides: Partial<AuditLog> = {}): AuditLog => ({
  id: 1,
  actor_user_id: 10,
  actor_name: "Audit actor",
  subject_user_id: 20,
  subject_name: "Audit subject",
  resource_type: "user",
  resource_id: "resource-1",
  action: "user.login",
  context: { request_id: "req-1" },
  ip_address: "127.0.0.1",
  user_agent: "Test browser",
  created_at: "2026-07-31T12:00:00Z",
  is_valid: true,
  ...overrides,
})

const renderFeature = () => render(<AdminAuditFeature />)

beforeEach(() => {
  motion.reduced = false
  auditQuery.result = {
    data: undefined,
    isPending: false,
  }
  auditQuery.calls = []
})

describe("AdminAuditFeature closure", () => {
  it("renders the initial loading state when no page data exists", () => {
    auditQuery.result = { data: undefined, isPending: true }

    renderFeature()

    expect(screen.getByText("audit.title")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
  })

  it("covers action colors, integrity states, fallbacks, context and both motion modes", async () => {
    const logs = [
      makeLog({ id: 1, action: "user.delete" }),
      makeLog({
        id: 2,
        action: "user.create",
        actor_name: undefined,
        actor_user_id: undefined,
        subject_name: undefined,
        subject_user_id: undefined,
        resource_id: undefined,
        ip_address: undefined,
        user_agent: undefined,
        context: {},
        is_valid: false,
      }),
      makeLog({ id: 3, action: "user.modify", context: undefined }),
      makeLog({ id: 4, action: "user.add" }),
      makeLog({ id: 5, action: "user.login" }),
    ]
    auditQuery.result = { data: { items: logs, total: logs.length }, isPending: false }

    const user = userEvent.setup()
    const { rerender } = renderFeature()

    expect(screen.getAllByRole("row")).toHaveLength(6)
    expect(screen.getByText("audit.details.system")).toBeInTheDocument()
    expect(screen.getByText("SYSTEM")).toBeInTheDocument()
    expect(screen.getByTitle("audit.details.integrityTampered")).toBeInTheDocument()
    expect(screen.getByText("USER DELETE")).toBeInTheDocument()
    expect(screen.getByText("USER CREATE")).toBeInTheDocument()
    expect(screen.getByText("USER MODIFY")).toBeInTheDocument()
    expect(screen.getByText("USER ADD")).toBeInTheDocument()
    expect(screen.getByText("USER LOGIN")).toBeInTheDocument()

    const expandButtons = screen.getAllByRole("button", { name: "audit.table.expandRow" })
    await user.click(expandButtons[0]!)
    expect(screen.getByText(/request_id/)).toBeInTheDocument()
    expect(screen.getByText("Audit subject")).toBeInTheDocument()

    await user.click(document.getElementById("audit-row-toggle-2")!)
    expect(screen.getAllByText("audit.details.notAvailable").length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText("audit.details.unknown")).toBeInTheDocument()

    motion.reduced = true
    rerender(<AdminAuditFeature />)
    await user.click(document.getElementById("audit-row-toggle-3")!)
    expect(screen.getAllByText("audit.details.title").length).toBeGreaterThanOrEqual(2)

    fireEvent.click(document.getElementById("audit-row-toggle-1")!)
    expect(document.getElementById("audit-row-toggle-1")).toHaveAttribute("aria-expanded", "false")
  })

  it("keeps the table visible while refreshing a populated page", () => {
    const logs = [makeLog()]
    auditQuery.result = { data: { items: logs, total: 101 }, isPending: true }

    renderFeature()

    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByText("audit.pagination.total:101")).toBeInTheDocument()
  })

  it("updates filters and pagination query inputs", async () => {
    const user = userEvent.setup()
    const logs = [makeLog()]
    auditQuery.result = { data: { items: logs, total: 101 }, isPending: false }

    renderFeature()

    expect(screen.getByRole("button", { name: "audit.pagination.previous" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "audit.pagination.next" })).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "audit.pagination.next" }))
    expect(auditQuery.calls[auditQuery.calls.length - 1]!.pagination.page).toBe(1)

    await user.type(screen.getByLabelText("audit.filters.resourceType"), "event")

    let latestCall = auditQuery.calls[auditQuery.calls.length - 1]!
    expect(latestCall.filters).toEqual({ resource_type: "event", action: "" })
    expect(latestCall.pagination).toEqual({ page: 0, rowsPerPage: 50 })

    await user.click(screen.getByRole("button", { name: "audit.pagination.next" }))
    expect(auditQuery.calls[auditQuery.calls.length - 1]!.pagination).toEqual({
      page: 1,
      rowsPerPage: 50,
    })

    await user.type(screen.getByLabelText("audit.filters.action"), "create")
    latestCall = auditQuery.calls[auditQuery.calls.length - 1]!
    expect(latestCall.filters).toEqual({ resource_type: "event", action: "create" })
    expect(latestCall.pagination).toEqual({ page: 0, rowsPerPage: 50 })

    await user.click(screen.getByRole("button", { name: "audit.pagination.next" }))
    expect(screen.getByRole("button", { name: "audit.pagination.previous" })).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "audit.pagination.previous" }))
    expect(auditQuery.calls[auditQuery.calls.length - 1]!.pagination.page).toBe(0)
  })

  it("renders an empty non-loading page and disables both pagination controls", () => {
    auditQuery.result = { data: { items: [], total: 0 }, isPending: false }

    renderFeature()

    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "audit.pagination.previous" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "audit.pagination.next" })).toBeDisabled()
  })
})
