import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import api from "../api/client"
import Layout from "../components/Layout"
import { useAuth } from "../contexts/AuthContext"
import { buildAvatarUrl } from "../utils/avatar"
import { cn } from "@/utils/cn"
import {
  Button,
  TextField,
  FormControlLabel,
  SectionCard,
  Avatar,
  Divider,
} from "@/components/settings"

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
    const params: Record<string, string> = {}
    if (filters.full_name) params.full_name = filters.full_name
    if (filters.group_id) params.group_id = filters.group_id
    if (filters.role) params.role = filters.role
    const res = await api.get<AdminUser[]>("/users", { params })
    setUsers(Array.isArray(res.data) ? res.data : [])
  }, [filters])

  const fetchGroups = useCallback(async () => {
    const res = await api.get<Group[]>("/groups")
    setGroups(Array.isArray(res.data) ? res.data : [])
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
    setFilters((prev) => ({ ...prev, [field]: value }))
  }

  const handleRoleChange = (value: UserRole) => {
    setFilters((prev) => ({ ...prev, role: value }))
  }

  const handleGroupFilterChange = (value: string) => {
    setFilters((prev) => ({ ...prev, group_id: value }))
  }

  const handleGroupSelectChange = (userId: string, value: string) => {
    void handleGroupChange(userId, value)
  }

  return (
    <Layout>
      <div className="min-h-screen w-full bg-background/50 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8 flex flex-col gap-6">
            <h1 className="text-4xl font-bold tracking-tight text-primary-text sm:text-5xl">
              {t("users.title")}
            </h1>

            <SectionCard className="flex flex-wrap items-end gap-4 p-6">
              <TextField
                label={t("users.filters.fullName")}
                value={filters.full_name}
                onChange={(e) => handleFilterChange("full_name")(e.target.value)}
                className="min-w-[220px] flex-1"
              />
              <div className="flex flex-col gap-1.5 min-w-[180px] flex-1">
                <label className="text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                  {t("users.filters.group")}
                </label>
                <select
                  value={filters.group_id}
                  onChange={(e) => handleGroupFilterChange(e.target.value)}
                  className={cn(
                    "h-11 rounded-xl border border-glass-border bg-surface/50 px-3 py-2 text-sm text-primary-text shadow-sm outline-none transition-all",
                    "focus:border-brand/40 focus:ring-2 focus:ring-brand/10"
                  )}
                >
                  <option value="">{t("users.filters.all")}</option>
                  {groups.map((g) => (
                    <option value={String(g.id)} key={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5 min-w-[180px] flex-1">
                <label className="text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                  {t("users.filters.role")}
                </label>
                <select
                  value={filters.role}
                  onChange={(e) => handleRoleChange(e.target.value as UserRole)}
                  className={cn(
                    "h-11 rounded-xl border border-glass-border bg-surface/50 px-3 py-2 text-sm text-primary-text shadow-sm outline-none transition-all",
                    "focus:border-brand/40 focus:ring-2 focus:ring-brand/10"
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
          <div className="hidden overflow-hidden rounded-3xl border border-glass-border bg-surface/40 shadow-glass md:block">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-glass-border/10 bg-surface-hover/20">
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.avatar")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.fullName")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.email")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.role")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.group")}
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                      {t("users.table.actions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-glass-border/10">
                  {users.map((user) => (
                    <tr key={user.id} className="transition-colors hover:bg-surface-hover/10">
                      <td className="whitespace-nowrap px-6 py-4">
                        <Avatar
                          src={buildAvatarUrl(user.avatar_url, user.id)}
                          alt={user.full_name}
                          className="h-10 w-10"
                        />
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-primary-text">
                        {user.full_name}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-secondary-text">
                        {user.email}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        <span className="inline-flex rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-bold text-brand ring-1 ring-inset ring-brand/20">
                          {roleOptions[user.role]}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {user.role !== "teacher" && user.role !== "admin" ? (
                          <select
                            value={user.group_id ? String(user.group_id) : ""}
                            onChange={(e) => handleGroupSelectChange(user.id, e.target.value)}
                            className={cn(
                              "rounded-lg border border-glass-border bg-surface/50 px-2.5 py-1 text-xs text-primary-text shadow-sm outline-none transition-all",
                              "focus:border-brand/40 focus:ring-2 focus:ring-brand/10"
                            )}
                          >
                            <option value="">-</option>
                            {groups.map((g) => (
                              <option value={String(g.id)} key={g.id}>
                                {g.name}
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
                            className="inline-flex items-center rounded-lg p-2 text-error transition-colors hover:bg-error/10"
                            title={t("users.deleteUser")}
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
                  <h3 className="truncate text-base font-bold text-primary-text">
                    {user.full_name}
                  </h3>
                  <p className="truncate text-sm text-secondary-text">
                    {user.email}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[0.7rem] font-bold text-brand ring-1 ring-inset ring-brand/20">
                      {roleOptions[user.role]}
                    </span>
                    {user.role !== "teacher" && user.role !== "admin" && (
                      <select
                        value={user.group_id ? String(user.group_id) : ""}
                        onChange={(e) => handleGroupSelectChange(user.id, e.target.value)}
                        className={cn(
                          "rounded-lg border border-glass-border bg-surface/50 px-2 py-0.5 text-[0.7rem] text-primary-text shadow-sm outline-none transition-all",
                          "focus:border-brand/40 focus:ring-2 focus:ring-brand/10"
                        )}
                      >
                        <option value="">-</option>
                        {groups.map((g) => (
                          <option value={String(g.id)} key={g.id}>
                            {g.name}
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
                    className="absolute top-4 right-4 rounded-lg p-1.5 text-error transition-colors hover:bg-error/10"
                    title={t("users.deleteUser")}
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
