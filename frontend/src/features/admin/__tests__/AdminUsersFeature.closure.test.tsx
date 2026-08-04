import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ChangeEventHandler, ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AdminUsersFeature } from "../AdminUsersFeature"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T) => value,
}))

vi.mock("@/api/client", () => ({
  default: {
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock("@/api/hooks/adminUsers", () => ({
  useAdminUsersQuery: vi.fn(),
  useAdminGroupsQuery: vi.fn(),
  invalidateAllAdminUsers: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}))

vi.mock("@/utils/avatar", () => ({
  buildAvatarUrl: (url: string | null, id: string) => url ?? `/avatar/${id}`,
}))

vi.mock("@/components/settings", () => ({
  Avatar: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
  SectionCard: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TextField: ({
    id,
    label,
    value,
    onChange,
  }: {
    id: string
    label: string
    value: string
    onChange: ChangeEventHandler<HTMLInputElement>
  }) => (
    <label htmlFor={id}>
      {label}
      <input id={id} value={value} onChange={onChange} />
    </label>
  ),
}))

vi.mock("@/components/ui/data-table/DataTableColumnHeader", () => ({
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}))

vi.mock("@/components/ui/data-table/DataTable", () => ({
  DataTable: ({
    columns,
    data,
  }: {
    columns: Array<{
      header?: unknown
      cell?: (context: unknown) => ReactNode
    }>
    data: unknown[]
  }) => (
    <div data-testid="admin-users-table">
      <div data-testid="admin-users-headers">
        {columns.map((column, index) => (
          <div key={index}>
            {typeof column.header === "function"
              ? (column.header as (context: unknown) => ReactNode)({ column: {} })
              : column.header}
          </div>
        ))}
      </div>
      {data.map((user) => {
        const record = user as Record<string, unknown>
        const row = {
          original: user,
          getValue: (key: string) => record[key],
        }
        return (
          <div key={String(record.id)}>
            {columns.map((column, index) => (
              <div key={index}>{column.cell?.({ row })}</div>
            ))}
          </div>
        )
      })}
    </div>
  ),
}))

vi.mock("@/components/ui", () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    onCancel,
    isLoading,
  }: {
    open: boolean
    onConfirm: () => void
    onCancel: () => void
    isLoading: boolean
  }) =>
    open ? (
      <div role="dialog" aria-busy={isLoading}>
        <button type="button" onClick={onConfirm}>
          confirm-delete
        </button>
        <button type="button" onClick={onCancel}>
          cancel-delete
        </button>
      </div>
    ) : null,
}))

import api from "@/api/client"
import {
  invalidateAllAdminUsers,
  useAdminGroupsQuery,
  useAdminUsersQuery,
} from "@/api/hooks/adminUsers"
import { useAuth } from "@/contexts/AuthContext"

const apiPatchMock = vi.mocked(api.patch)
const apiDeleteMock = vi.mocked(api.delete)
const invalidateMock = vi.mocked(invalidateAllAdminUsers)
const usersQueryMock = vi.mocked(useAdminUsersQuery)
const groupsQueryMock = vi.mocked(useAdminGroupsQuery)
const authMock = vi.mocked(useAuth)

const users = [
  {
    id: "u-current",
    full_name: "Current Admin",
    email: "current@example.test",
    role: "admin",
    group_id: null,
    avatar_url: null,
  },
  {
    id: "u-student",
    full_name: "Student",
    email: "student@example.test",
    role: "student",
    group_id: "g1",
    avatar_url: null,
  },
  {
    id: "u-student-empty",
    full_name: "Unassigned Student",
    email: "empty@example.test",
    role: "student",
    group_id: null,
    avatar_url: null,
  },
  {
    id: "u-teacher",
    full_name: "Teacher",
    email: "teacher@example.test",
    role: "teacher",
    group_id: null,
    avatar_url: null,
  },
  {
    id: "u-admin",
    full_name: "Other Admin",
    email: "admin@example.test",
    role: "admin",
    group_id: null,
    avatar_url: null,
  },
]

const groups = [
  { id: "g1", name: "Group One" },
  { id: "g2", name: "Group Two" },
]

const renderFeature = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AdminUsersFeature />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  usersQueryMock.mockReturnValue({ data: users } as never)
  groupsQueryMock.mockReturnValue({ data: groups } as never)
  authMock.mockReturnValue({ user: { id: "u-current", role: "admin" } } as never)
  apiPatchMock.mockResolvedValue({} as never)
  apiDeleteMock.mockResolvedValue({} as never)
  invalidateMock.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("AdminUsersFeature closure", () => {
  it("handles filters, group assignments, and both empty/non-empty group values", async () => {
    renderFeature()

    fireEvent.change(screen.getByLabelText("users.filters.fullName"), {
      target: { value: "Student" },
    })
    fireEvent.change(screen.getByLabelText("users.filters.group"), {
      target: { value: "g2" },
    })
    fireEvent.change(screen.getByLabelText("users.filters.role"), {
      target: { value: "teacher" },
    })

    const studentGroups = screen
      .getAllByRole("combobox")
      .filter((element) => (element as HTMLSelectElement).value === "g1")
    expect(studentGroups).toHaveLength(2)
    const studentGroup = studentGroups[0]

    fireEvent.change(studentGroup!, { target: { value: "g2" } })
    await waitFor(() => {
      expect(apiPatchMock).toHaveBeenCalledWith("/users/u-student", { group_id: "g2" })
    })
    await waitFor(() => expect(invalidateMock).toHaveBeenCalled())

    // The second student select is the mobile-card renderer and has a
    // separate callback closure from the desktop table cell.
    fireEvent.change(studentGroups[1]!, { target: { value: "g2" } })
    await waitFor(() => expect(apiPatchMock).toHaveBeenCalledWith("/users/u-student", { group_id: "g2" }))

    fireEvent.change(studentGroup!, { target: { value: "" } })
    await waitFor(() => {
      expect(apiPatchMock).toHaveBeenLastCalledWith("/users/u-student", { group_id: null })
    })
  })

  it("opens, confirms, and closes the delete dialog with invalidation", async () => {
    renderFeature()

    const deleteButtons = screen.getAllByRole("button", { name: "users.table.deleteUser" })
    expect(deleteButtons.length).toBeGreaterThan(0)
    fireEvent.click(deleteButtons[0]!)

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))

    await waitFor(() => {
      expect(apiDeleteMock).toHaveBeenCalledWith("/users/u-student")
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    })
    expect(invalidateMock).toHaveBeenCalled()

    // Exercise the mobile-card delete callback and the dialog cancel path.
    const mobileDeleteButton = screen.getAllByRole("button", { name: "users.table.deleteUser" }).at(-1)
    expect(mobileDeleteButton).toBeDefined()
    fireEvent.click(mobileDeleteButton!)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "cancel-delete" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
