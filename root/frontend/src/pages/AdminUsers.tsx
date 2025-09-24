// @ts-nocheck
import { useEffect, useState } from "react"
import api from "../api/axios"
import Layout from "../components/Layout"
import {
  Box, Typography, Avatar, Select, MenuItem, TextField, InputLabel, FormControl,
  IconButton, Paper, Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Stack, Button
} from "@mui/material"
import DeleteIcon from "@mui/icons-material/Delete"
import { useAuth } from "../contexts/AuthContext"
import useMediaQuery from "@mui/material/useMediaQuery"

const backendBaseUrl = "http://localhost:8000"

function getAvatar(url, id) {
  if (!url) return ""
  if (url.startsWith("http")) return url
  return backendBaseUrl + url + "?uid=" + id
}

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [groups, setGroups] = useState([])
  const [filters, setFilters] = useState({ full_name: "", group_id: "", role: "" })
  const { user: userContext } = useAuth()
  const isMobile = useMediaQuery("(max-width:1200px)")

  useEffect(() => { fetchUsers() }, [filters])
  useEffect(() => { fetchGroups() }, [])

  const fetchUsers = async () => {
    const params = {}
    if (filters.full_name) params.full_name = filters.full_name
    if (filters.group_id) params.group_id = filters.group_id
    if (filters.role) params.role = filters.role
    const res = await api.get("/users", { params })
    setUsers(res.data)
  }

  const fetchGroups = async () => {
    const res = await api.get("/groups")
    setGroups(res.data)
  }

  const handleGroupChange = async (userId, groupId) => {
    await api.patch(`/users/${userId}`, { group_id: groupId })
    fetchUsers()
  }

  const handleDelete = async (userId) => {
    if (!window.confirm("Удалить пользователя?")) return
    await api.delete(`/users/${userId}`)
    fetchUsers()
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
              onChange={e => setFilters(f => ({ ...f, full_name: e.target.value }))}
              sx={{ minWidth: 220 }}
            />
            <FormControl sx={{ minWidth: 150 }}>
              <InputLabel>Группа</InputLabel>
              <Select value={filters.group_id} onChange={e => setFilters(f => ({ ...f, group_id: e.target.value }))}>
                <MenuItem value="">Все</MenuItem>
                {groups.map(g => <MenuItem value={g.id} key={g.id}>{g.name}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl sx={{ minWidth: 150 }}>
              <InputLabel>Роль</InputLabel>
              <Select value={filters.role} onChange={e => setFilters(f => ({ ...f, role: e.target.value }))}>
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
                            value={user.group_id || ""}
                            onChange={e => handleGroupChange(user.id, e.target.value)}
                            sx={{ fontSize: 14, height: 28 }}
                          >
                            <MenuItem value="">-</MenuItem>
                            {groups.map(g => <MenuItem value={g.id} key={g.id}>{g.name}</MenuItem>)}
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
                            value={user.group_id || ""}
                            onChange={e => handleGroupChange(user.id, e.target.value)}
                            sx={{ minWidth: 65 }}
                          >
                            <MenuItem value="">-</MenuItem>
                            {groups.map(g => <MenuItem value={g.id} key={g.id}>{g.name}</MenuItem>)}
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