import { Suspense, lazy } from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import { Box, Paper, Skeleton, Stack } from "@mui/material"
import useMediaQuery from "@mui/material/useMediaQuery"
import { alpha, useTheme } from "@mui/material/styles"
import "../assets/themes.css"

const MapContent = lazy(() => import("./MapContent"))

function MapSkeleton() {
  const theme = useTheme()
  const isMobile = useMediaQuery("(max-width:900px)")
  const iconSize = isMobile ? 26 : 34

  return (
    <Paper
      sx={{
        width: "100%",
        borderRadius: 0,
        boxShadow: 5,
        bgcolor: "var(--card-bg,#fff)",
        color: "var(--page-text,#222)",
        p: 0,
      }}
    >
      <Box
        className="map-page"
        sx={{
          background: theme.palette.mode === "dark" ? "#0b0d12" : "#f6f7fb",
          position: "relative",
        }}
      >
        <Box className="glass glass--panel glass--sheen map-head">
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Skeleton variant="circular" width={iconSize} height={iconSize} />
              <Skeleton
                variant="text"
                width={isMobile ? 160 : 240}
                sx={{ fontSize: "clamp(1.1rem, 3.6vw, 2.4rem)" }}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <Skeleton variant="circular" width={40} height={40} />
              <Skeleton variant="circular" width={40} height={40} />
            </Stack>
          </Stack>
        </Box>

        <Skeleton
          variant="rectangular"
          animation="wave"
          sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 10 }}
        />

        <Box
          sx={{
            position: "absolute",
            inset: 0,
            zIndex: 20,
            display: "grid",
            placeItems: "center",
            background: `linear-gradient(120deg, ${alpha(theme.palette.background.paper, 0.92)}, ${alpha(
              theme.palette.background.paper,
              0.84
            )})`,
          }}
        >
          <Skeleton variant="circular" width={72} height={72} />
        </Box>

        <Box className="map-controls-shield" />

        <Stack
          spacing={1}
          className="map-controls-glass safe-bottom"
          sx={{ pointerEvents: "none" }}
        >
          <Stack direction="row" spacing={1} sx={{ pointerEvents: "auto" }}>
            <Box className="glass glass--panel" sx={{ px: 1.5, py: 1 }}>
              <Skeleton variant="rounded" width={isMobile ? 148 : 220} height={32} />
            </Box>
            <Skeleton variant="circular" width={40} height={40} />
          </Stack>
        </Stack>
      </Box>
    </Paper>
  )
}

export default function MapPage() {
  return (
    <Layout>
      <PageFadeIn>
        <Suspense fallback={<MapSkeleton />}>
          <MapContent />
        </Suspense>
      </PageFadeIn>
    </Layout>
  )
}
