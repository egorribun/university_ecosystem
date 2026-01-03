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
  Switch,
  Slider,
  Tooltip,
  Chip,
  circularProgressClasses,
  CircularProgress,
  IconButton,
} from "@mui/material"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"
import { FeatureFlag, FlagStatus } from "../types/Admin"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"

export default function AdminFeatureFlags() {
  const [flags, setFlags] = useState<FeatureFlag[]>([])
  const [loading, setLoading] = useState(true)
  const { t } = useTranslation("admin")

  const fetchFlags = useCallback(async () => {
    try {
      const res = await api.get<FeatureFlag[]>("/admin/feature-flags")
      setFlags(res.data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchFlags()
  }, [fetchFlags])

  const handleToggle = async (name: string, currentStatus: FlagStatus) => {
    const nextStatus: FlagStatus = currentStatus === "disabled" ? "enabled" : "disabled"
    await api.patch(`/admin/feature-flags/${name}`, { status: nextStatus })
    void fetchFlags()
  }

  const handlePercentageChange = async (name: string, value: number) => {
    await api.patch(`/admin/feature-flags/${name}`, {
      status: "percentage",
      percentage: value
    })
    void fetchFlags()
  }

  const getStatusColor = (status: FlagStatus) => {
    switch (status) {
      case "enabled": return "success"
      case "percentage": return "info"
      default: return "default"
    }
  }

  if (loading) {
    return (
      <Layout>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh" bgcolor="var(--page-bg)">
            <CircularProgress
                variant="indeterminate"
                disableShrink
                sx={{
                color: "var(--primary-main)",
                animationDuration: "550ms",
                [`& .${circularProgressClasses.circle}`]: {
                    strokeLinecap: "round",
                },
                }}
                size={40}
                thickness={4}
            />
        </Box>
      </Layout>
    )
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
        <Box maxWidth={1200} mx="auto">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Typography
              variant="h4"
              fontWeight={800}
              mb={4}
              sx={{
                background: "linear-gradient(45deg, var(--primary-main), #818cf8)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                letterSpacing: "-0.02em"
              }}
            >
              {t("featureFlags.title", "Dynamic Feature Flags")}
            </Typography>
          </motion.div>

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
            <Table>
              <TableHead>
                <TableRow sx={{ bgcolor: "rgba(0,0,0,0.05)" }}>
                  <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>{t("featureFlags.table.flag", "Feature Flag")}</TableCell>
                  <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>{t("featureFlags.table.status", "Status")}</TableCell>
                  <TableCell sx={{ fontWeight: 700, color: "var(--page-text)" }}>{t("featureFlags.table.rollout", "Rollout")}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700, color: "var(--page-text)" }}>{t("featureFlags.table.details", "Details")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <AnimatePresence mode="popLayout">
                  {flags.map((flag, index) => (
                    <TableRow
                      key={flag.name}
                      component={motion.tr}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05 }}
                      hover
                      sx={{
                        "&:last-child td, &:last-child th": { border: 0 },
                        transition: "background-color 0.2s"
                      }}
                    >
                      <TableCell>
                        <Stack spacing={0.5}>
                          <Typography fontWeight={700} fontSize={16} color="var(--page-text)">
                            {flag.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 300 }}>
                            {flag.description}
                          </Typography>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Chip
                            label={flag.status.toUpperCase()}
                            size="small"
                            color={getStatusColor(flag.status)}
                            sx={{ fontWeight: 700, borderRadius: 1.5, minWidth: 90 }}
                          />
                          <Switch
                            checked={flag.status !== "disabled"}
                            onChange={() => handleToggle(flag.name, flag.status)}
                            color="primary"
                            sx={{
                                "& .MuiSwitch-switchBase.Mui-checked": {
                                  color: "var(--primary-main)",
                                },
                                "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
                                  backgroundColor: "var(--primary-main)",
                                },
                            }}
                          />
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ width: 250 }}>
                        {flag.status === "percentage" ? (
                          <Box px={2}>
                            <Slider
                              value={flag.percentage}
                              onChange={(_, val) => handlePercentageChange(flag.name, val as number)}
                              valueLabelDisplay="auto"
                              step={5}
                              marks
                              min={0}
                              max={100}
                              sx={{
                                color: "var(--primary-main)",
                                "& .MuiSlider-thumb": {
                                  width: 14,
                                  height: 14,
                                  "&:hover, &.Mui-focusVisible": {
                                    boxShadow: "0 0 0 8px rgba(99, 102, 241, 0.16)",
                                  },
                                },
                              }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              {flag.percentage}% of users
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="text.disabled" fontStyle="italic">
                            Global toggle active
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip title={JSON.stringify(flag.metadata, null, 2)} arrow>
                          <IconButton size="small" sx={{ color: "text.secondary" }}>
                            <InfoOutlinedIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </AnimatePresence>
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      </Box>
    </Layout>
  )
}
