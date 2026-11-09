import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Trash2, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { DataTableColumnDef } from "@/components/ui/data-table/dataTableFeatures"
import { useQueryClient } from "@tanstack/react-query"
// PERF-20-05 (audit 2026-03-24): Debounce text filters.
import { useDebounced } from "@/hooks/useDebounced"

import api from "@/api/client"
// Wave 163 SW3 — TanStack Query factories for the admin users + groups
// endpoints. Closes W150 §Honesty #3 deferral.
import {
  invalidateAllAdminUsers,
  useAdminGroupsQuery,
  useAdminUsersQuery,
  type AdminUser,
  type AdminUserFilters,
  type UserRole,
} from "@/api/hooks/adminUsers"
import { useAuth } from "@/contexts/AuthContext"
import { buildAvatarUrl } from "@/utils/avatar"
import { cn } from "@/utils/cn"
import { TextField, SectionCard, Avatar, Alert, Snackbar } from "@/components/settings"
import { DataTable } from "@/components/ui/data-table/DataTable"
import { DataTableColumnHeader } from "@/components/ui/data-table/DataTableColumnHeader"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"

type UserFilters = AdminUserFilters
type MutationScope = `group:${string}:group_id` | `delete:${string}`

function groupMutationScope(userId: string): MutationScope {
  return `group:${userId}:group_id`
}

function deleteMutationScope(userId: string): MutationScope {
  return `delete:${userId}`
}

/**
 * AdminUsersFeature — Wave 164 SW2 orchestrator.
 *
 * Migrated from `pages/AdminUsers.tsx` (322 lines) to match the
 * features/activity/ pattern (W112 SW2). The page is now a thin
 * <Layout><FeatureErrorBoundary> wrapper; the feature owns content + state.
 *
 * Data layer: W163 SW3 TanStack Query factories at @/api/hooks/adminUsers
 * (useAdminUsersQuery + useAdminGroupsQuery + invalidateAllAdminUsers).
 * Closes W150 §Honesty #1 (features/admin/ structure migration).
 */
export function AdminUsersFeature() {
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<UserFilters>({ full_name: "", group_id: "", role: "" })
  // PERF-20-05: Debounce text filter to prevent API spam on every keystroke.
  // PERF-23-04: admin filters use validation preset (350ms).
  const debouncedFilters = useDebounced(filters, "validation")
  // Wave 163 SW3 — useAdminUsersQuery + useAdminGroupsQuery replace pre-W163
  // useCallback fetchUsers/fetchGroups + useState + useEffect chain. Cache
  // identity preserved via factory queryKey ["admin", "users", filters] +
  // ["admin", "groups"]. Mutation paths invalidate via invalidateAllAdminUsers.
  const { data: users = [] } = useAdminUsersQuery(debouncedFilters)
  const { data: groups = [] } = useAdminGroupsQuery()
  const { user: userContext } = useAuth()
  const actingUserId = userContext?.id
  const { t } = useTranslation("admin")
  const [userToDelete, setUserToDelete] = useState<string | null>(null)
  const [deletingMutationScope, setDeletingMutationScope] = useState<MutationScope | null>(null)
  const [mutationErrors, setMutationErrors] = useState<Map<MutationScope, true>>(() => new Map())
  const latestMutationRequestIds = useRef(new Map<MutationScope, number>())
  const nextMutationRequestId = useRef(0)
  const isDeleting =
    userToDelete !== null && deletingMutationScope === deleteMutationScope(userToDelete)

  useEffect(() => {
    latestMutationRequestIds.current.clear()
    setMutationErrors(new Map())
    setUserToDelete(null)
    setDeletingMutationScope(null)
  }, [actingUserId])

  const clearMutationError = useCallback(() => setMutationErrors(new Map()), [])
  const clearMutationErrorFor = useCallback((scope: MutationScope) => {
    setMutationErrors((currentErrors) => {
      if (!currentErrors.has(scope)) return currentErrors
      const nextErrors = new Map(currentErrors)
      nextErrors.delete(scope)
      return nextErrors
    })
  }, [])
  const beginMutation = useCallback(
    (scope: MutationScope) => {
      const requestId = nextMutationRequestId.current + 1
      nextMutationRequestId.current = requestId
      latestMutationRequestIds.current.set(scope, requestId)
      clearMutationErrorFor(scope)
      return requestId
    },
    [clearMutationErrorFor]
  )
  const reportMutationError = useCallback((scope: MutationScope, requestId: number) => {
    if (requestId !== latestMutationRequestIds.current.get(scope)) return
    setMutationErrors((currentErrors) => {
      const nextErrors = new Map(currentErrors)
      nextErrors.set(scope, true)
      return nextErrors
    })
  }, [])

  const roleOptions: Record<UserRole, string> = useMemo(
    () => ({
      student: t("users.roles.student"),
      teacher: t("users.roles.teacher"),
      admin: t("users.roles.admin"),
    }),
    [t]
  )

  const handleGroupChange = useCallback(
    async (userId: string, groupId: string) => {
      const scope = groupMutationScope(userId)
      const requestId = beginMutation(scope)
      const nextGroup = groupId || null
      try {
        await api.patch(`/users/${userId}`, { group_id: nextGroup })
        void invalidateAllAdminUsers(queryClient)
      } catch {
        reportMutationError(scope, requestId)
      }
    },
    [beginMutation, queryClient, reportMutationError]
  )

  const handleDelete = useCallback((userId: string) => {
    setUserToDelete(userId)
  }, [])

  const executeDelete = useCallback(
    async (userId: string) => {
      const scope = deleteMutationScope(userId)
      const requestId = beginMutation(scope)
      setDeletingMutationScope(scope)
      try {
        await api.delete(`/users/${userId}`)
        if (latestMutationRequestIds.current.get(scope) !== requestId) return
        void invalidateAllAdminUsers(queryClient)
        setUserToDelete((currentUserId) => (currentUserId === userId ? null : currentUserId))
      } catch {
        reportMutationError(scope, requestId)
      } finally {
        if (latestMutationRequestIds.current.get(scope) === requestId) {
          setDeletingMutationScope((currentScope) => (currentScope === scope ? null : currentScope))
        }
      }
    },
    [beginMutation, queryClient, reportMutationError]
  )

  const handleFilterChange = useCallback(
    (field: keyof UserFilters) => (event: React.ChangeEvent<HTMLInputElement>) => {
      setFilters((previousFilters) => ({ ...previousFilters, [field]: event.target.value }))
    },
    []
  )

  const handleRoleChange = (value: UserRole) => {
    setFilters((previousFilters) => ({ ...previousFilters, role: value }))
  }

  const handleGroupFilterChange = (value: string) => {
    setFilters((previousFilters) => ({ ...previousFilters, group_id: value }))
  }

  const columns = useMemo<DataTableColumnDef<AdminUser>[]>(
    () => [
      {
        accessorKey: "avatar_url",
        header: t("users.table.avatar"),
        cell: ({ row }) => (
          <Avatar
            src={buildAvatarUrl(row.original.avatar_url, row.original.id)}
            alt={row.original.full_name}
            className="h-10 w-10"
          />
        ),
      },
      {
        accessorKey: "full_name",
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title={t("users.table.fullName")} />
        ),
        cell: ({ row }) => (
          <div className="font-medium text-text-primary">{row.getValue("full_name")}</div>
        ),
      },
      {
        accessorKey: "email",
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title={t("users.table.email")} />
        ),
        cell: ({ row }) => <div className="text-text-secondary">{row.getValue("email")}</div>,
      },
      {
        accessorKey: "role",
        header: t("users.table.role"),
        cell: ({ row }) => (
          <span className="inline-flex rounded-full bg-brand/[calc(var(--opacity-subtle)*100%)] px-2.5 py-0.5 text-xs font-bold text-brand ring-1 ring-inset ring-brand/[calc(var(--opacity-dim)*100%)]">
            {roleOptions[row.original.role]}
          </span>
        ),
      },
      {
        accessorKey: "group_id",
        header: t("users.table.group"),
        cell: ({ row }) => {
          const user = row.original
          if (user.role === "teacher" || user.role === "admin") return null

          return (
            <select
              value={user.group_id ? String(user.group_id) : ""}
              onChange={(event) => void handleGroupChange(user.id, event.target.value)}
              className={cn(
                "rounded-lg border border-glass-border bg-surface/[calc(var(--opacity-medium)*100%)] px-2.5 py-1 text-xs text-text-primary shadow-sm outline-none transition-all",
                "focus:border-brand/[calc(var(--opacity-medium)*100%)] focus:ring-2 focus:ring-brand/[calc(var(--opacity-subtle)*100%)]"
              )}
            >
              <option value="">-</option>
              {groups.map((group) => (
                <option value={String(group.id)} key={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
          )
        },
      },
      {
        id: "actions",
        header: t("users.table.actions"),
        cell: ({ row }) => {
          if (row.original.id === userContext?.id) return null
          return (
            <div className="text-right">
              <button
                type="button"
                onClick={() => void handleDelete(row.original.id)}
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-error transition-colors hover:bg-error/[calc(var(--opacity-subtle)*100%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-offset-2"
                aria-label={t("users.table.deleteUser")}
                title={t("users.table.deleteUser")}
              >
                <Trash2 className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          )
        },
      },
    ],
    [t, roleOptions, groups, handleGroupChange, handleDelete, userContext?.id]
  )

  return (
    <>
      <div className="min-h-screen w-full bg-background/[calc(var(--opacity-medium)*100%)] py-8">
        <div className="mx-auto max-w-(--layout-max-wide) px-4 sm:px-6 lg:px-8">
          <div className="mb-8 flex flex-col gap-6">
            <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
              {t("users.title")}
            </h1>

            <SectionCard className="flex flex-wrap items-end gap-4 p-6">
              <TextField
                id="full-name-filter"
                label={t("users.filters.fullName")}
                value={filters.full_name}
                onChange={handleFilterChange("full_name")}
                className="min-w-(--min-w-sidebar) flex-1"
              />
              <div className="flex flex-col gap-1.5 min-w-(--min-w-field) flex-1">
                <label
                  htmlFor="group-filter"
                  className="text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                >
                  {t("users.filters.group")}
                </label>
                <select
                  id="group-filter"
                  value={filters.group_id}
                  onChange={(e) => handleGroupFilterChange(e.target.value)}
                  className={cn(
                    "h-11 rounded-sm border border-glass-border bg-surface/[calc(var(--opacity-medium)*100%)] px-3 py-2 text-sm text-text-primary shadow-sm outline-none transition-all",
                    "focus:border-brand/[calc(var(--opacity-medium)*100%)] focus:ring-2 focus:ring-brand/[calc(var(--opacity-subtle)*100%)]"
                  )}
                >
                  <option value="">{t("users.filters.all")}</option>
                  {groups.map((group) => (
                    <option value={String(group.id)} key={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5 min-w-(--min-w-field) flex-1">
                <label
                  htmlFor="role-filter"
                  className="text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                >
                  {t("users.filters.role")}
                </label>
                <select
                  id="role-filter"
                  value={filters.role}
                  onChange={(e) => handleRoleChange(e.target.value as UserRole)}
                  className={cn(
                    "h-11 rounded-sm border border-glass-border bg-surface/[calc(var(--opacity-medium)*100%)] px-3 py-2 text-sm text-text-primary shadow-sm outline-none transition-all",
                    "focus:border-brand/[calc(var(--opacity-medium)*100%)] focus:ring-2 focus:ring-brand/[calc(var(--opacity-subtle)*100%)]"
                  )}
                >
                  <option value="">{t("users.filters.all")}</option>
                  <option value="student">{roleOptions.student}</option>
                  <option value="teacher">{roleOptions.teacher}</option>
                  <option value="admin">{roleOptions.admin}</option>
                </select>
              </div>
            </SectionCard>
          </div>

          {/* Desktop Table - Hidden on mobile, valid since we have cards for mobile */}
          <div className="hidden md:block">
            <DataTable columns={columns} data={users} />
          </div>

          {/* Mobile Cards */}
          <div className="grid grid-cols-1 gap-4 md:hidden">
            {users.map((user) => (
              <SectionCard key={user.id} className="relative flex-row items-center gap-4 p-4">
                <Avatar
                  src={buildAvatarUrl(user.avatar_url, user.id)}
                  alt={user.full_name}
                  className="h-14 w-14"
                />
                <div className="flex flex-1 flex-col min-w-0">
                  <h3 className="truncate text-base font-bold text-text-primary">
                    {user.full_name}
                  </h3>
                  <p className="truncate text-sm text-(--text-secondary)">{user.email}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="rounded-full bg-brand/[calc(var(--opacity-subtle)*100%)] px-2 py-0.5 text-(--fs-badge) font-bold text-brand ring-1 ring-inset ring-brand/[calc(var(--opacity-dim)*100%)]">
                      {roleOptions[user.role]}
                    </span>
                    {user.role !== "teacher" && user.role !== "admin" && (
                      <select
                        value={user.group_id ? String(user.group_id) : ""}
                        onChange={(event) => void handleGroupChange(user.id, event.target.value)}
                        className={cn(
                          "rounded-lg border border-glass-border bg-(--bg-surface)/[calc(var(--opacity-medium)*100%)] px-2 py-0.5 text-badge text-text-primary shadow-sm outline-none transition-all",
                          "focus:border-brand/[calc(var(--opacity-medium)*100%)] focus:ring-2 focus:ring-brand/[calc(var(--opacity-subtle)*100%)]"
                        )}
                      >
                        <option value="">-</option>
                        {groups.map((group) => (
                          <option value={String(group.id)} key={group.id}>
                            {group.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
                {user.id !== userContext?.id && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(user.id)}
                    className="absolute top-4 right-4 rounded-lg p-1.5 min-h-[44px] min-w-[44px] flex items-center justify-center text-error transition-colors hover:bg-error/[calc(var(--opacity-subtle)*100%)]"
                    aria-label={t("users.table.deleteUser")}
                    title={t("users.table.deleteUser")}
                  >
                    <Trash2 className="h-5 w-5" aria-hidden="true" />
                  </button>
                )}
              </SectionCard>
            ))}
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={userToDelete !== null}
        title={t("users.confirmDelete")}
        message={t("users.confirmDeleteDescription")}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => void executeDelete(userToDelete!)}
        onCancel={() => setUserToDelete(null)}
        isLoading={isDeleting}
      />
      <Snackbar
        open={mutationErrors.size > 0}
        onClose={clearMutationError}
        autoHideDuration={5000}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error">
          <span className="flex items-center justify-between gap-3">
            <span>{t("common:errors.generic")}</span>
            <button
              type="button"
              onClick={clearMutationError}
              className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg transition-colors hover:bg-black/[calc(var(--opacity-faint)*100%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-offset-2"
              aria-label={t("common:buttons.close")}
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </span>
        </Alert>
      </Snackbar>
    </>
  )
}
