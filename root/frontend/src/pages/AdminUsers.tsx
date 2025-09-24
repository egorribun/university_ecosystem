import { useCallback, useEffect, useState } from "react"
import api from "../api/axios"
import Layout from "../components/Layout"
import {
  Box, Typography, Avatar, Select, MenuItem, TextField, InputLabel, FormControl,
  IconButton, Paper, Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Stack,
  type SelectChangeEvent,
} from "@mui/material"
import DeleteIcon from "@mui/icons-material/Delete"
import { useAuth } from "../contexts/AuthContext"
import useMediaQuery from "@mui/material/useMediaQuery"

const backendBaseUrl = "http://localhost:8000"

type UserRole = "student" | "teacher" | "admin"

type AdminUser = {
  id: number
  full_name: string
  email: string
  role: UserRole
  group_id: number | null
  avatar_url?: string | null
}

type Group = { id: number; name: string }

type UserFilters = {
  full_name: string
  group_id: string
  role: "" | UserRole
}

function getAvatar(url: string | null | undefined, id: number) {
  if (!url) return ""
  if (url.startsWith("http")) return url
  return backendBaseUrl + url + "?uid=" + id
}

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [filters, setFilters] = useState<UserFilters>({ full_name: "", group_id: "", role: "" })
  const { user: userContext } = useAuth()
  const isMobile = useMediaQuery("(max-width:1200px)")

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

  const handleGroupChange = async (userId: number, groupId: string) => {
    const nextGroup = groupId ? Number(groupId) : null
    await api.patch(`/users/${userId}`, { group_id: nextGroup })
    void fetchUsers()
  }

  const handleDelete = async (userId: number) => {
    if (!window.confirm("Удалить пользователя?")) return
    await api.delete(`/users/${userId}`)
    void fetchUsers()
  }

  const handleFilterChange = (field: keyof UserFilters) => (value: string) => {
    setFilters(prev => ({ ...prev, [field]: value }))
  }

  const handleRoleChange = (event: SelectChangeEvent<string>) => {
    const value = event.target.value as UserFilters["role"]
    setFilters(prev => ({ ...prev, role: value }))
  }

  const handleGroupFilterChange = (event: SelectChangeEvent<string>) => {
    setFilters(prev => ({ ...prev, group_id: event.target.value }))
  }

  const handleGroupSelectChange = (userId: number) => (event: SelectChangeEvent<string>) => {
    void handleGroupChange(userId, event.target.value)
  }

  return (
    <Layout>
      <Box
        sx={{
          width: "100vw",
          minHeight: "100vh",
          bgcolor: "var(--page-bg)",
          color: "var(--page-text)",
          py: { xs: 3.5, sm: 3.5, md: 3.5, lg: 3.5 }
        }}
      >
        <Box
          sx={{
            ml: { xs: 2, sm: 4, md: 5, lg: 8 },
            mr: { xs: 2, sm: 4, md: 5, lg: 8 },
            maxWidth: 1200,
            mx: "auto"
          }}
        >
          <Typography
            variant="h4"
            fontWeight={700}
            mb={3}
            color="primary.main"
            sx={{
              textAlign: "left",
              fontSize: "clamp(0.8rem, 5vw, 2.7rem)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis"
            }}
          >
            Пользователи
          </Typography>
          <Box mb={2} display="flex" gap={2} flexWrap="wrap">
            <TextField
              label="ФИО"
              value={filters.full_name}
              onChange={e => handleFilterChange("full_name")(e.target.value)}
              sx={{ minWidth: 220 }}
            />
            <FormControl sx={{ minWidth: 150 }}>
              <InputLabel>Группа</InputLabel>
              <Select value={filters.group_id} onChange={handleGroupFilterChange}>
                <MenuItem value="">Все</MenuItem>
                {groups.map(g => (
                  <MenuItem value={String(g.id)} key={g.id}>
                    {g.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 150 }}>
              <InputLabel>Роль</InputLabel>
              <Select value={filters.role} onChange={handleRoleChange}>
                <MenuItem value="">Все</MenuItem>
                <MenuItem value="student">Студент</MenuItem>
                <MenuItem value="teacher">Преподаватель</MenuItem>
                <MenuItem value="admin">Админ</MenuItem>
              </Select>
            </FormControl>
          </Box>

          {isMobile ? (
            <Stack spacing={2}>
              {users.map(user => (
                <Paper
                  key={user.id}
                  elevation={3}
                  sx={{
                    borderRadius: 3,
                    p: 2,
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                    position: "relative"
                  }}
                >
                  <Avatar src={getAvatar(user.avatar_url, user.id)} sx={{ width: 44, height: 44 }} />
                  <Box flex={1}>
                    <Typography fontWeight={600} fontSize={17} noWrap>
                      {user.full_name}
                    </Typography>
                    <Typography fontSize={15} color="text.secondary" noWrap>
                      {user.email}
                    </Typography>
                    <Stack direction="row" spacing={1} alignItems="center" mt={0.4}>
                      <Typography fontSize={14} sx={{ bgcolor: "#e3f1fd", color: "#1565c0", borderRadius: 1, px: 1.2, py: 0.2 }}>
                        {user.role}
                      </Typography>
                      {user.role !== "teacher" && user.role !== "admin" && (
                        <FormControl size="small" sx={{ minWidth: 60 }}>
                          <Select
                            value={user.group_id ? String(user.group_id) : ""}
                            onChange={handleGroupSelectChange(user.id)}
                            sx={{ fontSize: 14, height: 28 }}
                          >
                            <MenuItem value="">-</MenuItem>
                            {groups.map(g => (
                              <MenuItem value={String(g.id)} key={g.id}>
                                {g.name}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      )}
                    </Stack>
                  </Box>
                  {user.id !== (userContext?.id ?? null) && (
                    <IconButton color="error" onClick={() => handleDelete(user.id)} sx={{ position: "absolute", top: 8, right: 8 }}>
                      <DeleteIcon />
                    </IconButton>
                  )}
                </Paper>
              ))}
            </Stack>
          ) : (
            <TableContainer
              component={Paper}
              sx={{
                borderRadius: { xs: 2, md: 4 },
                boxShadow: 5,
                bgcolor: "var(--card-bg)",
                color: "var(--page-text)",
                overflowX: "auto",
                width: "100%",
                minWidth: 0,
                mt: 1
              }}
            >
              <Table stickyHeader sx={{ minWidth: 700, width: "100%" }}>
                <TableHead>
                  <TableRow>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>Аватар</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>ФИО</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>Email</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>Роль</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>Группа</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>Действия</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {users.map(user => (
                    <TableRow key={user.id}>
                      <TableCell align="center">
                        <Avatar src={getAvatar(user.avatar_url, user.id)} />
                      </TableCell>
                      <TableCell align="center">{user.full_name}</TableCell>
                      <TableCell align="center">{user.email}</TableCell>
                      <TableCell align="center">{user.role}</TableCell>
                      <TableCell align="center">
                        {user.role !== "teacher" && user.role !== "admin" ? (
                          <Select
                            value={user.group_id ? String(user.group_id) : ""}
                            onChange={handleGroupSelectChange(user.id)}
                            sx={{ minWidth: 65 }}
                          >
                            <MenuItem value="">-</MenuItem>
                            {groups.map(g => (
                              <MenuItem value={String(g.id)} key={g.id}>
                                {g.name}
                              </MenuItem>
                            ))}
                          </Select>
                        ) : (
                          ""
                        )}
                      </TableCell>
                      <TableCell align="center">
                        {user.id !== (userContext?.id ?? null) && (
                          <IconButton color="error" onClick={() => handleDelete(user.id)}>
                            <DeleteIcon />
                          </IconButton>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </Box>
    </Layout>
  )
}