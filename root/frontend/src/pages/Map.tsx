import React, { useEffect, useMemo, useRef, useState } from "react"
import Layout from "../components/Layout"
import {
  Box,
  Paper,
  Stack,
  Typography,
  IconButton,
  ToggleButtonGroup,
  ToggleButton,
  Tooltip,
  Snackbar,
  Alert,
  useMediaQuery
} from "@mui/material"
import { alpha, useTheme } from "@mui/material/styles"
import OpenInNewIcon from "@mui/icons-material/OpenInNew"
import MapIcon from "@mui/icons-material/Map"
import SatelliteAltIcon from "@mui/icons-material/SatelliteAlt"
import TrafficIcon from "@mui/icons-material/Traffic"
import RestartAltIcon from "@mui/icons-material/RestartAlt"
import "../assets/themes.css"

type LayerMode = "map" | "hybrid"

const MAP_ID = "128006a9ca6ecba0793cdcd05524ff66e1c0b5187d421dfcae39dd12345e4b57"
const CAMPUS = { lat: 55.71392, lon: 37.81474 }
const Z_DEFAULT = 16
const LOAD_TIMEOUT_MS = 12000

export default function MapPage() {
  const theme = useTheme()
  const isMobile = useMediaQuery("(max-width:900px)")
  const [layer, setLayer] = useState<LayerMode>("map")
  const [traffic, setTraffic] = useState(false)
  const [iframeLoaded, setIframeLoaded] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [frameKey, setFrameKey] = useState(0)
  const loadSeq = useRef(0)
  const loadTimer = useRef<number | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const qs = new URLSearchParams(location.search)
    const l = (qs.get("layer") as LayerMode) || "map"
    const t = qs.get("traffic") === "1"
    if (l) setLayer(l)
    setTraffic(t)
  }, [])

  useEffect(() => {
    const qs = new URLSearchParams()
    qs.set("layer", layer)
    qs.set("traffic", traffic ? "1" : "0")
    const url = `${location.pathname}?${qs.toString()}`
    window.history.replaceState(null, "", url)
  }, [layer, traffic])

  const lParam = useMemo(() => {
    const base = layer === "map" ? "map" : "sat,skl"
    return traffic ? `${base},trf` : base
  }, [layer, traffic])

  const mapSrc = useMemo(() => {
    if (layer === "map" && !traffic) {
      return `https://yandex.ru/map-widget/v1/?um=constructor%3A${MAP_ID}&source=constructor`
    }
    const ll = encodeURIComponent(`${CAMPUS.lon.toFixed(6)},${CAMPUS.lat.toFixed(6)}`)
    return `https://yandex.ru/map-widget/v1/?ll=${ll}&z=${Z_DEFAULT}&l=${encodeURIComponent(lParam)}`
  }, [layer, traffic, lParam])

  const forceReload = () => {
    setIframeLoaded(false)
    setLoadError(false)
    setFrameKey(k => k + 1)
    loadSeq.current += 1
    if (loadTimer.current) window.clearTimeout(loadTimer.current)
    const seqNow = loadSeq.current
    loadTimer.current = window.setTimeout(() => {
      if (seqNow === loadSeq.current && !iframeLoaded) setLoadError(true)
    }, LOAD_TIMEOUT_MS)
  }

  useEffect(() => {
    forceReload()
    return () => {
      if (loadTimer.current) window.clearTimeout(loadTimer.current)
    }
  }, [mapSrc])

  useEffect(() => {
    const computeTop = () => {
      const nav = document.querySelector<HTMLElement>(".navbar-root")
      const h = nav ? Math.round(nav.getBoundingClientRect().height) : 0
      containerRef.current?.style.setProperty("--layout-offset-top", `${Math.max(0, h)}px`)
    }
    computeTop()
    const nav = document.querySelector<HTMLElement>(".navbar-root")
    const ro = (window as any).ResizeObserver ? new ResizeObserver(() => computeTop()) : null
    if (nav && ro) ro.observe(nav)
    window.addEventListener("resize", computeTop)
    window.addEventListener("orientationchange", computeTop)
    return () => {
      ro?.disconnect?.()
      window.removeEventListener("resize", computeTop)
      window.removeEventListener("orientationchange", computeTop)
    }
  }, [])

  const openInYandex = () => {
    if (layer === "map" && !traffic) {
      window.open(`https://yandex.ru/maps/?um=constructor:${MAP_ID}&source=constructor`, "_blank", "noopener,noreferrer")
      return
    }
    const ll = `${CAMPUS.lon.toFixed(6)},${CAMPUS.lat.toFixed(6)}`
    window.open(`https://yandex.ru/maps/?ll=${ll}&z=${Z_DEFAULT}&l=${lParam.replace(/%2C/g, ",")}`, "_blank", "noopener,noreferrer")
  }

  const reset = () => {
    setTraffic(false)
    forceReload()
  }

  const tooltipCfg = isMobile
    ? { disableFocusListener: true, disableHoverListener: true, disableTouchListener: true }
    : { enterDelay: 200, enterTouchDelay: 0, leaveTouchDelay: 0, disableInteractive: true }

  return (
    <Layout>
      <Paper sx={{ width: "100%", borderRadius: 0, boxShadow: 5, bgcolor: "var(--card-bg,#fff)", color: "var(--page-text,#222)", p: 0 }}>
        <Box ref={containerRef} className="map-page" sx={{ background: theme.palette.mode === "dark" ? "#0b0d12" : "#f6f7fb" }}>
          <Box className="glass glass--panel glass--sheen map-head">
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <MapIcon color="primary" sx={{ fontSize: isMobile ? 26 : 34 }} />
                <Typography
                  className="map-title"
                  variant="h4"
                  fontWeight={800}
                  sx={{ letterSpacing: 0.2, fontSize: "clamp(1.1rem, 3.6vw, 2.4rem)" }}
                >
                  Карта кампуса
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1}>
                <Tooltip title="Открыть в Яндекс-Картах" {...tooltipCfg}>
                  <IconButton
                    aria-label="Открыть в Яндекс-Картах"
                    className="glass glass--btn map-btn map-btn--open"
                    onClick={openInYandex}
                    sx={{ touchAction: "manipulation" }}
                  >
                    <OpenInNewIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Сбросить" {...tooltipCfg}>
                  <IconButton
                    aria-label="Сбросить"
                    className="glass glass--btn map-btn map-btn--reset"
                    onClick={reset}
                    sx={{ touchAction: "manipulation" }}
                  >
                    <RestartAltIcon />
                  </IconButton>
                </Tooltip>
              </Stack>
            </Stack>
          </Box>

          <iframe
            key={`${frameKey}`}
            src={mapSrc}
            title="Карта кампуса ГУУ"
            width="100%"
            height="100%"
            style={{ border: 0, position: "absolute", inset: 0, display: "block" }}
            allowFullScreen
            loading="lazy"
            onLoad={() => {
              setIframeLoaded(true)
              setLoadError(false)
              if (loadTimer.current) window.clearTimeout(loadTimer.current)
            }}
          />

          {(!iframeLoaded || loadError) && (
            <Box
              sx={{
                position: "absolute",
                inset: 0,
                zIndex: 40,
                display: "grid",
                placeItems: "center",
                background: `linear-gradient(120deg, ${alpha(theme.palette.background.paper, 0.9)}, ${alpha(theme.palette.background.paper, 0.82)})`
              }}
            >
              {!loadError ? (
                <Box sx={{
                  width: 72,
                  height: 72,
                  borderRadius: "50%",
                  border: `5px solid ${alpha(theme.palette.text.primary, .18)}`,
                  borderTopColor: theme.palette.primary.main,
                  animation: "spin 900ms linear infinite",
                  "@keyframes spin": { to: { transform: "rotate(360deg)" } }
                }} />
              ) : (
                <Stack spacing={2} alignItems="center">
                  <Typography>Не удалось загрузить карту</Typography>
                  <IconButton color="primary" onClick={() => { setLoadError(false); setIframeLoaded(false); setFrameKey(k => k + 1) }}>
                    <RestartAltIcon />
                  </IconButton>
                </Stack>
              )}
            </Box>
          )}

          <Box className="map-controls-shield" />

          <Stack spacing={1} className="map-controls-glass safe-bottom" sx={{ pointerEvents: "none" }}>
            <Stack direction="row" spacing={1} sx={{ pointerEvents: "auto" }}>
              <Box className="glass glass--panel">
                <ToggleButtonGroup
                  exclusive
                  value={layer}
                  onChange={(_, v: LayerMode | null) => { if (v) setLayer(v) }}
                  sx={{
                    "& .MuiToggleButtonGroup-grouped": { border: 0, px: 1.5, m: 0 },
                    "& .MuiToggleButton-root": { borderRadius: 0, touchAction: "manipulation" },
                    "& .MuiToggleButton-root.Mui-selected": { bgcolor: alpha(theme.palette.primary.main, 0.14) }
                  }}
                >
                  <ToggleButton value="map" disableRipple aria-label="Схема">
                    <MapIcon fontSize="small" />{!isMobile && <Box ml={1}>Карта</Box>}
                  </ToggleButton>
                  <ToggleButton value="hybrid" disableRipple aria-label="Спутник">
                    <SatelliteAltIcon fontSize="small" />{!isMobile && <Box ml={1}>Спутник</Box>}
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>
              <Tooltip title={traffic ? "Скрыть пробки" : "Показать пробки"} {...tooltipCfg}>
                <IconButton
                  aria-pressed={traffic}
                  aria-label="Пробки"
                  onClick={() => setTraffic(v => !v)}
                  className="glass glass--btn"
                  sx={{ touchAction: "manipulation" }}
                >
                  <TrafficIcon color={traffic ? "error" : "inherit"} />
                </IconButton>
              </Tooltip>
            </Stack>
          </Stack>
        </Box>
      </Paper>

      <Snackbar open={false}>
        <Alert severity="info" sx={{ width: "100%" }} />
      </Snackbar>
    </Layout>
  )
}