import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import api from "../api/client"
import Layout from "../components/Layout"
import { useAuth } from "../contexts/AuthContext"
import { buildAvatarUrl } from "../utils/avatar"
import { cn } from "@/utils/cn"
import { TextField, SectionCard, Avatar } from "@/components/settings"

type UserRole = "student" | "teacher" | "admin"

type AdminUser = {
  id: string
  full_name: string
  email: string
  role: UserRole
  group_id: string | null
  avatar_url?: string | null
}

type Group = { id: string; name: string }

type UserFilters = {
  full_name: string
  group_id: string
  role: "" | UserRole
}

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [filters, setFilters] = useState<UserFilters>({ full_name: "", group_id: "", role: "" })
  const { user: userContext } = useAuth()
  const { t } = useTranslation("admin")

  const roleOptions: Record<UserRole, string> = {
    student: t("users.roles.student"),
    teacher: t("users.roles.teacher"),
    admin: t("users.roles.admin"),
  }

  const fetchUsers = useCallback(async () => {
    const queryParameters: Record<string, string> = {}
    if (filters.full_name) queryParameters.full_name = filters.full_name
    if (filters.group_id) queryParameters.group_id = filters.group_id
    if (filters.role) queryParameters.role = filters.role
    const response = await api.get<AdminUser[]>("/users", { params: queryParameters })
    setUsers(Array.isArray(response.data) ? response.data : [])
  }, [filters])

  const fetchGroups = useCallback(async () => {
    const response = await api.get<Group[]>("/groups")
    setGroups(Array.isArray(response.data) ? response.data : [])
  }, [])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  useEffect(() => {
    void fetchGroups()
  }, [fetchGroups])

  const handleGroupChange = async (userId: string, groupId: string) => {
    const nextGroup = groupId || null
    await api.patch(`/users/${userId}`, { group_id: nextGroup })
    void fetchUsers()
  }

  const handleDelete = async (userId: string) => {
    if (!window.confirm(t("users.confirmDelete"))) return
    await api.delete(`/users/${userId}`)
    void fetchUsers()
  }

  const handleFilterChange = (field: keyof UserFilters) => (value: string) => {
    setFilters((previousFilters) => ({ ...previousFilters, [field]: value }))
  }

  const handleRoleChange = (value: UserRole) => {
    setFilters((previousFilters) => ({ ...previousFilters, role: value }))
  }

  const handleGroupFilterChange = (value: string) => {
    setFilters((previousFilters) => ({ ...previousFilters, group_id: value }))
  }

  const handleGroupSelectChange = (userId: string, value: string) => {
    void handleGroupChange(userId, value)
  }

  return (
    <Layout>
      <div className="min-h-screen w-full bg-background/(--opacity-medium) py-8">
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
                onChange={(event) => handleFilterChange("full_name")(event.target.value)}
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
                  onChange={(event) => handleGroupFilterChange(event.target.value)}
                  className={cn(
                    "h-11 rounded-sm border border-glass-border bg-surface/(--opacity-medium) px-3 py-2 text-sm text-text-primary shadow-sm outline-none transition-all",
                    "focus:border-brand/(--opacity-medium) focus:ring-2 focus:ring-brand/(--opacity-subtle)"
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
                  onChange={(event) => handleRoleChange(event.target.value as UserRole)}
                  className={cn(
                    "h-11 rounded-sm border border-glass-border bg-surface/(--opacity-medium) px-3 py-2 text-sm text-text-primary shadow-sm outline-none transition-all",
                    "focus:border-brand/(--opacity-medium) focus:ring-2 focus:ring-brand/(--opacity-subtle)"
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

          {/* Desktop Table */}
          <div className="hidden overflow-hidden rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) shadow-glass md:block">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface-hover)/(--opacity-dim)">
                    <th className="px-6 py-4 text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.avatar")}
                    </th>
                    <th className="px-6 py-4 text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.fullName")}
                    </th>
                    <th className="px-6 py-4 text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.email")}
                    </th>
                    <th className="px-6 py-4 text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.role")}
                    </th>
                    <th className="px-6 py-4 text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.group")}
                    </th>
                    <th className="px-6 py-4 text-right text-(--fs-xs) font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("users.table.actions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-glass-border/(--opacity-subtle)">
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      className="transition-colors hover:bg-(--bg-surface-hover)/(--opacity-subtle)"
                    >
                      <td className="whitespace-nowrap px-6 py-4">
                        <Avatar
                          src={buildAvatarUrl(user.avatar_url, user.id)}
                          alt={user.full_name}
                          className="h-10 w-10"
                        />
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-text-primary">
                        {user.full_name}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-(--text-secondary)">
                        {user.email}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        <span className="inline-flex rounded-full bg-brand/(--opacity-subtle) px-2.5 py-0.5 text-xs font-bold text-brand ring-1 ring-inset ring-brand/(--opacity-dim)">
                          {roleOptions[user.role]}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {user.role !== "teacher" && user.role !== "admin" ? (
                          <select
                            value={user.group_id ? String(user.group_id) : ""}
                            onChange={(event) =>
                              handleGroupSelectChange(user.id, event.target.value)
                            }
                            className={cn(
                              "rounded-lg border border-glass-border bg-surface/(--opacity-medium) px-2.5 py-1 text-xs text-text-primary shadow-sm outline-none transition-all",
                              "focus:border-brand/(--opacity-medium) focus:ring-2 focus:ring-brand/(--opacity-subtle)"
                            )}
                          >
                            <option value="">-</option>
                            {groups.map((group) => (
                              <option value={String(group.id)} key={group.id}>
                                {group.name}
                              </option>
                            ))}
                          </select>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-right">
                        {user.id !== (userContext?.id ?? null) && (
                          <button
                            type="button"
                            onClick={() => handleDelete(user.id)}
                            className="inline-flex items-center rounded-lg p-2 text-error transition-colors hover:bg-error/(--opacity-subtle)"
                            aria-label={t("users.table.deleteUser")}
                            title={t("users.table.deleteUser")}
                          >
                            <Trash2 className="h-5 w-5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
                    <span className="rounded-full bg-brand/(--opacity-subtle) px-2 py-0.5 text-(--fs-badge) font-bold text-brand ring-1 ring-inset ring-brand/(--opacity-dim)">
                      {roleOptions[user.role]}
                    </span>
                    {user.role !== "teacher" && user.role !== "admin" && (
                      <select
                        value={user.group_id ? String(user.group_id) : ""}
                        onChange={(event) => handleGroupSelectChange(user.id, event.target.value)}
                        className={cn(
                          "rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) px-2 py-0.5 text-badge text-text-primary shadow-sm outline-none transition-all",
                          "focus:border-brand/(--opacity-medium) focus:ring-2 focus:ring-brand/(--opacity-subtle)"
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
                {user.id !== (userContext?.id ?? null) && (
                  <button
                    type="button"
                    onClick={() => handleDelete(user.id)}
                    className="absolute top-4 right-4 rounded-lg p-1.5 text-error transition-colors hover:bg-error/(--opacity-subtle)"
                    aria-label={t("users.table.deleteUser")}
                    title={t("users.table.deleteUser")}
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                )}
              </SectionCard>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  )
}
