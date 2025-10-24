import { Box, CircularProgress, Skeleton, Typography } from "@mui/material"
import { visuallyHidden } from "@mui/utils"
import { useTranslation } from "react-i18next"
import Layout from "./Layout"

const HEADER_SKELETON_RADIUS = "16px"

export default function RouteGuardLoading() {
  const { t } = useTranslation("common")
  const loadingLabel = t("statuses.loading")

  return (
    <Layout>
      <Box
        component="header"
        sx={{
          px: { xs: 2, sm: 4 },
          py: { xs: 3, sm: 4 },
          borderBottom: 1,
          borderColor: "divider",
        }}
      >
        <Typography component="h1" variant="h5" sx={{ ...visuallyHidden }}>
          {loadingLabel}
        </Typography>
        <Skeleton
          aria-hidden="true"
          variant="rounded"
          sx={{
            width: { xs: "62%", sm: "44%" },
            maxWidth: 320,
            height: { xs: 32, sm: 36 },
            borderRadius: HEADER_SKELETON_RADIUS,
          }}
        />
      </Box>
      <Box
        component="section"
        role="status"
        aria-live="polite"
        aria-busy="true"
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 2,
          px: { xs: 2, sm: 4 },
          py: { xs: 10, md: 12 },
          minHeight: "min(60dvh, 520px)",
          textAlign: "center",
        }}
      >
        <CircularProgress aria-hidden="true" size={36} />
        <Typography component="p" variant="body1">
          {loadingLabel}
        </Typography>
      </Box>
    </Layout>
  )
}
