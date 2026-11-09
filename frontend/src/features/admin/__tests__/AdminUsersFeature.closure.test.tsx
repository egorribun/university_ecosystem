import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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
  Alert: ({ children }: { children: ReactNode }) => <div role="alert">{children}</div>,
  Snackbar: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div>{children}</div> : null,
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
      header?: ReactNode | ((context: unknown) => ReactNode)
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
          <div key={String(record.id)} data-testid={`admin-users-row-${String(record.id)}`}>
            {columns.map((column, index) => (
              <div key={index}>{column.cell?.({ row })}</div>
            ))}
          </div>
        )
      })}
    </div>
  ),
}))

vi.mock("@/components/ui/ConfirmDialog", () => ({
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

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = (value) => resolvePromise(value)
    reject = (reason) => rejectPromise(reason)
  })
  return { promise, resolve, reject }
}

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
    await waitFor(() =>
      expect(apiPatchMock).toHaveBeenCalledWith("/users/u-student", { group_id: "g2" })
    )

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
    const mobileDeleteButton = screen
      .getAllByRole("button", { name: "users.table.deleteUser" })
      .at(-1)
    expect(mobileDeleteButton).toBeDefined()
    fireEvent.click(mobileDeleteButton!)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "cancel-delete" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})

describe("AdminUsersFeature mutation failure feedback", () => {
  it("announces a localized group assignment failure without invalidating users", async () => {
    apiPatchMock.mockRejectedValueOnce(new Error("upstream detail"))
    renderFeature()

    const studentGroup = screen
      .getAllByRole("combobox")
      .find((element) => (element as HTMLSelectElement).value === "g1")
    expect(studentGroup).toBeDefined()
    fireEvent.change(studentGroup!, { target: { value: "g2" } })

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("common:errors.generic")
    expect(alert).not.toHaveTextContent("upstream detail")
    expect(invalidateMock).not.toHaveBeenCalled()
    const dismissButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(dismissButton).toHaveClass("min-h-[44px]", "min-w-[44px]")
    fireEvent.click(dismissButton)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("ignores an older group failure after a newer group update succeeds", async () => {
    const firstRequest = createDeferred<unknown>()
    const secondRequest = createDeferred<unknown>()
    apiPatchMock
      .mockReturnValueOnce(firstRequest.promise as never)
      .mockReturnValueOnce(secondRequest.promise as never)
    renderFeature()

    const studentGroup = screen
      .getAllByRole("combobox")
      .find((element) => (element as HTMLSelectElement).value === "g1")
    expect(studentGroup).toBeDefined()
    fireEvent.change(studentGroup!, { target: { value: "g2" } })
    fireEvent.change(studentGroup!, { target: { value: "" } })
    expect(apiPatchMock).toHaveBeenCalledTimes(2)

    await act(async () => {
      secondRequest.resolve({})
      await secondRequest.promise
    })
    await waitFor(() => expect(invalidateMock).toHaveBeenCalledTimes(1))

    await act(async () => {
      firstRequest.reject(new Error("stale upstream detail"))
      await firstRequest.promise.catch(() => undefined)
    })

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(invalidateMock).toHaveBeenCalledTimes(1)
  })

  it("keeps errors scoped to each user and group field", async () => {
    const olderUserRequest = createDeferred<unknown>()
    const newerUserRequest = createDeferred<unknown>()
    const nextNewerUserRequest = createDeferred<unknown>()
    const retryNewerUserRequest = createDeferred<unknown>()
    apiPatchMock
      .mockReturnValueOnce(olderUserRequest.promise as never)
      .mockReturnValueOnce(newerUserRequest.promise as never)
      .mockReturnValueOnce(nextNewerUserRequest.promise as never)
      .mockReturnValueOnce(retryNewerUserRequest.promise as never)
    renderFeature()

    const olderUserGroup = within(screen.getByTestId("admin-users-row-u-student")).getByRole(
      "combobox"
    )
    const newerUserGroup = within(screen.getByTestId("admin-users-row-u-student-empty")).getByRole(
      "combobox"
    )
    fireEvent.change(olderUserGroup, { target: { value: "g2" } })
    fireEvent.change(newerUserGroup, { target: { value: "g2" } })

    await act(async () => {
      newerUserRequest.resolve({})
      await newerUserRequest.promise
    })
    await waitFor(() => expect(invalidateMock).toHaveBeenCalledTimes(1))

    await act(async () => {
      olderUserRequest.reject(new Error("older user failure"))
      await olderUserRequest.promise.catch(() => undefined)
    })
    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")

    fireEvent.change(
      within(screen.getByTestId("admin-users-row-u-student-empty")).getByRole("combobox"),
      {
        target: { value: "g1" },
      }
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    await act(async () => {
      nextNewerUserRequest.reject(new Error("newer user failure"))
      await nextNewerUserRequest.promise.catch(() => undefined)
    })
    expect(screen.getAllByRole("alert")).toHaveLength(1)

    fireEvent.change(
      within(screen.getByTestId("admin-users-row-u-student-empty")).getByRole("combobox"),
      { target: { value: "g2" } }
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    await act(async () => {
      retryNewerUserRequest.resolve({})
      await retryNewerUserRequest.promise
    })
    expect(screen.getByRole("alert")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("waits for the latest same-user group update before showing a failure", async () => {
    const firstRequest = createDeferred<unknown>()
    const secondRequest = createDeferred<unknown>()
    apiPatchMock
      .mockReturnValueOnce(firstRequest.promise as never)
      .mockReturnValueOnce(secondRequest.promise as never)
    renderFeature()

    const studentGroup = within(screen.getByTestId("admin-users-row-u-student")).getByRole(
      "combobox"
    )
    fireEvent.change(studentGroup, { target: { value: "g2" } })
    fireEvent.change(studentGroup, { target: { value: "" } })

    await act(async () => {
      firstRequest.reject(new Error("stale upstream detail"))
      await firstRequest.promise.catch(() => undefined)
    })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    await act(async () => {
      secondRequest.reject(new Error("latest upstream detail"))
      await secondRequest.promise.catch(() => undefined)
    })
    expect(await screen.findByRole("alert")).toHaveTextContent("common:errors.generic")
  })

  it("resets mutation feedback and pending delete state when the acting admin changes", async () => {
    const pendingDeleteForPreviousAdmin = createDeferred<unknown>()
    const pendingDeleteForCurrentAdmin = createDeferred<unknown>()
    apiPatchMock.mockRejectedValueOnce(new Error("old admin failure"))
    apiDeleteMock
      .mockReturnValueOnce(pendingDeleteForPreviousAdmin.promise as never)
      .mockReturnValueOnce(pendingDeleteForCurrentAdmin.promise as never)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={queryClient}>
        <AdminUsersFeature />
      </QueryClientProvider>
    )

    const studentGroup = within(screen.getByTestId("admin-users-row-u-student")).getByRole(
      "combobox"
    )
    fireEvent.change(studentGroup, { target: { value: "g2" } })
    expect(await screen.findByRole("alert")).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole("button", { name: "users.table.deleteUser" })[0]!)
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")

    authMock.mockReturnValue({ user: { id: "u-next-admin", role: "admin" } } as never)
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <AdminUsersFeature />
      </QueryClientProvider>
    )
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    })

    // The new acting admin can start deleting the same target before the old
    // admin's request completes. The old completion must not close this dialog.
    fireEvent.click(screen.getAllByRole("button", { name: "users.table.deleteUser" })[0]!)
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))
    expect(apiDeleteMock).toHaveBeenCalledTimes(2)
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")

    await act(async () => {
      pendingDeleteForPreviousAdmin.resolve({})
      await pendingDeleteForPreviousAdmin.promise
    })
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")
    expect(invalidateMock).not.toHaveBeenCalled()

    await act(async () => {
      pendingDeleteForCurrentAdmin.resolve({})
      await pendingDeleteForCurrentAdmin.promise
    })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(invalidateMock).toHaveBeenCalledTimes(1)
  })

  it("keeps another user's delete dialog and pending state when a delete completes", async () => {
    const firstDelete = createDeferred<unknown>()
    const secondDelete = createDeferred<unknown>()
    apiDeleteMock
      .mockReturnValueOnce(firstDelete.promise as never)
      .mockReturnValueOnce(secondDelete.promise as never)
    renderFeature()

    fireEvent.click(
      within(screen.getByTestId("admin-users-row-u-student")).getByRole("button", {
        name: "users.table.deleteUser",
      })
    )
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")

    fireEvent.click(
      within(screen.getByTestId("admin-users-row-u-student-empty")).getByRole("button", {
        name: "users.table.deleteUser",
      })
    )
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))
    expect(apiDeleteMock).toHaveBeenNthCalledWith(1, "/users/u-student")
    expect(apiDeleteMock).toHaveBeenNthCalledWith(2, "/users/u-student-empty")
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")

    await act(async () => {
      firstDelete.resolve({})
      await firstDelete.promise
    })
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true")
    expect(invalidateMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      secondDelete.resolve({})
      await secondDelete.promise
    })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(invalidateMock).toHaveBeenCalledTimes(2)
  })

  it("announces a localized delete failure and leaves the confirmation available to retry", async () => {
    apiDeleteMock.mockRejectedValueOnce(new Error("upstream detail"))
    renderFeature()

    fireEvent.click(screen.getAllByRole("button", { name: "users.table.deleteUser" })[0]!)
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("common:errors.generic")
    expect(alert).not.toHaveTextContent("upstream detail")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(invalidateMock).not.toHaveBeenCalled()

    apiDeleteMock.mockResolvedValueOnce({} as never)
    fireEvent.click(screen.getByRole("button", { name: "confirm-delete" }))

    await waitFor(() => {
      expect(apiDeleteMock).toHaveBeenCalledTimes(2)
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    })
    expect(apiDeleteMock).toHaveBeenNthCalledWith(1, "/users/u-student")
    expect(apiDeleteMock).toHaveBeenNthCalledWith(2, "/users/u-student")
    expect(invalidateMock).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})
