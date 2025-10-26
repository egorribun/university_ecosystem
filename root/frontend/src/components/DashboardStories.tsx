import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useId,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react"
import SmartImage from "@/components/SmartImage"
import type { StoryItem } from "@/types/Story"
import { storyCircleSx } from "@/constants/storyCircle"
import {
  Avatar,
  Box,
  Button,
  ButtonBase,
  Dialog,
  IconButton,
  LinearProgress,
  Skeleton,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material"
import { visuallyHidden } from "@mui/utils"
import CloseRoundedIcon from "@mui/icons-material/CloseRounded"
import ArrowBackIosNewRoundedIcon from "@mui/icons-material/ArrowBackIosNewRounded"
import ArrowForwardIosRoundedIcon from "@mui/icons-material/ArrowForwardIosRounded"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"

const STORY_AUTO_ADVANCE_MS = 6500
const SKELETON_COUNT = 8

type DashboardStoriesProps = {
  stories: StoryItem[]
  loading?: boolean
  onPrefetch?: () => void
  onStoryOpen?: (story: StoryItem) => void
  maxVisibleStories?: number
}

export default function DashboardStories({
  stories,
  loading = false,
  onPrefetch,
  onStoryOpen,
  maxVisibleStories = 12,
}: DashboardStoriesProps) {
  const theme = useTheme()
  const { t } = useTranslation("dashboard")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const listLabel = t("aria.storiesList")

  const displayStories = useMemo(() => {
    const filtered = Array.isArray(stories) ? stories.filter(Boolean) : []
    return filtered.slice(0, Math.max(1, maxVisibleStories))
  }, [stories, maxVisibleStories])

  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [progress, setProgress] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const touchOrigin = useRef<{ x: number; y: number } | null>(null)
  const rafRef = useRef<number | null>(null)
  const autoStartRef = useRef<number>(0)

  useEffect(() => {
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  const closeViewer = useCallback(() => {
    setOpenIndex(null)
    setProgress(0)
  }, [])

  const goToIndex = useCallback(
    (nextIndex: number | null) => {
      if (nextIndex === null) {
        closeViewer()
        return
      }
      const next = Math.max(0, Math.min(displayStories.length - 1, nextIndex))
      setProgress(0)
      setOpenIndex(next)
      if (displayStories[next]) {
        onStoryOpen?.(displayStories[next])
      }
    },
    [closeViewer, displayStories, onStoryOpen]
  )

  const goNext = useCallback(() => {
    if (openIndex === null) return
    if (openIndex >= displayStories.length - 1) {
      closeViewer()
      return
    }
    goToIndex(openIndex + 1)
  }, [openIndex, displayStories.length, goToIndex, closeViewer])

  const goPrev = useCallback(() => {
    if (openIndex === null) return
    if (openIndex <= 0) {
      setProgress(0)
      return
    }
    goToIndex(openIndex - 1)
  }, [openIndex, goToIndex])

  useEffect(() => {
    if (openIndex === null) {
      setProgress(0)
      return
    }
    setProgress(0)
    autoStartRef.current = performance.now()
  }, [openIndex])

  useEffect(() => {
    if (openIndex === null || prefersReducedMotion || isPaused) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    const step = (timestamp: number) => {
      const elapsed = timestamp - autoStartRef.current
      const ratio = Math.min(1, elapsed / STORY_AUTO_ADVANCE_MS)
      setProgress(ratio * 100)
      if (ratio >= 1) {
        rafRef.current = null
        goNext()
        return
      }
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [openIndex, goNext, prefersReducedMotion, isPaused])

  useEffect(() => {
    if (openIndex === null) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        closeViewer()
      }
      if (event.key === "ArrowRight") {
        event.preventDefault()
        goNext()
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault()
        goPrev()
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [openIndex, closeViewer, goNext, goPrev])

  const dialogTitleId = useId()

  const progressForIndex = useCallback(
    (index: number) => {
      if (openIndex === null) return 0
      if (index < openIndex) return 100
      if (index > openIndex) return 0
      return progress
    },
    [openIndex, progress]
  )

  const renderAvatar = useCallback((story: StoryItem) => {
    if (story.cover_url) {
      return (
        <SmartImage
          srcRaw={story.cover_url}
          alt={story.title}
          style={{ width: "100%", height: "100%", borderRadius: "inherit" }}
        />
      )
    }
    const initials = story.title.slice(0, 2).toUpperCase()
    return (
      <Avatar
        sx={{
          width: "100%",
          height: "100%",
          fontWeight: 700,
          bgcolor: "transparent",
          color: "inherit",
          fontSize: "1.1rem",
        }}
      >
        {initials}
      </Avatar>
    )
  }, [])

  const openStory = useCallback(
    (story: StoryItem, index: number) => {
      autoStartRef.current = performance.now()
      setProgress(0)
      setOpenIndex(index)
      onStoryOpen?.(story)
    },
    [onStoryOpen]
  )

  const viewerStory = openIndex === null ? null : (displayStories[openIndex] ?? null)

  const linkPropsFor = useCallback((url?: string | null) => {
    if (!url) return null
    const trimmed = url.trim()
    if (!trimmed) return null
    if (trimmed.startsWith("/")) {
      return { component: Link, to: trimmed }
    }
    if (/^https?:/i.test(trimmed)) {
      return { href: trimmed, target: "_blank", rel: "noreferrer" as const }
    }
    return { href: trimmed }
  }, [])

  const storyDialogLabel = viewerStory
    ? t("stories.viewer.aria.dialog", {
        title: viewerStory.title,
        index: (openIndex ?? 0) + 1,
        total: displayStories.length,
      })
    : undefined

  const hasStories = displayStories.length > 0
  const shouldShowHeading = loading || hasStories

  const handlePointerStart = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    touchOrigin.current = { x: event.clientX, y: event.clientY }
    setIsPaused(true)
  }, [])

  const handlePointerEnd = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const origin = touchOrigin.current
      touchOrigin.current = null
      setIsPaused(false)
      if (!origin) return
      const dx = event.clientX - origin.x
      const dy = event.clientY - origin.y
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 48) {
        if (dx < 0) {
          goNext()
        } else {
          goPrev()
        }
      }
    },
    [goNext, goPrev]
  )

  return (
    <Box
      data-fade
      style={{ "--fade-delay": "120ms" } as CSSProperties}
      sx={{ mt: 3, mb: 3, display: "flex", flexDirection: "column", gap: 2 }}
      aria-busy={loading}
      onPointerEnter={onPrefetch}
      onFocusCapture={onPrefetch}
    >
      {shouldShowHeading && (
        <Typography component="h2" variant="h6" sx={{ ...visuallyHidden }}>
          {t("stories.heading")}
        </Typography>
      )}
      {loading && (
        <Stack direction="row" spacing={1.6} sx={{ flexWrap: "wrap", rowGap: 1.6, py: 0.75 }}>
          {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
            <Stack
              key={index}
              alignItems="center"
              justifyContent="center"
              sx={{ width: 92, minHeight: 112 }}
            >
              <Skeleton variant="circular" width={76} height={76} />
            </Stack>
          ))}
        </Stack>
      )}
      {!loading && hasStories && (
        <Stack
          component="ul"
          direction="row"
          spacing={1.6}
          sx={{
            listStyle: "none",
            p: 0,
            m: 0,
            overflowX: "auto",
            columnGap: 1.6,
            rowGap: 1.6,
            flexWrap: { xs: "nowrap", sm: "wrap" },
            pr: { xs: 1, sm: 0 },
            mr: { xs: -1, sm: 0 },
            scrollbarWidth: "none",
            "&::-webkit-scrollbar": {
              display: "none",
            },
          }}
          aria-label={listLabel}
        >
          {displayStories.map((story, index) => {
            const label = t("aria.storyItem", { title: story.title })
            const tooltip = story.short_text || story.title
            return (
              <Stack
                key={story.id}
                component="li"
                alignItems="center"
                justifyContent="center"
                sx={{
                  width: 92,
                  minHeight: 112,
                  flex: { xs: "0 0 auto", sm: "0 0 92px" },
                  overflow: "visible",
                  ...(index === 0
                    ? {
                        ml: { xs: 1.2, sm: 0.8 },
                      }
                    : {}),
                }}
              >
                <ButtonBase
                  focusRipple
                  onClick={() => openStory(story, index)}
                  onFocus={onPrefetch}
                  onMouseEnter={onPrefetch}
                  aria-label={label}
                  title={tooltip}
                  data-active={viewerStory?.id === story.id || undefined}
                  sx={{
                    ...storyCircleSx(),
                    cursor: "pointer",
                    outline: "none",
                    position: "relative",
                    zIndex: 1,
                    "&:hover": {
                      boxShadow:
                        "0 8px 22px rgba(37,99,235,0.26), 0 0 0 4px rgba(125,172,255,0.22)",
                      zIndex: 3,
                    },
                    "&:hover::after": {
                      opacity: 1,
                      transform: "scale(1)",
                    },
                    "&:focus-visible": {
                      outline: "none",
                      boxShadow: "0 8px 24px rgba(37,99,235,0.3), 0 0 0 4px rgba(125,172,255,0.42)",
                      zIndex: 3,
                    },
                    "&:focus-visible::after": {
                      opacity: 1,
                      transform: "scale(1)",
                    },
                    "&[data-active='true']::after": {
                      opacity: 1,
                      transform: "scale(1)",
                    },
                    "&[data-active='true']": {
                      zIndex: 3,
                    },
                  }}
                >
                  <Box
                    aria-hidden="true"
                    sx={{
                      position: "relative",
                      width: "100%",
                      height: "100%",
                      borderRadius: "50%",
                      overflow: "hidden",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {renderAvatar(story)}
                  </Box>
                </ButtonBase>
              </Stack>
            )
          })}
        </Stack>
      )}

      <Dialog
        open={openIndex !== null}
        onClose={closeViewer}
        aria-labelledby={dialogTitleId}
        aria-label={storyDialogLabel}
        keepMounted
        PaperProps={{
          sx: {
            background: "transparent",
            boxShadow: "none",
            color: "#fff",
            position: "relative",
            overflow: "visible",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            p: { xs: 2, sm: 4 },
            m: 0,
            maxWidth: "unset",
          },
        }}
        BackdropProps={{
          sx: {
            backgroundColor: "rgba(8,11,21,0.35)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
          },
        }}
      >
        <Box
          aria-hidden
          sx={{
            position: "absolute",
            inset: 0,
            zIndex: 0,
            pointerEvents: "none",
            background: "transparent",
            backdropFilter: "none",
            WebkitBackdropFilter: "none",
          }}
        />
        {viewerStory && (
          <Box
            sx={{
              position: "relative",
              zIndex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              px: { xs: 0, sm: 2 },
              py: { xs: 0, sm: 2 },
            }}
          >
            <Box
              sx={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "stretch",
                justifyContent: "center",
                width: { xs: "min(92vw, 420px)", sm: "min(96vw, 960px)" },
                maxWidth: { xs: "min(92vw, 420px)", sm: "min(96vw, 960px)" },
                maxHeight: { xs: "92vh", sm: "80vh" },
                aspectRatio: { xs: "9 / 16", sm: "16 / 9" },
                borderRadius: viewerStory.cover_url ? 0 : { xs: 3, sm: 4 },
                overflow: "hidden",
                boxShadow: viewerStory.cover_url ? "none" : "0 30px 80px rgba(0,0,0,0.55)",
                backgroundColor: viewerStory.cover_url ? "#080b15" : undefined,
                backgroundImage: viewerStory.cover_url
                  ? "none"
                  : "linear-gradient(135deg,#1d4ed8,#60a5fa)",
              }}
              onPointerDown={handlePointerStart}
              onPointerUp={handlePointerEnd}
              onPointerCancel={() => {
                touchOrigin.current = null
                setIsPaused(false)
              }}
              onPointerLeave={() => {
                touchOrigin.current = null
                setIsPaused(false)
              }}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("button,a")) {
                  return
                }
                goNext()
              }}
            >
              {viewerStory.cover_url ? (
                <>
                  <SmartImage
                    srcRaw={viewerStory.cover_url}
                    alt={viewerStory.title}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "contain",
                      objectPosition: "center",
                      backgroundColor: "#080b15",
                    }}
                  />
                </>
              ) : (
                <Box
                  sx={{
                    flex: 1,
                    display: "grid",
                    placeItems: "center",
                    background: "linear-gradient(135deg,#1d4ed8,#60a5fa)",
                  }}
                >
                  <Typography
                    sx={{
                      fontWeight: 800,
                      fontSize: "clamp(2.2rem, 12vw, 3.2rem)",
                      textTransform: "uppercase",
                    }}
                  >
                    {viewerStory.title.slice(0, 2).toUpperCase()}
                  </Typography>
                </Box>
              )}

              <Typography sx={{ ...visuallyHidden }}>{t("stories.viewer.hints.auto")}</Typography>

              {(viewerStory.title || viewerStory.short_text || viewerStory.cta_url) && (
                <Stack
                  spacing={viewerStory.cta_url ? 2 : 1}
                  sx={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    bottom: 0,
                    p: { xs: 3, sm: 4 },
                    pt: { xs: 6, sm: 7 },
                    backgroundImage: viewerStory.cover_url
                      ? "linear-gradient(180deg, rgba(8,11,21,0) 0%, rgba(8,11,21,0.65) 55%, rgba(8,11,21,0.85) 100%)"
                      : "linear-gradient(180deg, rgba(15,23,42,0) 0%, rgba(15,23,42,0.82) 60%, rgba(15,23,42,0.95) 100%)",
                    backdropFilter: viewerStory.cover_url ? "blur(12px)" : "none",
                    WebkitBackdropFilter: viewerStory.cover_url ? "blur(12px)" : "none",
                  }}
                >
                  <Typography
                    id={dialogTitleId}
                    variant="h5"
                    component="h2"
                    sx={{ fontWeight: 800, lineHeight: 1.2 }}
                  >
                    {viewerStory.title}
                  </Typography>
                  {viewerStory.short_text && (
                    <Typography component="p" sx={{ opacity: 0.95, fontSize: "1rem" }}>
                      {viewerStory.short_text}
                    </Typography>
                  )}
                  {viewerStory.cta_url && (
                    <Button
                      variant="contained"
                      color="secondary"
                      {...(linkPropsFor(viewerStory.cta_url) ?? {})}
                      sx={{
                        alignSelf: "flex-start",
                        textTransform: "none",
                        borderRadius: 999,
                        px: 3,
                      }}
                    >
                      {t("stories.viewer.openLink")}
                    </Button>
                  )}
                </Stack>
              )}

              <Stack
                direction="row"
                spacing={1}
                sx={{
                  position: "absolute",
                  top: 12,
                  left: 16,
                  right: 16,
                }}
              >
                {displayStories.map((story, index) => (
                  <LinearProgress
                    key={story.id}
                    variant="determinate"
                    aria-label={t("stories.viewer.aria.progress", {
                      index: index + 1,
                      total: displayStories.length,
                      title: story.title,
                    })}
                    value={progressForIndex(index)}
                    sx={{
                      flex: 1,
                      height: 3,
                      borderRadius: 999,
                      backgroundColor: "rgba(255,255,255,0.35)",
                      "& .MuiLinearProgress-bar": {
                        backgroundColor: "#fff",
                        transition: "transform 140ms linear",
                      },
                    }}
                  />
                ))}
              </Stack>

              <IconButton
                onClick={closeViewer}
                aria-label={t("stories.viewer.aria.close")}
                sx={{
                  position: "absolute",
                  top: 36,
                  right: 16,
                  color: "inherit",
                  backgroundColor: "rgba(8,11,21,0.55)",
                  "&:hover": { backgroundColor: "rgba(8,11,21,0.7)" },
                }}
              >
                <CloseRoundedIcon />
              </IconButton>
            </Box>

            <Box
              sx={{
                position: "absolute",
                inset: 0,
                pointerEvents: "none",
              }}
            >
              <Box
                component="span"
                sx={{
                  position: "absolute",
                  top: "50%",
                  left: { xs: 4, sm: 24 },
                  transform: "translateY(-50%)",
                  pointerEvents: "auto",
                }}
              >
                <IconButton
                  onClick={goPrev}
                  aria-label={t("stories.viewer.aria.prev")}
                  sx={{
                    color: "inherit",
                    backgroundColor: "rgba(8,11,21,0.55)",
                    "&:hover": { backgroundColor: "rgba(8,11,21,0.7)" },
                  }}
                >
                  <ArrowBackIosNewRoundedIcon />
                </IconButton>
              </Box>
              <Box
                component="span"
                sx={{
                  position: "absolute",
                  top: "50%",
                  right: { xs: 4, sm: 24 },
                  transform: "translateY(-50%)",
                  pointerEvents: "auto",
                }}
              >
                <IconButton
                  onClick={goNext}
                  aria-label={t("stories.viewer.aria.next")}
                  sx={{
                    color: "inherit",
                    backgroundColor: "rgba(8,11,21,0.55)",
                    "&:hover": { backgroundColor: "rgba(8,11,21,0.7)" },
                  }}
                >
                  <ArrowForwardIosRoundedIcon />
                </IconButton>
              </Box>
            </Box>
          </Box>
        )}
      </Dialog>
    </Box>
  )
}
