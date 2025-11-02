import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import NewsCard from "../components/NewsCard"
import NewsCardSkeleton from "../components/NewsCardSkeleton"
import {
  useEffect,
  useState,
  useRef,
  useCallback,
  useDeferredValue,
  startTransition,
  useMemo,
  type ReactNode,
} from "react"
import { createNews, uploadNewsImage, type NewsItem } from "@/api/news"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { useNewsFeed } from "@/hooks/useNewsFeed"

const inputClass =
  "w-full rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-4 py-2.5 text-[0.98rem] text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"
const textareaClass = `${inputClass} min-h-[148px] resize-y leading-relaxed`

type NewsFormState = {
  title: string
  content: string
  title_en: string
  content_en: string
}

const initialNews: NewsFormState = {
  title: "",
  content: "",
  title_en: "",
  content_en: "",
}

type FieldProps = {
  label: ReactNode
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]"
      >
        {label}
        {required ? <span className="ml-1 text-[#f87171]">*</span> : null}
      </label>
      {children}
    </div>
  )
}

const revealDelayClasses = [
  "delay-[0ms]",
  "delay-[60ms]",
  "delay-[120ms]",
  "delay-[180ms]",
  "delay-[240ms]",
  "delay-[300ms]",
  "delay-[360ms]",
  "delay-[420ms]",
  "delay-[480ms]",
  "delay-[540ms]",
  "delay-[600ms]",
  "delay-[660ms]",
  "delay-[720ms]",
  "delay-[780ms]",
  "delay-[840ms]",
  "delay-[900ms]",
] as const

type AnimatedNewsGridProps = {
  news: NewsItem[]
  isLoading: boolean
  skeletonCount: number
  showEmptyState: boolean
  onRefresh: () => void
  emptyState?: ReactNode
}

const usePrefersReducedMotion = () => {
  const [prefers, setPrefers] = useState(false)

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")

    const updatePreference = () => {
      setPrefers(mediaQuery.matches)
    }

    updatePreference()

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", updatePreference)
      return () => mediaQuery.removeEventListener("change", updatePreference)
    }

    mediaQuery.addListener(updatePreference)
    return () => mediaQuery.removeListener(updatePreference)
  }, [])

  return prefers
}

const AnimatedNewsGrid = ({
  news,
  isLoading,
  skeletonCount,
  showEmptyState,
  onRefresh,
  emptyState,
}: AnimatedNewsGridProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const prefersReducedMotion = usePrefersReducedMotion()
  const revealSignature = useMemo(() => news.map((item) => item.id).join("|"), [news])
  const totalItems = isLoading ? skeletonCount : news.length

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const elements = Array.from(
      container.querySelectorAll<HTMLElement>('[data-animated-card="true"]'),
    )

    const showImmediately = () => {
      elements.forEach((element) => {
        element.classList.remove("opacity-0", "translate-y-6")
        element.classList.add("opacity-100", "translate-y-0")
      })
    }

    if (prefersReducedMotion || typeof IntersectionObserver === "undefined") {
      showImmediately()
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const target = entry.target as HTMLElement
            target.classList.add("opacity-100", "translate-y-0")
            target.classList.remove("opacity-0", "translate-y-6")
            observer.unobserve(target)
          }
        })
      },
      { threshold: 0.18, rootMargin: "0px 0px -12% 0px" },
    )

    elements.forEach((element) => {
      element.classList.remove("opacity-100", "translate-y-0")
      element.classList.add("opacity-0", "translate-y-6")
      observer.observe(element)
    })

    return () => observer.disconnect()
  }, [prefersReducedMotion, revealSignature, totalItems, isLoading, skeletonCount])

  const getDelayClass = useCallback(
    (index: number) => revealDelayClasses[Math.min(index, revealDelayClasses.length - 1)],
    [],
  )

  const cardClassName =
    "group/card relative flex h-full w-full min-h-[360px] items-stretch overflow-visible " +
    "transform-gpu opacity-0 translate-y-6 transition-[transform,opacity] duration-[680ms] ease-out will-change-transform will-change-opacity"

  const renderSkeletons = () =>
    Array.from({ length: skeletonCount }).map((_, index) => (
      <div
        key={`news-skeleton-${index}`}
        data-animated-card="true"
        className={`${cardClassName} ${getDelayClass(index)}`}
      >
        <NewsCardSkeleton />
      </div>
    ))

  const renderNewsCards = () =>
    news.map((item, index) => (
      <div
        key={item.id}
        data-animated-card="true"
        className={`${cardClassName} ${getDelayClass(index)}`}
      >
        <NewsCard
          {...item}
          image_url={item.image_url ?? undefined}
          onChange={onRefresh}
        />
      </div>
    ))

  return (
    <div
      data-fade
      className="relative isolate mt-2 overflow-hidden rounded-ue-2xl border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_90%,white_10%)]/90 p-5 shadow-[0_35px_80px_-45px_rgba(15,23,42,0.85)] backdrop-blur-2xl [--fade-delay:200ms] sm:p-8 before:pointer-events-none before:absolute before:-left-1/2 before:top-[-38%] before:h-[520px] before:w-[520px] before:translate-x-1/2 before:rounded-full before:bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--glass-highlight)_70%,transparent)_0%,transparent_72%)] before:opacity-70 before:blur-3xl before:content-[''] before:animate-[float_18s_infinite] after:pointer-events-none after:absolute after:-bottom-40 after:right-[-18%] after:h-[460px] after:w-[460px] after:rounded-full after:bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--nav-link)_52%,transparent)_0%,transparent_75%)] after:opacity-55 after:blur-[120px] after:content-[''] after:animate-[float_24s_infinite] after:[animation-delay:3s]"
    >
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.18),transparent_65%)] mix-blend-soft-light" aria-hidden />
      <div ref={containerRef} className="relative z-10 grid grid-cols-[repeat(auto-fit,minmax(310px,1fr))] gap-5 sm:gap-6">
        {isLoading ? renderSkeletons() : renderNewsCards()}
        {showEmptyState && (
          <div className="col-span-full flex justify-center">
            <div className="relative isolate flex w-full max-w-[440px] flex-col items-center gap-5 rounded-ue-xl border border-white/10 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)]/90 px-6 py-12 text-center text-[color:var(--secondary-text)] shadow-surface before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--nav-link)_28%,transparent)_0%,transparent_74%)] before:opacity-80 before:blur-3xl before:content-[''] before:animate-[float_18s_infinite] before:[animation-delay:-2s] after:pointer-events-none after:absolute after:-top-28 after:left-1/2 after:h-[320px] after:w-[320px] after:-translate-x-1/2 after:rounded-full after:bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--glass-highlight)_65%,transparent)_0%,transparent_70%)] after:opacity-65 after:blur-3xl after:content-[''] after:animate-[float_22s_infinite]">
              {emptyState}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const News = () => {
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()
  const { data: newsDataList, refetch: refetchNews, isPending, isFetching } = useNewsFeed(language)
  const newsList = newsDataList ?? []
  const deferredList = useDeferredValue(newsList)
  const [visibleCount, setVisibleCount] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const [newsData, setNewsData] = useState(initialNews)
  const [adding, setAdding] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const isInitialLoading = isPending && newsList.length === 0
  const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0
  const skeletonCount = Math.max(visibleCount || 0, 6)
  const isAdmin = user?.role === "admin"

  useEffect(() => {
    return () => {
      if (imagePreview) URL.revokeObjectURL(imagePreview)
    }
  }, [imagePreview])

  useEffect(() => {
    setVisibleCount(Math.min(12, deferredList.length))
  }, [deferredList.length])

  useEffect(() => {
    if (visibleCount >= deferredList.length) return
    let cancelled = false
    const chunk = 16
    const ric = (cb: () => void) => {
      if (typeof (window as any).requestIdleCallback === "function")
        (window as any).requestIdleCallback(() => {
          if (!cancelled) cb()
        })
      else
        setTimeout(() => {
          if (!cancelled) cb()
        }, 0)
    }
    const step = () => {
      startTransition(() => {
        setVisibleCount((v) => {
          const next = Math.min(v + chunk, deferredList.length)
          if (next < deferredList.length) ric(step)
          return next
        })
      })
    }
    ric(step)
    return () => {
      cancelled = true
    }
  }, [visibleCount, deferredList.length])

  const handleImageChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        setImageFile(file)
        if (imagePreview) URL.revokeObjectURL(imagePreview)
        setImagePreview(URL.createObjectURL(file))
      }
    },
    [imagePreview]
  )

  const handleAddNews = useCallback(async () => {
    if (adding) return
    setAdding(true)
    try {
      let image_url = ""
      if (imageFile) {
        const uploadedUrl = await uploadNewsImage(imageFile)
        image_url = uploadedUrl || ""
      }

      const payload = {
        title: newsData.title,
        content: newsData.content,
        image_url,
        ...(newsData.title_en.trim() ? { title_en: newsData.title_en } : {}),
        ...(newsData.content_en.trim() ? { content_en: newsData.content_en } : {}),
      } satisfies Parameters<typeof createNews>[0]

      await createNews(payload)
      setAddOpen(false)
      setNewsData(initialNews)
      setImageFile(null)
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
        setImagePreview(null)
      }
      void refetchNews()
      if (imageInputRef.current) imageInputRef.current.value = ""
    } finally {
      setAdding(false)
    }
  }, [adding, imageFile, imagePreview, newsData, refetchNews])

  const handleCloseDialog = useCallback(() => {
    setAddOpen(false)
    setNewsData(initialNews)
    setImageFile(null)
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
      setImagePreview(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [imagePreview])

  const visibleList = useMemo(
    () => (visibleCount > 0 ? deferredList.slice(0, visibleCount) : deferredList),
    [deferredList, visibleCount]
  )

  const handleRefreshNews = useCallback(() => {
    void refetchNews()
  }, [refetchNews])

  const emptyStateContent = useMemo(
    () => (
      <>
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
          <ArticleIcon className="text-[2.2rem]" />
        </span>
        <p className="text-lg font-semibold text-[color:var(--page-text)] sm:text-xl">
          {t("news:states.empty")}
        </p>
        {isAdmin && (
          <Button size="lg" onClick={() => setAddOpen(true)} className="px-6">
            {t("news:actions.add")}
          </Button>
        )}
      </>
    ),
    [isAdmin, t]
  )

  return (
    <Layout>
      <PageFadeIn>
        <div className="flex w-full flex-col px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          <div
            data-fade
            className="mb-4 mt-4 flex flex-wrap items-center gap-3 text-nav-link [--fade-delay:80ms] sm:mb-8 sm:mt-6"
          >
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
              <ArticleIcon className="text-[1.85rem]" />
            </span>
            <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
              {t("news:pageTitle")}
            </h1>
          </div>

          {isAdmin && (
            <div data-fade className="mb-6 flex justify-start [--fade-delay:140ms]">
              <Button
                size="lg"
                onClick={() => setAddOpen(true)}
                disabled={adding}
                className="px-6 text-[clamp(1rem,2.2vw,1.1rem)]"
              >
                {t("news:actions.add")}
              </Button>
            </div>
          )}

          <AnimatedNewsGrid
            news={visibleList}
            isLoading={isInitialLoading}
            skeletonCount={skeletonCount}
            showEmptyState={showEmptyState}
            onRefresh={handleRefreshNews}
            emptyState={emptyStateContent}
          />

          <Dialog
            open={addOpen}
            onClose={handleCloseDialog}
            title={t("news:dialogs.create.title")}
            size="md"
            fullScreenOnMobile
            closeLabel={t("common:buttons.close")}
            bodyClassName="space-y-4"
            footerClassName="flex-col-reverse gap-3 sm:flex-row"
            footer={
              <>
                <Button
                  variant="outline"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  className="w-full sm:w-auto"
                >
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  onClick={() => {
                    void handleAddNews()
                  }}
                  disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
                  loading={adding}
                  className="w-full sm:w-auto"
                >
                  {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                </Button>
              </>
            }
            initialFocus={() => titleInputRef.current ?? undefined}
          >
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                void handleAddNews()
              }}
            >
              <Field label={t("news:form.title") ?? ""} htmlFor="news-title" required>
                <input
                  id="news-title"
                  ref={titleInputRef}
                  type="text"
                  value={newsData.title}
                  onChange={(e) => setNewsData({ ...newsData, title: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                  className={inputClass}
                />
              </Field>

              <Field label={t("news:form.content") ?? ""} htmlFor="news-content" required>
                <textarea
                  id="news-content"
                  value={newsData.content}
                  onChange={(e) => setNewsData({ ...newsData, content: e.target.value })}
                  maxLength={3000}
                  disabled={adding}
                  className={textareaClass}
                  rows={6}
                />
              </Field>

              <Field
                label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                htmlFor="news-title-en"
              >
                <input
                  id="news-title-en"
                  type="text"
                  value={newsData.title_en}
                  onChange={(e) => setNewsData({ ...newsData, title_en: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                  className={inputClass}
                />
              </Field>

              <Field
                label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
                htmlFor="news-content-en"
              >
                <textarea
                  id="news-content-en"
                  value={newsData.content_en}
                  onChange={(e) => setNewsData({ ...newsData, content_en: e.target.value })}
                  maxLength={3000}
                  disabled={adding}
                  className={textareaClass}
                  rows={6}
                />
              </Field>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Button
                  as="label"
                  variant="outline"
                  size="sm"
                  leadingIcon={<PhotoCamera className="text-[1.15rem]" />}
                  className="w-full sm:w-auto"
                  disabled={adding}
                >
                  {imageFile ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>

                {imagePreview ? (
                  <SmartImage
                    srcRaw={imagePreview}
                    alt={t("news:alt.newCover")}
                    className="h-20 w-full max-w-[160px] rounded-ue-md border border-white/10 object-cover shadow-surface"
                  />
                ) : null}
              </div>
            </form>
          </Dialog>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default News
