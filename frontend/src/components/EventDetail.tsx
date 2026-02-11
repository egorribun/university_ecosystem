import { useParams, useNavigate } from "react-router-dom"
import type React from "react"
import { useEffect, useState, useRef, useCallback, useActionState, useOptimistic } from "react"
import api from "../api/client"
import {
  Users as PeopleAltIcon,
  ArrowLeft as ArrowBackIcon,
  Trash2 as DeleteIcon,
  Pencil as EditIcon,
  Save as SaveIcon,
  X as CloseIcon,
} from "lucide-react"
import { useAuth } from "../contexts/AuthContext"
import Layout from "../components/Layout"
import { resolveMediaUrl } from "@/utils/media"
import SmartImage from "@/components/SmartImage"
import type { Event } from "@/types/Event"
import { useTranslation } from "react-i18next"
import {
  applyOptimisticFileAction,
  isUploadErrorState,
  type FileOptimisticAction,
  type OptimisticEventFile,
  type UploadState,
} from "./EventDetail.helpers"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { Button, Badge } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { cn } from "@/utils/cn"

dayjs.extend(utc)
dayjs.extend(timezone)

const formatLocalDateTime = (s?: string) => {
  if (!s) return "—"
  const norm = s.replace(" ", "T")
  const withSec = norm.length === 16 ? norm + ":00" : norm
  const d = dayjs(withSec)
  return d.isValid() ? d.format("DD.MM.YYYY HH:mm") : "—"
}
const formatDateSafe = (v?: string) => formatLocalDateTime(v)

const isCanceledRequestError = (err: unknown): boolean => {
  if (typeof err !== "object" || err === null) {
    return false
  }

  const record = err as Record<string, unknown>
  const name = record.name
  const code = record.code

  return (
    (typeof name === "string" && name === "CanceledError") ||
    (typeof code === "string" && code === "ERR_CANCELED")
  )
}

const inputClass =
  "w-full rounded-xl border border-(--glass-border) bg-(--bg-surface)/(--opacity-medium) px-4 py-3 text-input font-medium text-(--text-primary) shadow-sm transition-all duration-200 focus:border-(--primary-main) focus:outline-none focus:ring-4 focus:ring-(--primary-main)/(--opacity-faint) placeholder:text-(--text-secondary)/(--opacity-medium)"

function Snackbar({
  open,
  message,
  onClose,
}: {
  open: boolean
  message: string
  onClose: () => void
}) {
  useEffect(() => {
    if (!open || !message) return
    const timer = setTimeout(() => {
      onClose()
    }, 2500)
    return () => clearTimeout(timer)
  }, [open, message, onClose])

  if (!open || !message) return null

  return (
    <div className="fixed bottom-6 left-1/2 z-(--z-navbar) -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="rounded-[1.25rem] border border-(--glass-border) bg-(--bg-surface)/(--opacity-heavy) px-5 py-3.5 text-sm font-semibold text-(--text-primary) shadow-premium backdrop-blur-md">
        {message}
      </div>
    </div>
  )
}

const EventDetail = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const { t, i18n } = useTranslation(["events", "common"])
  const language = i18n.language?.startsWith("en") ? "en" : "ru"

  const [event, setEvent] = useState<Event | null>(null)
  const [loading, setLoading] = useState(true)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [optimisticFiles, mutateFiles] = useOptimistic<OptimisticEventFile[], FileOptimisticAction>(
    event?.files ?? [],
    applyOptimisticFileAction
  )

  const [uploadState, uploadAction, uploadPending] = useActionState<UploadState, FormData>(
    async (_prev, input) => {
      if (input.get("__upload_reset__") === "1") {
        return { status: "idle" }
      }

      const file = input.get("file")
      if (!(file instanceof File) || file.size === 0) {
        return { status: "error", error: t("events:detail.upload.errors.noFile") }
      }

      if (!event) {
        return { status: "error", error: t("events:detail.messages.notFound") }
      }

      const optimisticId = `pending-${Date.now()}`
      mutateFiles({
        type: "add",
        file: {
          id: optimisticId,
          event_id: event.id,
          description: file.name,
          file_url: "",
          pending: true,
        },
      })

      try {
        const data = new FormData()
        data.append("file", file)
        await api.post(`/events/${id}/upload_file`, data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        mutateFiles({ type: "remove", id: optimisticId })
        setSnackbar(t("events:detail.messages.fileAdded"))
        setSelectedFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ""
        await refreshEvent().catch(() => {})
        return { status: "success" }
      } catch (err) {
        mutateFiles({ type: "remove", id: optimisticId })
        setSnackbar(t("events:detail.messages.fileAddFailed"))
        return { status: "error", error: t("events:detail.upload.errors.failed") }
      }
    },
    { status: "idle" }
  )

  const [editingAbout, setEditingAbout] = useState(false)
  const [aboutDraft, setAboutDraft] = useState("")
  const [savingAbout, setSavingAbout] = useState(false)

  const [snackbar, setSnackbar] = useState("")
  const [heroPos, setHeroPos] = useState<"50% 18%" | "50% 38%" | "50% 50%" | string>("50% 38%")
  const handleHeroLoad: React.ReactEventHandler<HTMLImageElement> = (e) => {
    const img = e.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (!w || !h) return
    const r = w / h
    if (r < 0.9) setHeroPos("50% 18%")
    else if (r > 2) setHeroPos("50% 50%")
    else setHeroPos("50% 38%")
  }
  const aboutSectionRef = useRef<HTMLHeadingElement | null>(null)

  const imageUrl = event?.image_url || ""

  useEffect(() => {
    setHeroPos("50% 38%")
  }, [imageUrl])

  const fetchEvent = useCallback(
    async (signal?: AbortSignal) => {
      const res = await api.get<Event>(`/events/${id}`, signal ? { signal } : undefined)
      return res.data
    },
    [id]
  )

  const refreshEvent = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      try {
        const data = await fetchEvent(signal)
        if (!signal?.aborted) {
          setEvent(data)
        }
        return data
      } catch (err) {
        if (!isCanceledRequestError(err) && !signal?.aborted) {
          setSnackbar(t("events:detail.messages.loadFailed"))
        }
        throw err
      } finally {
        if (!signal?.aborted) {
          setLoading(false)
        }
      }
    },
    [fetchEvent, t]
  )

  useEffect(() => {
    const controller = new AbortController()
    refreshEvent(controller.signal).catch(() => {})
    return () => controller.abort()
  }, [refreshEvent])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = e.target.files?.[0] || null
    setSelectedFile(nextFile)
    if (isUploadErrorState(uploadState) && !uploadPending) {
      const marker = new FormData()
      marker.append("__upload_reset__", "1")
      uploadAction(marker)
    }
  }

  const handleDeleteFile = async (fileId: string) => {
    mutateFiles({ type: "remove", id: fileId })
    try {
      await api.delete(`/events/file/${fileId}`)
      setSnackbar(t("events:detail.messages.fileDeleted"))
    } catch {
      setSnackbar(t("events:detail.messages.fileDeleteFailed"))
    } finally {
      await refreshEvent().catch(() => {})
    }
  }

  const getAboutBaseline = useCallback(() => {
    if (!event) return ""
    return language === "en" ? (event.about_en ?? "") : (event.about ?? "")
  }, [event, language])

  const aboutBaseline = getAboutBaseline()

  const handleEditAbout = () => {
    if (!event) {
      return
    }

    setAboutDraft(aboutBaseline)
    setEditingAbout(true)
  }

  const handleSaveAbout = async () => {
    if (!event) {
      setSnackbar(t("events:detail.messages.aboutUpdateFailed"))
      return
    }

    setSavingAbout(true)
    try {
      const payloadKey = language === "en" ? "about_en" : "about"
      await api.patch(`/events/${event.id}`, { [payloadKey]: aboutDraft.trim() })
      setEditingAbout(false)
      setSnackbar(t("events:detail.messages.aboutUpdated"))
      await refreshEvent().catch(() => {})
      setTimeout(() => aboutSectionRef.current?.focus?.(), 0)
    } catch {
      setSnackbar(t("events:detail.messages.aboutUpdateFailed"))
    } finally {
      setSavingAbout(false)
    }
  }

  const handleCancelAbout = () => {
    setEditingAbout(false)
    setAboutDraft(aboutBaseline)
  }

  const handleBack = () => {
    const canGoBack =
      window.history?.state &&
      typeof window.history.state.idx === "number" &&
      window.history.state.idx > 0
    if (canGoBack) navigate(-1)
    else navigate("/events")
  }

  if (loading) {
    return (
      <Layout>
        <div className="flex min-h-(--h-hero-lg) items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--primary-main) border-t-transparent" />
        </div>
      </Layout>
    )
  }

  if (!event) {
    return (
      <Layout>
        <div className="flex min-h-(--h-hero-lg) items-center justify-center">
          <p className="text-(--text-primary)">{t("events:detail.messages.notFound")}</p>
        </div>
      </Layout>
    )
  }

  const BackButton = (
    <Button
      onClick={handleBack}
      leadingIcon={<ArrowBackIcon size={20} />}
      className={cn(
        "mb-6 w-full font-bold sm:w-auto",
        "bg-linear-to-r from-(--primary-main) via-(--primary-main) to-(--primary-main) text-white",
        "shadow-premium ring-1 ring-white/(--opacity-subtle)",
        "transition-all duration-300 transform-gpu",
        "hover:scale-105 hover:shadow-glass-strong",
        "active:scale-95",
        "md:sticky md:top-3 md:z-(--z-overlay)"
      )}
    >
      {t("common:buttons.back")}
    </Button>
  )

  if (isMobile) {
    return (
      <Layout>
        <div className="w-full min-h-(--h-screen-offset) bg-(--bg-page) px-4 py-4 sm:px-6 md:px-8 lg:px-12">
          {BackButton}
          <div className="space-y-6">
            <h1 className="text-2xl font-extrabold text-(--text-primary) sm:text-3xl">
              {event.title}
            </h1>
            <div className="flex flex-wrap items-center gap-2">
              {event.event_type && (
                <Badge size="sm" className="bg-(--primary-main) text-white">
                  {event.event_type}
                </Badge>
              )}
              <Badge
                size="sm"
                leadingIcon={<PeopleAltIcon size={16} className="text-(--primary-main)" />}
                className="border-(--glass-border) bg-(--primary-main)/(--opacity-faint) text-(--primary-main)"
              >
                {t("events:card.participants", { count: event.participant_count || 0 })}
              </Badge>
            </div>
            <p className="text-base font-semibold text-(--text-primary)">{event.description}</p>
            <div className="space-y-2">
              <p className="text-base font-semibold text-(--text-primary)">
                {t("events:detail.fields.location")}: <strong>{event.location}</strong>
              </p>
              <p className="text-base text-(--text-primary)">
                {t("events:detail.fields.date")}:{" "}
                <strong>
                  {formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}
                </strong>
              </p>
              {event.speaker && (
                <p className="text-base text-(--text-primary)">
                  {t("events:detail.fields.speaker")}: <strong>{event.speaker}</strong>
                </p>
              )}
            </div>
            {imageUrl && (
              <div className="relative w-full overflow-hidden rounded-2xl border border-(--glass-border) bg-black/(--opacity-faint) shadow-premium aspect-video">
                <SmartImage
                  srcRaw={imageUrl}
                  alt={t("events:alt.image")}
                  onLoad={handleHeroLoad}
                  className="absolute inset-0 block h-full w-full object-cover"
                  style={{ objectPosition: heroPos }}
                />
              </div>
            )}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <h2
                  ref={aboutSectionRef}
                  tabIndex={-1}
                  className="text-xl font-bold text-(--text-primary)"
                >
                  {t("events:detail.sections.about.title")}
                </h2>
                {(user?.role === "admin" || user?.role === "teacher") && !editingAbout && (
                  <button
                    type="button"
                    aria-label={t("events:detail.sections.about.editAria")}
                    className="rounded-full p-1 text-(--text-secondary) transition-colors hover:text-(--primary-main)"
                    onClick={handleEditAbout}
                  >
                    <EditIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
              {editingAbout ? (
                <div className="space-y-3">
                  <textarea
                    value={aboutDraft}
                    onChange={(e) => setAboutDraft(e.target.value)}
                    disabled={savingAbout}
                    rows={3}
                    className={cn(inputClass, "min-h-(--min-h-textarea) resize-y")}
                    placeholder={
                      language === "en"
                        ? t("events:detail.sections.about.fieldLabel_en", {
                            defaultValue: `${t("events:detail.sections.about.fieldLabel")} (English)`,
                          })
                        : t("events:detail.sections.about.fieldLabel")
                    }
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="solid"
                      size="sm"
                      leadingIcon={<SaveIcon />}
                      onClick={handleSaveAbout}
                      disabled={savingAbout || aboutDraft.trim() === aboutBaseline.trim()}
                    >
                      {savingAbout
                        ? t("events:detail.sections.about.savePending")
                        : t("common:buttons.save")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      leadingIcon={<CloseIcon />}
                      onClick={handleCancelAbout}
                      disabled={savingAbout}
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <p
                  className={cn(
                    "whitespace-pre-line text-base leading-relaxed",
                    event?.about ? "text-(--text-primary)" : "text-(--text-secondary)"
                  )}
                >
                  {event?.about || t("events:detail.sections.about.empty")}
                </p>
              )}
            </div>

            {user && (user.role === "admin" || user.role === "teacher") && (
              <div>
                <form action={uploadAction} className="flex flex-wrap items-center gap-2">
                  <Button variant="solid" as="label" disabled={uploadPending}>
                    {t("events:detail.sections.files.pickFile")}
                    <input
                      type="file"
                      name="file"
                      hidden
                      required
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      disabled={uploadPending}
                    />
                  </Button>
                  <Button variant="outline" type="submit" disabled={!selectedFile || uploadPending}>
                    {uploadPending
                      ? t("events:detail.upload.submit.pending")
                      : t("events:detail.upload.submit.label")}
                  </Button>
                  {selectedFile && (
                    <span
                      className="ml-2 max-w-[110px] truncate text-xs text-(--text-secondary)"
                      title={selectedFile.name}
                    >
                      {selectedFile.name}
                    </span>
                  )}
                </form>
                {isUploadErrorState(uploadState) && (
                  <p className="mt-2 text-xs text-error-text">{uploadState.error}</p>
                )}
              </div>
            )}

            {optimisticFiles.length > 0 ? (
              <div>
                <h3 className="mb-2 text-base font-semibold text-(--text-primary)">
                  {t("events:detail.sections.files.title")}
                </h3>
                <div className="space-y-2">
                  {optimisticFiles.map((f) => {
                    const isPendingFile =
                      f.pending === true || f.id.toString().startsWith("pending-")
                    const fallbackName = f.file_url.split("/").pop() || f.file_url
                    const fileLabel = f.description || fallbackName
                    return (
                      <div key={f.id} className="flex items-center gap-2">
                        {isPendingFile ? (
                          <span className="flex-1 text-sm text-(--text-secondary)">
                            {f.description || t("events:detail.sections.files.pending")}
                          </span>
                        ) : (
                          <a
                            href={resolveMediaUrl(f.file_url) || "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            download
                            title={fileLabel}
                            aria-label={t("events:detail.sections.files.downloadAria", {
                              label: fileLabel,
                            })}
                            className="flex-1 text-sm font-medium text-(--primary-main) underline transition-colors hover:text-(--primary-dark)"
                          >
                            {fileLabel}
                          </a>
                        )}
                        {(user?.role === "admin" || user?.role === "teacher") && (
                          <button
                            type="button"
                            aria-label={t("events:detail.sections.files.deleteAria")}
                            disabled={isPendingFile}
                            className="rounded-full p-1 text-error-text transition-colors hover:bg-error-bg/(--opacity-subtle) disabled:opacity-(--opacity-medium)"
                            onClick={async () => {
                              if (!isPendingFile) {
                                await handleDeleteFile(f.id)
                              }
                            }}
                          >
                            <DeleteIcon className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <p className="text-sm text-(--text-secondary)">
                {t("events:detail.sections.files.empty")}
              </p>
            )}
          </div>

          <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="flex w-full min-h-(--h-screen-offset) flex-col bg-(--bg-page) px-4 py-4 sm:px-6 md:px-8 lg:px-12">
        {BackButton}
        <div className="flex flex-row gap-8 items-start">
          <div className="w-[45%] space-y-6">
            {imageUrl && (
              <div className="relative w-full overflow-hidden rounded-4xl border border-(--glass-border) bg-black/(--opacity-faint) shadow-premium aspect-21/9">
                <SmartImage
                  srcRaw={imageUrl}
                  alt={t("events:alt.image")}
                  onLoad={handleHeroLoad}
                  className="absolute inset-0 block h-full w-full object-cover"
                  style={{ objectPosition: heroPos }}
                />
              </div>
            )}
            <div className="h-px bg-(--glass-border)" />
            <div>
              <div className="mb-2 flex items-center gap-2">
                <h2
                  ref={aboutSectionRef}
                  tabIndex={-1}
                  className="text-2xl font-bold text-(--text-primary)"
                >
                  {t("events:detail.sections.about.title")}
                </h2>
                {(user?.role === "admin" || user?.role === "teacher") && !editingAbout && (
                  <button
                    type="button"
                    aria-label={t("events:detail.sections.about.editAria")}
                    className="rounded-full p-1 text-(--text-secondary) transition-colors hover:text-(--primary-main)"
                    onClick={handleEditAbout}
                  >
                    <EditIcon size={20} />
                  </button>
                )}
              </div>
              {editingAbout ? (
                <div className="space-y-3">
                  <textarea
                    value={aboutDraft}
                    onChange={(e) => setAboutDraft(e.target.value)}
                    disabled={savingAbout}
                    rows={3}
                    className={cn(inputClass, "min-h-(--min-h-textarea) resize-y")}
                    placeholder={
                      language === "en"
                        ? t("events:detail.sections.about.fieldLabel_en", {
                            defaultValue: `${t("events:detail.sections.about.fieldLabel")} (English)`,
                          })
                        : t("events:detail.sections.about.fieldLabel")
                    }
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="solid"
                      size="sm"
                      leadingIcon={<SaveIcon size={18} />}
                      onClick={handleSaveAbout}
                      disabled={savingAbout || aboutDraft.trim() === aboutBaseline.trim()}
                    >
                      {savingAbout
                        ? t("events:detail.sections.about.savePending")
                        : t("common:buttons.save")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      leadingIcon={<CloseIcon size={18} />}
                      onClick={handleCancelAbout}
                      disabled={savingAbout}
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <p
                  className={cn(
                    "whitespace-pre-line text-lg leading-relaxed",
                    event?.about ? "text-(--text-primary)" : "text-(--text-secondary)"
                  )}
                >
                  {event?.about || t("events:detail.sections.about.empty")}
                </p>
              )}
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-4">
            <h1 className="text-4xl font-extrabold text-(--text-primary) sm:text-5xl">
              {event.title}
            </h1>
            <div className="flex flex-wrap items-center gap-3">
              {event.event_type && (
                <Badge size="md" className="bg-(--primary-main) text-white">
                  {event.event_type}
                </Badge>
              )}
              <Badge
                size="md"
                leadingIcon={<PeopleAltIcon size={18} className="text-(--primary-main)" />}
                className="border-(--glass-border) bg-(--primary-main)/5 text-(--primary-main)"
              >
                {t("events:card.participants", { count: event.participant_count || 0 })}
              </Badge>
            </div>
            <div className="h-px bg-(--glass-border)" />
            <p className="whitespace-pre-line text-xl font-semibold leading-relaxed text-(--text-primary)">
              {event.description}
            </p>
            <div className="h-px bg-(--glass-border)" />
            <p className="text-base font-semibold text-(--text-primary)">
              {t("events:detail.fields.location")}: <strong>{event.location}</strong>
            </p>
            <p className="text-base text-(--text-primary)">
              {t("events:detail.fields.date")}:{" "}
              <strong>
                {formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}
              </strong>
            </p>
            {event.speaker && (
              <p className="text-base text-(--text-primary)">
                {t("events:detail.fields.speaker")}: <strong>{event.speaker}</strong>
              </p>
            )}

            {user && (user.role === "admin" || user.role === "teacher") && (
              <div className="mt-4">
                <form action={uploadAction} className="flex flex-wrap items-center gap-3">
                  <Button variant="solid" as="label" disabled={uploadPending}>
                    {t("events:detail.sections.files.pickFile")}
                    <input
                      type="file"
                      name="file"
                      hidden
                      required
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      disabled={uploadPending}
                    />
                  </Button>
                  <Button variant="outline" type="submit" disabled={!selectedFile || uploadPending}>
                    {uploadPending
                      ? t("events:detail.upload.submit.pending")
                      : t("events:detail.upload.submit.label")}
                  </Button>
                  {selectedFile && (
                    <span
                      className="ml-2 max-w-[150px] truncate text-sm text-(--text-secondary)"
                      title={selectedFile.name}
                    >
                      {selectedFile.name}
                    </span>
                  )}
                </form>
                {isUploadErrorState(uploadState) && (
                  <p className="mt-2 text-sm text-error-text">{uploadState.error}</p>
                )}
              </div>
            )}

            {optimisticFiles.length > 0 ? (
              <div>
                <div className="my-3 h-px bg-(--glass-border)" />
                <h3 className="mb-2 text-base font-semibold text-(--text-primary)">
                  {t("events:detail.sections.files.title")}
                </h3>
                <div className="space-y-2">
                  {optimisticFiles.map((f) => {
                    const isPendingFile =
                      f.pending === true || f.id.toString().startsWith("pending-")
                    const fallbackName = f.file_url.split("/").pop() || f.file_url
                    const fileLabel = f.description || fallbackName
                    return (
                      <div key={f.id} className="flex items-center gap-2">
                        {isPendingFile ? (
                          <span className="flex-1 text-sm text-(--text-secondary)">
                            {f.description || t("events:detail.sections.files.pending")}
                          </span>
                        ) : (
                          <a
                            href={resolveMediaUrl(f.file_url) || "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            download
                            title={fileLabel}
                            aria-label={t("events:detail.sections.files.downloadAria", {
                              label: fileLabel,
                            })}
                            className="flex-1 text-sm font-medium text-(--primary-main) underline transition-colors hover:text-(--primary-dark)"
                          >
                            {fileLabel}
                          </a>
                        )}
                        {(user?.role === "admin" || user?.role === "teacher") && (
                          <button
                            type="button"
                            aria-label={t("events:detail.sections.files.deleteAria")}
                            disabled={isPendingFile}
                            className="ml-2 rounded-full p-1 text-error-text transition-colors hover:bg-error-bg/(--opacity-subtle) disabled:opacity-(--opacity-medium)"
                            onClick={async () => {
                              if (!isPendingFile) {
                                await handleDeleteFile(f.id)
                              }
                            }}
                          >
                            <DeleteIcon size={16} />
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <p className="text-sm text-(--text-secondary)">
                {t("events:detail.sections.files.empty")}
              </p>
            )}
          </div>
        </div>

        <Snackbar open={!!snackbar} message={snackbar} onClose={() => setSnackbar("")} />
      </div>
    </Layout>
  )
}

export default EventDetail
