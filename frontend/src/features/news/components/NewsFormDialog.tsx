import { useState, useRef, useCallback, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { Camera as PhotoCamera } from "lucide-react"
import { Dialog, DialogActions, DialogContent, DialogTitle, Alert } from "@/components/settings"
import { Button } from "@/components/ui"
import SmartImage from "@/components/SmartImage"
import { createNews, uploadNewsImage } from "@/api/news"
import { resetEtagCache } from "@/api/client"
import { cn } from "@/utils/cn"
import { type NewsFormState, initialNewsState } from "../types"

const inputClass =
  "w-full rounded-md border border-glass-border bg-(--bg-surface)/(--opacity-medium) px-4 py-2.5 text-input text-text-primary shadow-sm focus:border-brand focus:outline-none transition placeholder:text-(--text-secondary)/(--opacity-medium)"
const textareaClass = cn(inputClass, "min-h-36 resize-y leading-relaxed")

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
        className="text-sm font-semibold tracking-wide text-(--text-secondary)/(--opacity-hover)"
      >
        {label}
        {required ? <span className="ml-1 text-error-text text-sm font-bold">*</span> : null}
      </label>
      {children}
    </div>
  )
}

interface NewsFormDialogProps {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

export const NewsFormDialog = ({ open, onClose, onSuccess }: NewsFormDialogProps) => {
  const { t } = useTranslation(["news", "common"])
  const queryClient = useQueryClient()

  const [newsData, setNewsData] = useState<NewsFormState>(initialNewsState)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)

  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const handleImageChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) {
        setImageFile(file)
        if (imagePreview) URL.revokeObjectURL(imagePreview)
        setImagePreview(URL.createObjectURL(file))
      }
    },
    [imagePreview]
  )

  const resolveCreateError = useCallback(
    (error: unknown) => {
      const fallback =
        t("news:notifications.savedError", { defaultValue: "Failed to save the news" }) ??
        "Failed to save the news"

      if (isAxiosError(error)) {
        const data = error.response?.data
        if (typeof data === "string" && data.trim()) return data
        if (data && typeof data === "object") {
          const detail = (data as { detail?: unknown }).detail
          if (typeof detail === "string" && detail.trim()) return detail
          const message = (data as { message?: unknown }).message
          if (typeof message === "string" && message.trim()) return message
        }
      }

      if (error instanceof Error && error.message?.trim()) {
        return error.message
      }

      return fallback
    },
    [t]
  )

  const handleClose = useCallback(() => {
    onClose()
    // Reset state after transition or immediately if preferred.
    // Doing it here ensures next open is clean.
    setNewsData(initialNewsState)
    setAddError(null)
    setImageFile(null)
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
      setImagePreview(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [onClose, imagePreview])

  const handleAddNews = useCallback(async () => {
    if (adding) return
    setAdding(true)
    setAddError(null)
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

      resetEtagCache()
      void queryClient.invalidateQueries({ queryKey: ["news", "list"] })

      if (onSuccess) onSuccess()
      handleClose()
    } catch (error) {
      setAddError(resolveCreateError(error))
    } finally {
      setAdding(false)
    }
  }, [adding, imageFile, newsData, queryClient, resolveCreateError, onSuccess, handleClose])

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>{t("news:dialogs.create.title")}</DialogTitle>
      <DialogContent className="space-y-6 pt-4">
        <form
          className="grid grid-cols-1 md:grid-cols-2 gap-6"
          onSubmit={(event) => {
            event.preventDefault()
            void handleAddNews()
          }}
        >
          <div className="space-y-4">
            {addError ? <Alert severity="error">{addError}</Alert> : null}

            <Field label={t("news:form.title") ?? ""} htmlFor="news-title" required>
              <input
                id="news-title"
                ref={titleInputRef}
                type="text"
                value={newsData.title}
                onChange={(event) => setNewsData({ ...newsData, title: event.target.value })}
                maxLength={100}
                disabled={adding}
                className={inputClass}
              />
            </Field>

            <Field label={t("news:form.content") ?? ""} htmlFor="news-content" required>
              <textarea
                id="news-content"
                value={newsData.content}
                onChange={(event) => setNewsData({ ...newsData, content: event.target.value })}
                maxLength={3000}
                disabled={adding}
                className={textareaClass}
                rows={6}
              />
            </Field>
          </div>

          <div className="space-y-4">
            <Field
              label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
              htmlFor="news-title-en"
            >
              <input
                id="news-title-en"
                type="text"
                value={newsData.title_en}
                onChange={(event) => setNewsData({ ...newsData, title_en: event.target.value })}
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
                onChange={(event) => setNewsData({ ...newsData, content_en: event.target.value })}
                maxLength={3000}
                disabled={adding}
                className={textareaClass}
                rows={6}
              />
            </Field>

            <div className="space-y-3">
              <label className="block text-sm font-semibold text-(--text-secondary)">
                {t("news:form.image", { defaultValue: "Cover Image" })}
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  as="label"
                  variant="outline"
                  size="sm"
                  className="w-full sm:w-auto bg-(--bg-surface)/(--opacity-dim) border-glass-border"
                  disabled={adding}
                >
                  <div className="flex items-center gap-2">
                    <PhotoCamera className="h-4 w-4" />
                    {imageFile ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                  </div>
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>

                {imagePreview ? (
                  <div className="overflow-hidden rounded-md border border-glass-border shadow-sm">
                    <SmartImage
                      srcRaw={imagePreview}
                      alt={t("news:alt.newCover")}
                      className="h-14 w-28 object-cover"
                    />
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </form>
      </DialogContent>
      <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
        <Button
          variant="ghost"
          onClick={handleClose}
          disabled={adding}
          className="w-full sm:w-auto"
        >
          {t("common:buttons.cancel")}
        </Button>
        <Button
          id="news-publish-btn"
          variant="solid"
          onClick={() => {
            void handleAddNews()
          }}
          disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
          className="w-full sm:w-auto min-w-(--min-w-btn)"
        >
          {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
