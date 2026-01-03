import { useCallback, useEffect, useState } from "react"
import api from "../api/client"
import Layout from "../components/Layout"
import {
  Box,
  Typography,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TableContainer,
  Stack,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  TablePagination,
  Chip,
  Tooltip,
  IconButton,
  Collapse,
} from "@mui/material"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import { AuditLog, AuditLogList } from "../types/Admin"
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser"
import GppBadIcon from "@mui/icons-material/GppBad"
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown"
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import dayjs from "dayjs"

function Row({ log }: { log: AuditLog }) {
  const [open, setOpen] = useState(false)

  const getActionColor = (action: string) => {
    if (action.includes("delete")) return "error"
    if (action.includes("create") || action.includes("add")) return "success"
    if (action.includes("update") || action.includes("modify")) return "warning"
    return "default"
  }

  return (
    <>
      <TableRow
        hover
        sx={{
          "& > *": { borderBottom: "unset" },
          bgcolor: log.is_valid ? "transparent" : "rgba(239, 68, 68, 0.05)"
        }}
      >
        <TableCell width={50}>
          <IconButton size="small" onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell>
          <Typography variant="body2" fontWeight={600}>
            {dayjs(log.created_at).format("MMM D, HH:mm:ss")}
          </Typography>
        </TableCell>
        <TableCell>
          <Stack spacing={0.5}>
            <Typography variant="body2" fontWeight={700}>
              {log.actor_name || "System"}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              ID: {log.actor_user_id || "N/A"}
            </Typography>
          </Stack>
        </TableCell>
        <TableCell>
          <Chip
            label={log.action.replace(/\./g, " ").toUpperCase()}
            size="small"
            color={getActionColor(log.action) as any}
            sx={{ fontWeight: 700, borderRadius: 1.5, fontSize: "0.65rem" }}
          />
        </TableCell>
        <TableCell>
          <Typography variant="body2" color="text.secondary">
            {log.resource_type}
          </Typography>
        </TableCell>
        <TableCell align="center">
          {log.is_valid ? (
            <Tooltip title="Cryptographic Integrity Verified">
              <VerifiedUserIcon color="success" fontSize="small" />
            </Tooltip>
          ) : (
            <Tooltip title="TAMPERED OR INVALID SIGNATURE">
              <GppBadIcon color="error" fontSize="small" />
            </Tooltip>
          )}
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={6}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 2, p: 2, bgcolor: "rgba(0,0,0,0.02)", borderRadius: 2, border: "1px solid var(--glass-border)" }}>
              <Typography variant="subtitle2" gutterBottom component="div" fontWeight={700}>
                Details
              </Typography>
              <Stack spacing={1}>
                <Box display="flex" gap={2}>
                  <Typography variant="caption" fontWeight={700}>Resource ID:</Typography>
                  <Typography variant="caption">{log.resource_id || "N/A"}</Typography>
                </Box>
                <Box display="flex" gap={2}>
                  <Typography variant="caption" fontWeight={700}>Subject:</Typography>
                  <Typography variant="caption">{log.subject_name || "N/A"} ({log.subject_user_id || "N/A"})</Typography>
                </Box>
                <Box display="flex" gap={2}>
                  <Typography variant="caption" fontWeight={700}>IP Address:</Typography>
                  <Typography variant="caption">{log.ip_address || "Unknown"}</Typography>
                </Box>
                <Box display="flex" gap={2}>
                  <Typography variant="caption" fontWeight={700}>User Agent:</Typography>
                  <Typography variant="caption" sx={{ wordBreak: "break-all" }}>{log.user_agent || "N/A"}</Typography>
                </Box>
                {log.context && Object.keys(log.context).length > 0 && (
                  <Box>
                    <Typography variant="caption" fontWeight={700}>Context:</Typography>
                    <Paper
                      variant="outlined"
                      sx={{
                        mt: 1,
                        p: 1,
                        bgcolor: "var(--initial-bg)",
                        color: "#fff",
                        fontFamily: "monospace",
                        fontSize: "0.75rem",
                        maxHeight: 200,
                        overflow: "auto"
                      }}
                    >
                      <pre>{JSON.stringify(log.context, null, 2)}</pre>
                    </Paper>
                  </Box>
                )}
              </Stack>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  )
}

export default function AdminAudit() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)
  const [filters, setFilters] = useState({ resource_type: "", action: "" })

  const { t } = useTranslation("admin")

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      }
      if (filters.resource_type) params.resource_type = filters.resource_type
      if (filters.action) params.action = filters.action

      const res = await api.get<AuditLogList>("/admin/audit", { params })
      setLogs(res.data.items)
      setTotal(res.data.total)
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, filters])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  const handleChangePage = (event: unknown,控制: number) => {
    setPage(控制)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10))
    setPage(0)
  }

  return (
    <Layout>
      <Box
        sx={{
          width: "100%",
          minHeight: "100vh",
          bgcolor: "var(--page-bg)",
          color: "var(--page-text)",
          py: 4,
          px: { xs: 2, sm: 4, md: 6 },
        }}
      >
        <Box maxWidth={1400} mx="auto">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Typography
              variant="h4"
              fontWeight={800}
              mb={4}
              sx={{
                background: "linear-gradient(45deg, #fbbf24, #f59e0b)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                letterSpacing: "-0.02em"
              }}
            >
              {t("audit.title", "Secure Audit Logs")}
            </Typography>
          </motion.div>

          {/* Filters */}
          <Paper
            sx={{
                p: 2, mb: 3,
                borderRadius: 3,
                display: "flex",
                gap: 2,
                flexWrap: "wrap",
                bgcolor: "var(--surface-accent)",
                border: "1px solid var(--glass-border)"
            }}
          >
             <TextField
              label="Resource Type"
              variant="outlined"
              size="small"
              value={filters.resource_type}
              onChange={(e) => setFilters(f => ({ ...f, resource_type: e.target.value }))}
              sx={{ minWidth: 200 }}
            />
            <TextField
              label="Action"
              variant="outlined"
              size="small"
              value={filters.action}
              onChange={(e) => setFilters(f => ({ ...f, action: e.target.value }))}
              sx={{ minWidth: 200 }}
            />
          </Paper>

          <TableContainer
            component={Paper}
            sx={{
              borderRadius: 4,
              overflow: "hidden",
              border: "1px solid var(--glass-border)",
              bgcolor: "var(--surface-accent)",
              backdropFilter: "blur(12px)",
              boxShadow: "0 8px 32px 0 rgba(0, 0, 0, 0.1)",
            }}
          >
            {loading && logs.length === 0 ? (
                <Box display="flex" justifyContent="center" p={10}>
                    <CircularProgress color="inherit" />
                </Box>
            ) : (
                <>
                <Table>
                <TableHead>
                    <TableRow sx={{ bgcolor: "rgba(0,0,0,0.05)" }}>
                    <TableCell />
                    <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>Time</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>Actor</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>Action</TableCell>
                    <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>Target</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700, color: "var(--page-text)" }}>Integrity</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    <AnimatePresence mode="popLayout">
                    {logs.map((log) => (
                        <Row key={log.id} log={log} />
                    ))}
                    </AnimatePresence>
                </TableBody>
                </Table>
                <TablePagination
                    rowsPerPageOptions={[25, 50, 100]}
                    component="div"
                    count={total}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={handleChangePage}
                    onRowsPerPageChange={handleChangeRowsPerPage}
                    sx={{ color: "var(--page-text)" }}
                />
                </>
            )}
          </TableContainer>
        </Box>
      </Box>
    </Layout>
  )
}
