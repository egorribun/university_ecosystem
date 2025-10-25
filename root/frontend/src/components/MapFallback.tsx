import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Box, Button, Chip, Stack, Typography } from "@mui/material"
import { alpha, useTheme } from "@mui/material/styles"
import { useTranslation } from "react-i18next"

type MapFallbackReason = "load-error" | "preferences"

interface MapFallbackProps {
  reason: MapFallbackReason
  onRetry?: () => void
}

type CampusPointConfig = {
  key:
    | "main"
    | "library"
    | "sports"
    | "dormitory"
    | "cafeteria"
  tags: (
    | "services"
    | "study"
    | "events"
    | "sports"
    | "housing"
    | "food"
  )[]
}

const CAMPUS_POINTS: CampusPointConfig[] = [
  { key: "main", tags: ["services", "events"] },
  { key: "library", tags: ["study", "services"] },
  { key: "sports", tags: ["sports", "events"] },
  { key: "dormitory", tags: ["housing", "services"] },
  { key: "cafeteria", tags: ["food", "services"] },
]

const getBackground = (themeMode: "light" | "dark") =>
  themeMode === "dark"
    ? "linear-gradient(160deg, rgba(10,12,19,0.94), rgba(12,16,24,0.88))"
    : "linear-gradient(160deg, rgba(244,246,252,0.94), rgba(255,255,255,0.88))"

export default function MapFallback({ reason, onRetry }: MapFallbackProps) {
  const theme = useTheme()
  const { t } = useTranslation("system")
  const baseId = useId()
  const instructionsId = `${baseId}-instructions`
  const titleId = `${baseId}-title`
  const listLabelId = `${baseId}-list`
  const points = useMemo(
    () =>
      CAMPUS_POINTS.map((point) => ({
        key: point.key,
        name: t(`map.fallback.points.${point.key}.title`),
        description: t(`map.fallback.points.${point.key}.description`),
        address: t(`map.fallback.points.${point.key}.address`),
        tags: point.tags.map((tag) => ({
          key: tag,
          label: t(`map.fallback.tags.${tag}`),
        })),
      })),
    [t]
  )
  const [activeIndex, setActiveIndex] = useState(0)
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])

  const focusIndex = useCallback(
    (next: number) => {
      if (next < 0 || next >= points.length) return
      const item = itemRefs.current[next]
      if (item) {
        item.focus()
        setActiveIndex(next)
      }
    },
    [points.length]
  )

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (points.length === 0) return
      switch (event.key) {
        case "ArrowDown":
        case "ArrowRight": {
          event.preventDefault()
          const next = (activeIndex + 1) % points.length
          focusIndex(next)
          break
        }
        case "ArrowUp":
        case "ArrowLeft": {
          event.preventDefault()
          const next = (activeIndex - 1 + points.length) % points.length
          focusIndex(next)
          break
        }
        case "Home": {
          event.preventDefault()
          focusIndex(0)
          break
        }
        case "End": {
          event.preventDefault()
          focusIndex(points.length - 1)
          break
        }
        default:
          break
      }
    },
    [activeIndex, focusIndex, points.length]
  )

  return (
    <Box
      role="region"
      aria-labelledby={titleId}
      sx={{
        position: "absolute",
        inset: 0,
        zIndex: 45,
        overflowY: "auto",
        background: getBackground(theme.palette.mode),
        px: { xs: 3, sm: 6 },
        py: { xs: 4, sm: 6 },
        color: theme.palette.mode === "dark" ? "#f5f7ff" : "#0b1020",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <Stack spacing={4} sx={{ width: "min(720px, 100%)" }}>
        <Stack spacing={2}>
          <Typography id={titleId} component="h2" variant="h5" fontWeight={700}>
            {t("map.fallback.title")}
          </Typography>
          <Typography component="p" variant="body1">
            {t(`map.fallback.description.${reason === "load-error" ? "load" : "preferences"}`)}
          </Typography>
          <Typography
            id={instructionsId}
            component="p"
            variant="body2"
            color={theme.palette.mode === "dark" ? "#c9d4ff" : "text.secondary"}
          >
            {t("map.fallback.instructions")}
          </Typography>
          <Typography
            component="p"
            variant="body2"
            color={theme.palette.mode === "dark" ? "#c9d4ff" : "text.secondary"}
          >
            {t("map.fallback.offlineNotice")}
          </Typography>
          {reason === "load-error" && onRetry ? (
            <Button
              variant="outlined"
              onClick={onRetry}
              sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}
            >
              {t("map.fallback.retry")}
            </Button>
          ) : null}
        </Stack>

        <Box
          role="listbox"
          aria-labelledby={listLabelId}
          aria-describedby={instructionsId}
          onKeyDown={handleKeyDown}
          sx={{ display: "flex", flexDirection: "column", gap: 2, pb: 2 }}
        >
          <Typography
            id={listLabelId}
            component="p"
            variant="subtitle2"
            sx={{ textTransform: "uppercase", letterSpacing: 1.2 }}
          >
            {t("map.fallback.listLabel")}
          </Typography>
          {points.map((point, index) => {
            const isActive = index === activeIndex
            return (
              <Box
                key={point.key}
                role="option"
                aria-selected={isActive}
                ref={(node) => {
                  itemRefs.current[index] = node
                }}
                tabIndex={isActive ? 0 : -1}
                onFocus={() => setActiveIndex(index)}
                onClick={() => focusIndex(index)}
                sx={{
                  borderRadius: 2,
                  border: `1px solid ${alpha(theme.palette.common.black, 0.08)}`,
                  backgroundColor: isActive
                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.3 : 0.12)
                    : alpha(theme.palette.common.white, theme.palette.mode === "dark" ? 0.08 : 0.4),
                  backdropFilter: "blur(8px)",
                  px: { xs: 2, sm: 3 },
                  py: { xs: 2.5, sm: 3 },
                  outline: "none",
                  transition: "background-color 160ms ease, transform 160ms ease",
                  boxShadow: isActive
                    ? theme.shadows[4]
                    : theme.palette.mode === "dark"
                      ? `0 8px 24px ${alpha("#02050d", 0.72)}`
                      : `0 8px 24px ${alpha("#1f2f4b", 0.18)}`,
                  cursor: "pointer",
                  display: "grid",
                  gap: 1,
                  textAlign: "left",
                }}
              >
                <Typography component="h3" variant="h6" fontWeight={700}>
                  {point.name}
                </Typography>
                <Typography
                  component="p"
                  variant="body2"
                  color={theme.palette.mode === "dark" ? "#dde5ff" : "text.secondary"}
                >
                  {point.address}
                </Typography>
                <Typography component="p" variant="body2">
                  {point.description}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
                  {point.tags.map((tag) => (
                    <Chip
                      key={tag.key}
                      label={tag.label}
                      size="small"
                      sx={{
                        bgcolor: alpha(
                          theme.palette.primary.main,
                          theme.palette.mode === "dark" ? 0.32 : 0.18
                        ),
                        color: theme.palette.mode === "dark" ? "#f6f8ff" : theme.palette.primary.dark,
                        fontWeight: 600,
                      }}
                    />
                  ))}
                </Stack>
              </Box>
            )
          })}
        </Box>
      </Stack>
    </Box>
  )
}
