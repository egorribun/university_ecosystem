import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  useMediaQuery,
} from "@mui/material"
import { alpha, useTheme } from "@mui/material/styles"
import OpenInNewIcon from "@mui/icons-material/OpenInNew"
import MapIcon from "@mui/icons-material/Map"
import SatelliteAltIcon from "@mui/icons-material/SatelliteAlt"
import RestartAltIcon from "@mui/icons-material/RestartAlt"
import "../assets/themes.css"
import { useTranslation } from "react-i18next"
import MapFallback from "@/components/MapFallback"
import { CAMPUS_COORDINATES } from "@/constants/campus"

type LayerMode = "map" | "hybrid"

const MAP_ID = "128006a9ca6ecba0793cdcd05524ff66e1c0b5187d421dfcae39dd12345e4b57"
const Z_DEFAULT = 16
const LOAD_TIMEOUT_MS = 12000

const detectEmbedOptOut = (): boolean => {
  if (typeof window === "undefined") return false
  try {
    const navigatorWithPrivacy = window.navigator as Navigator & {
      globalPrivacyControl?: boolean
      msDoNotTrack?: string | null
    }
    if (typeof navigatorWithPrivacy.globalPrivacyControl === "boolean") {
      if (navigatorWithPrivacy.globalPrivacyControl) return true
    }
    const doNotTrack =
      navigatorWithPrivacy.doNotTrack ??
      navigatorWithPrivacy.msDoNotTrack ??
      (window as typeof window & { doNotTrack?: string }).doNotTrack
    return doNotTrack === "1" || doNotTrack === "yes"
  } catch {
    return false
  }
}

export default function MapContent() {
  const theme = useTheme()
  const isMobile = useMediaQuery("(max-width:900px)")
  const { t } = useTranslation("system")
  const [layer, setLayer] = useState<LayerMode>("map")
  const [iframeLoaded, setIframeLoaded] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [frameKey, setFrameKey] = useState(0)
  const loadSeq = useRef(0)
  const loadTimer = useRef<number | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const iframeLoadedRef = useRef(false)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const [privacyBlocksEmbeds, setPrivacyBlocksEmbeds] = useState(() => detectEmbedOptOut())
  // Используем цвета светлой темы для обеих тем (темный текст)
  const lightThemeTextPrimary = "#101621" // --page-text светлой темы
  const lightThemePrimary = "#0f4faa" // --nav-link светлой темы
  const toggleBaseColor = alpha(lightThemeTextPrimary, 0.88)
  const toggleSelectedColor = theme.palette.common.white
  // Используем одинаковый фон для обеих тем (как на светлой)
  const toggleSelectedBg = alpha(lightThemePrimary, 0.24)
  const toggleHoverColor = lightThemePrimary

  useEffect(() => {
    const qs = new URLSearchParams(location.search)
    const l = (qs.get("layer") as LayerMode) || "map"
    if (l) setLayer(l)
  }, [])

  useEffect(() => {
    const qs = new URLSearchParams()
    qs.set("layer", layer)
    const url = `${location.pathname}?${qs.toString()}`
    window.history.replaceState(null, "", url)
  }, [layer])

  const lParam = useMemo(() => {
    return layer === "map" ? "map" : "sat,skl"
  }, [layer])

  const mapSrc = useMemo(() => {
    if (layer === "map") {
      return `https://yandex.ru/map-widget/v1/?um=constructor%3A${MAP_ID}&source=constructor`
    }
    const ll = encodeURIComponent(
      `${CAMPUS_COORDINATES.lon.toFixed(6)},${CAMPUS_COORDINATES.lat.toFixed(6)}`
    )
    return `https://yandex.ru/map-widget/v1/?ll=${ll}&z=${Z_DEFAULT}&l=${encodeURIComponent(lParam)}`
  }, [layer, lParam])

  const disableEmbeds = prefersReducedMotion || privacyBlocksEmbeds
  const showFallback = loadError || disableEmbeds
  const fallbackReason = loadError ? "load-error" : disableEmbeds ? "preferences" : null

  const forceReload = useCallback(() => {
    if (disableEmbeds) return
    iframeLoadedRef.current = false
    setIframeLoaded(false)
    setLoadError(false)
    setFrameKey((k) => k + 1)
    loadSeq.current += 1
    if (loadTimer.current) window.clearTimeout(loadTimer.current)
    const seqNow = loadSeq.current
    loadTimer.current = window.setTimeout(() => {
      if (seqNow === loadSeq.current && !iframeLoadedRef.current) setLoadError(true)
    }, LOAD_TIMEOUT_MS)
  }, [disableEmbeds])

  useEffect(() => {
    if (disableEmbeds) {
      iframeLoadedRef.current = false
      setIframeLoaded(false)
      setLoadError(false)
      if (loadTimer.current) window.clearTimeout(loadTimer.current)
      return
    }
    forceReload()
    return () => {
      if (loadTimer.current) window.clearTimeout(loadTimer.current)
    }
  }, [mapSrc, disableEmbeds, forceReload])

  useEffect(() => {
    if (typeof window === "undefined") return
    const handleOptOutChange = () => {
      setPrivacyBlocksEmbeds(detectEmbedOptOut())
    }
    window.addEventListener("focus", handleOptOutChange)
    window.addEventListener("storage", handleOptOutChange)
    return () => {
      window.removeEventListener("focus", handleOptOutChange)
      window.removeEventListener("storage", handleOptOutChange)
    }
  }, [])

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
    if (layer === "map") {
      window.open(
        `https://yandex.ru/maps/?um=constructor:${MAP_ID}&source=constructor`,
        "_blank",
        "noopener,noreferrer"
      )
      return
    }
    const ll = `${CAMPUS_COORDINATES.lon.toFixed(6)},${CAMPUS_COORDINATES.lat.toFixed(6)}`
    window.open(
      `https://yandex.ru/maps/?ll=${ll}&z=${Z_DEFAULT}&l=${lParam.replace(/%2C/g, ",")}`,
      "_blank",
      "noopener,noreferrer"
    )
  }

  const reset = () => {
    if (disableEmbeds) return
    forceReload()
  }

  const tooltipCfg = isMobile
    ? { disableFocusListener: true, disableHoverListener: true, disableTouchListener: true }
    : { enterDelay: 200, enterTouchDelay: 0, leaveTouchDelay: 0, disableInteractive: true }

  return (
    <>
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
          ref={containerRef}
          className="map-page"
          sx={{ background: theme.palette.mode === "dark" ? "#0b0d12" : "#f6f7fb" }}
        >
          <Box className="glass glass--panel glass--sheen map-head">
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <MapIcon sx={{ fontSize: isMobile ? 26 : 34, color: "#0f4faa" }} />
                <Typography
                  className="map-title"
                  variant="h4"
                  fontWeight={800}
                  sx={{ letterSpacing: 0.2, fontSize: "clamp(1.1rem, 3.6vw, 2.4rem)" }}
                >
                  {t("map.title")}
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1}>
                <Tooltip title={t("map.openInYandex") ?? undefined} {...tooltipCfg}>
                  <IconButton
                    aria-label={t("map.openInYandex")}
                    className="glass glass--btn map-btn map-btn--open"
                    onClick={openInYandex}
                    sx={{ touchAction: "manipulation" }}
                  >
                    <OpenInNewIcon />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t("map.reset") ?? undefined} {...tooltipCfg}>
                  <IconButton
                    aria-label={t("map.reset")}
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

          {!disableEmbeds && (
            <iframe
              key={`${frameKey}`}
              src={mapSrc}
              title={t("map.iframeTitle")}
              width="100%"
              height="calc(100% + 35px)"
              style={{ border: 0, position: "absolute", top: "-35px", left: 0, right: 0, bottom: "-35px", display: "block" }}
              allowFullScreen
              loading="lazy"
              onLoad={() => {
                iframeLoadedRef.current = true
                setIframeLoaded(true)
                setLoadError(false)
                if (loadTimer.current) window.clearTimeout(loadTimer.current)
              }}
            />
          )}

          {(!iframeLoaded || loadError) && !disableEmbeds && (
            <Box
              sx={{
                position: "absolute",
                inset: 0,
                zIndex: 40,
                display: "grid",
                placeItems: "center",
                background: `linear-gradient(120deg, ${alpha(theme.palette.background.paper, 0.9)}, ${alpha(theme.palette.background.paper, 0.82)})`,
              }}
            >
              {!loadError ? (
                <Box
                  sx={{
                    width: 72,
                    height: 72,
                    borderRadius: "50%",
                    border: `5px solid ${alpha(theme.palette.text.primary, 0.18)}`,
                    borderTopColor: theme.palette.primary.main,
                    animation: "spin 900ms linear infinite",
                    "@keyframes spin": { to: { transform: "rotate(360deg)" } },
                  }}
                />
              ) : (
                <Stack spacing={2} alignItems="center">
                  <Typography>{t("map.loadError")}</Typography>
                  <IconButton
                    color="primary"
                    onClick={() => {
                      setLoadError(false)
                      iframeLoadedRef.current = false
                      setIframeLoaded(false)
                      setFrameKey((k) => k + 1)
                    }}
                  >
                    <RestartAltIcon />
                  </IconButton>
                </Stack>
              )}
            </Box>
          )}

          {showFallback && fallbackReason && (
            <MapFallback
              reason={fallbackReason}
              onRetry={fallbackReason === "load-error" ? forceReload : undefined}
            />
          )}

          <Box className="map-controls-shield" />

          <Stack
            spacing={1}
            className="map-controls-glass safe-bottom"
            sx={{ pointerEvents: "none" }}
          >
            <Stack direction="row" spacing={1} sx={{ pointerEvents: "auto" }}>
              <Box className="glass glass--panel">
                <ToggleButtonGroup
                  exclusive
                  value={layer}
                  onChange={(_, v: LayerMode | null) => {
                    if (v) setLayer(v)
                  }}
                  sx={{
                    "& .MuiToggleButtonGroup-grouped": { border: 0, px: 1.5, m: 0 },
                    "& .MuiToggleButton-root": {
                      borderRadius: 0,
                      touchAction: "manipulation",
                      color: toggleBaseColor,
                      transition: "color 160ms ease",
                      "& .MuiSvgIcon-root": {
                        color: "inherit",
                        transition: "color 160ms ease",
                      },
                      "&:hover": {
                        color: toggleHoverColor,
                        "& .MuiSvgIcon-root": { color: "inherit" },
                      },
                    },
                    "& .MuiToggleButton-root.Mui-selected": {
                      bgcolor: toggleSelectedBg,
                      color: toggleSelectedColor,
                      "&:hover": {
                        bgcolor: toggleSelectedBg,
                      },
                    },
                    "& .MuiToggleButton-root.Mui-selected .MuiSvgIcon-root": { color: "inherit" },
                  }}
                >
                  <ToggleButton value="map" disableRipple aria-label={t("map.layerAria.map")}>
                    <MapIcon fontSize="small" sx={{ color: "inherit" }} />
                    {!isMobile && (
                      <Box component="span" ml={1} sx={{ color: "inherit" }}>
                        {t("map.layer.map")}
                      </Box>
                    )}
                  </ToggleButton>
                  <ToggleButton value="hybrid" disableRipple aria-label={t("map.layerAria.hybrid")}>
                    <SatelliteAltIcon fontSize="small" sx={{ color: "inherit" }} />
                    {!isMobile && (
                      <Box component="span" ml={1} sx={{ color: "inherit" }}>
                        {t("map.layer.hybrid")}
                      </Box>
                    )}
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>
            </Stack>
          </Stack>
        </Box>
      </Paper>

      <Snackbar open={false}>
        <Alert severity="info" sx={{ width: "100%" }} />
      </Snackbar>
    </>
  )
}
