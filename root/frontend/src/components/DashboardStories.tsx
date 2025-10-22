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
  Divider,
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
import { cardHoverSx } from "@/constants/cardHover"
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
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"))

  const listLabel = t("aria.storiesList")
  const emptyLabel = t("stories.empty")
  const emptyDescription = t("stories.emptyDescription")
  const subheading = t("stories.subheading")

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
  const dialogHintsId = useId()

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
          style={{ width: "100%", height: "100%" }}
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

  const viewerInstructions = t("stories.viewer.aria.instructions")
  const autoHint = t("stories.viewer.hints.auto")
  const tapHint = t("stories.viewer.hints.tap")
  const keyboardHint = t("stories.viewer.hints.keyboard")
  const swipeHint = t("stories.viewer.hints.swipe")

  const normalizedHints = useMemo(() => {
    const hints: string[] = []
    if (autoHint && autoHint !== "stories.viewer.hints.auto") {
      hints.push(autoHint)
    }
    const navigationHint = isMobile ? swipeHint : keyboardHint
    const navigationKey = isMobile
      ? "stories.viewer.hints.swipe"
      : "stories.viewer.hints.keyboard"
    if (navigationHint && navigationHint !== navigationKey) {
      hints.push(navigationHint)
    }
    if (tapHint && tapHint !== "stories.viewer.hints.tap") {
      hints.push(tapHint)
    }
    return hints
  }, [autoHint, isMobile, keyboardHint, swipeHint, tapHint])

  const hasSubheading = subheading && subheading !== "stories.subheading"
  const hasEmptyDescription =
    emptyDescription && emptyDescription !== "stories.emptyDescription"
  const hasViewerInstructions =
    viewerInstructions && viewerInstructions !== "stories.viewer.aria.instructions"

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
      sx={{
        ...cardHoverSx({ hoverTransform: null, hoverBoxShadow: null }),
        background: "var(--card-bg)",
        borderRadius: "2rem",
        border: {
          xs: "1px solid color-mix(in srgb, var(--page-text) 12%, transparent)",
          md: "1px solid transparent",
        },
        p: { xs: 2, md: 2.5 },
        boxShadow: {
          xs: "0 16px 40px rgba(0,0,0,.22), 0 6px 16px rgba(0,0,0,.12)",
          md: "var(--shadow-1)",
        },
        backdropFilter: { xs: "saturate(110%)", md: "none" },
        mt: 3,
        mb: 3,
      }}
      aria-busy={loading}
      onPointerEnter={onPrefetch}
      onFocusCapture={onPrefetch}
    >
      <Stack spacing={0.75} sx={{ mb: 0.5 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography
            component="h2"
            sx={{ fontWeight: 800, fontSize: "clamp(1.05rem, 2vw, 1.4rem)" }}
          >
            {t("stories.heading")}
          </Typography>
          {viewerStory && viewerStory.cta_url && (
            <Button
              size="small"
              variant="contained"
              color="primary"
              {...(linkPropsFor(viewerStory.cta_url) ?? {})}
              sx={{ textTransform: "none" }}
            >
              {t("stories.viewer.openLink")}
            </Button>
          )}
        </Stack>
        {hasSubheading && (
          <Typography variant="body2" color="text.secondary">
            {subheading}
          </Typography>
        )}
      </Stack>
      <Divider sx={{ my: 1.5 }} />
      {loading && (
        <Stack direction="row" spacing={1.6} sx={{ flexWrap: "wrap", rowGap: 1.6 }}>
          {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
            <Stack key={index} spacing={0.9} alignItems="center" sx={{ width: 92 }}>
              <Skeleton variant="circular" width={76} height={76} />
              <Skeleton width={70} height={18} />
            </Stack>
          ))}
        </Stack>
      )}
      {!loading && displayStories.length === 0 && (
        <Stack spacing={0.5}>
          <Typography color="text.secondary">{emptyLabel}</Typography>
          {hasEmptyDescription && (
            <Typography color="text.secondary" variant="body2">
              {emptyDescription}
            </Typography>
          )}
        </Stack>
      )}
      {!loading && displayStories.length > 0 && (
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
                spacing={0.9}
                alignItems="center"
                sx={{ width: 92, flex: { xs: "0 0 auto", sm: "0 0 92px" } }}
              >
                <ButtonBase
                  focusRipple
                  onClick={() => openStory(story, index)}
                  onFocus={onPrefetch}
                  onMouseEnter={onPrefetch}
                  aria-label={label}
                  sx={{
                    ...storyCircleSx(),
                    cursor: "pointer",
                    "&:hover": {
                      transform: "translateY(-2px)",
                      boxShadow: "0 18px 40px rgba(37,99,235,0.28)",
                    },
                    "&:focus-visible": {
                      outline: "none",
                      boxShadow: "0 0 0 4px #1d4ed81f, 0 0 0 6px #1d4ed880",
                    },
                  }}
                >
                  {renderAvatar(story)}
                </ButtonBase>
                <Typography
                  component="span"
                  align="center"
                  title={tooltip}
                  sx={{
                    maxWidth: 84,
                    fontWeight: 600,
                    fontSize: ".85rem",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {story.title}
                </Typography>
              </Stack>
            )
          })}
        </Stack>
      )}

      <Dialog
        fullScreen
        open={openIndex !== null}
        onClose={closeViewer}
        aria-labelledby={dialogTitleId}
        aria-label={storyDialogLabel}
        aria-describedby={
          hasViewerInstructions || normalizedHints.length > 0 ? dialogHintsId : undefined
        }
        keepMounted
        PaperProps={{
          sx: {
            background:
              theme.palette.mode === "dark" ? "rgba(6, 11, 25, 0.94)" : "rgba(12, 29, 67, 0.92)",
            backdropFilter: "blur(16px)",
            color: "#fff",
          },
        }}
      >
        {viewerStory && (
          <Box
            sx={{
              position: "relative",
              width: "100%",
              height: "100%",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Stack direction="row" spacing={1} sx={{ p: { xs: 2, md: 3 }, gap: 1 }}>
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
                    height: 4,
                    borderRadius: 8,
                    backgroundColor: "rgba(255,255,255,0.3)",
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: "#fff",
                      transition: "transform 120ms linear",
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
                top: 16,
                right: 16,
                color: "inherit",
                backgroundColor: "rgba(0,0,0,0.35)",
                "&:hover": { backgroundColor: "rgba(0,0,0,0.5)" },
              }}
            >
              <CloseRoundedIcon />
            </IconButton>

            <Box
              sx={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                px: { xs: 2, md: 6 },
                pb: { xs: 6, md: 8 },
                textAlign: "center",
                gap: 3,
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
              <Box
                sx={{
                  display: "grid",
                  placeItems: "center",
                  borderRadius: "1.6rem",
                  overflow: "hidden",
                  width: "min(86vw, 420px)",
                  height: isMobile ? 280 : 360,
                  boxShadow: "0 20px 45px rgba(0,0,0,0.35)",
                  background: viewerStory.cover_url
                    ? "rgba(0,0,0,0.35)"
                    : "linear-gradient(135deg,#1d4ed8,#60a5fa)",
                }}
              >
                {viewerStory.cover_url ? (
                  <SmartImage
                    srcRaw={viewerStory.cover_url}
                    alt={viewerStory.title}
                    style={{ width: "100%", height: "100%" }}
                  />
                ) : (
                  <Typography sx={{ fontWeight: 800, fontSize: "clamp(1.8rem, 8vw, 2.6rem)" }}>
                    {viewerStory.title.slice(0, 2).toUpperCase()}
                  </Typography>
                )}
              </Box>

            <Stack spacing={1.5} sx={{ maxWidth: 480 }}>
              <Typography id={dialogTitleId} variant="h4" component="h2" sx={{ fontWeight: 800 }}>
                {viewerStory.title}
              </Typography>
              {viewerStory.short_text && (
                <Typography component="p" sx={{ opacity: 0.9, fontSize: "1.05rem" }}>
                  {viewerStory.short_text}
                </Typography>
              )}
              {viewerStory.cta_url && (
                <Button
                  variant="contained"
                  color="secondary"
                  {...(linkPropsFor(viewerStory.cta_url) ?? {})}
                  sx={{ alignSelf: "center", textTransform: "none" }}
                >
                  {t("stories.viewer.openLink")}
                </Button>
              )}
              {(hasViewerInstructions || normalizedHints.length > 0) && (
                <Stack spacing={0.5} id={dialogHintsId}>
                  {hasViewerInstructions && (
                    <Typography sx={{ ...visuallyHidden }}>
                      {viewerInstructions}
                    </Typography>
                  )}
                  {normalizedHints.map((hint, index) => (
                    <Typography
                      key={index}
                      component="p"
                      variant="body2"
                      sx={{ opacity: 0.85 }}
                    >
                      {hint}
                    </Typography>
                  ))}
                </Stack>
              )}
            </Stack>
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
                  left: 8,
                  transform: "translateY(-50%)",
                  pointerEvents: "auto",
                }}
              >
                <IconButton
                  onClick={goPrev}
                  aria-label={t("stories.viewer.aria.prev")}
                  sx={{
                    color: "inherit",
                    backgroundColor: "rgba(0,0,0,0.35)",
                    "&:hover": { backgroundColor: "rgba(0,0,0,0.5)" },
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
                  right: 8,
                  transform: "translateY(-50%)",
                  pointerEvents: "auto",
                }}
              >
                <IconButton
                  onClick={goNext}
                  aria-label={t("stories.viewer.aria.next")}
                  sx={{
                    color: "inherit",
                    backgroundColor: "rgba(0,0,0,0.35)",
                    "&:hover": { backgroundColor: "rgba(0,0,0,0.5)" },
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
