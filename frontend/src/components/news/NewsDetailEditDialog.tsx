import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { Camera as PhotoCamera } from "lucide-react"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import SmartImage from "@/components/media/SmartImage"
import { Button, Input, Textarea } from "@/components/ui"
import { updateNews, uploadNewsImage } from "@/api/news"
import { useTranslation } from "react-i18next"
import { useQueryClient } from "@tanstack/react-query"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"

/* ── Form field helper ── */
type FieldProps = {
  label: ReactNode
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-(--text-secondary)"
      >
        {label}
        {required && <span className="ml-1 text-(--error-text)">*</span>}
      </label>
      {children}
    </div>
  )
}

interface NewsDetailEditDialogProps {
  open: boolean
  onClose: () => void
  newsId: string
  language: string
  initialData: {
    title: string
    content: string
    title_en: string
    content_en: string
    image_url: string
  }
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

export function NewsDetailEditDialog({
  open,
  onClose,
  newsId,
  language,
  initialData,
  onSuccess,
  onError,
}: NewsDetailEditDialogProps) {
  const { t } = useTranslation(["news", "common"])
  const queryClient = useQueryClient()

  const [editData, setEditData] = useState(initialData)
  const [saving, setSaving] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  // Sync initial data when dialog opens
  useEffect(() => {
    if (open) setEditData(initialData)
  }, [open, initialData])

  // Cleanup preview URL on unmount
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    },
    [previewUrl]
  )

  const resetPreview = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
    setNewImage(null)
  }, [previewUrl])

  const handleClose = useCallback(() => {
    resetPreview()
    onClose()
  }, [resetPreview, onClose])

  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setNewImage(file)
    setPreviewUrl(URL.createObjectURL(file))
  }

  const imageUrl = previewUrl || editData.image_url

  const handleSave = async () => {
    const telemetryContext = captureActiveTelemetryContext()
    setSaving(true)
    try {
      let finalImageUrl = editData.image_url
      const image = newImage
      if (image) {
        finalImageUrl = await telemetryContext.run(() => uploadNewsImage(image))
      }
      const { data } = await telemetryContext.run(() =>
        updateNews(newsId, {
          title: editData.title,
          content: editData.content,
          title_en: editData.title_en,
          content_en: editData.content_en,
          image_url: finalImageUrl,
        })
      )
      queryClient.setQueryData(["news", newsId, language], data)
      await telemetryContext.run(() =>
        queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      )
      onSuccess(t("news:notifications.updated"))
      handleClose()
    } catch {
      onError(t("news:notifications.savedError"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>{t("news:dialogs.edit.title")}</DialogTitle>
      <DialogContent className="space-y-6 pt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <Field label={t("news:form.title") ?? ""} htmlFor="edit-title" required>
              <Input
                id="edit-title"
                type="text"
                value={editData.title}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setEditData({ ...editData, title: e.target.value })
                }
                maxLength={100}
              />
            </Field>
            <Field label={t("news:form.content") ?? ""} htmlFor="edit-content" required>
              <Textarea
                id="edit-content"
                value={editData.content}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setEditData({ ...editData, content: e.target.value })
                }
                maxLength={3000}
                rows={6}
              />
            </Field>
          </div>
          <div className="space-y-4">
            <Field label={t("news:form.title_en") ?? ""} htmlFor="edit-title-en">
              <Input
                id="edit-title-en"
                type="text"
                value={editData.title_en}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setEditData({ ...editData, title_en: e.target.value })
                }
                maxLength={100}
              />
            </Field>
            <Field label={t("news:form.content_en") ?? ""} htmlFor="edit-content-en">
              <Textarea
                id="edit-content-en"
                value={editData.content_en}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setEditData({ ...editData, content_en: e.target.value })
                }
                maxLength={3000}
                rows={6}
              />
            </Field>
            <div className="space-y-3">
              <label className="block text-sm font-semibold text-(--text-secondary)">
                {t("news:form.image")}
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button as="label" variant="glass" className="w-full sm:w-auto" disabled={saving}>
                  <div className="flex items-center gap-2">
                    <PhotoCamera className="h-4 w-4" />
                    {newImage ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                  </div>
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>
                {imageUrl && (
                  <div className="overflow-hidden rounded-lg border border-glass-border/(--opacity-soft) shadow-sm">
                    <SmartImage
                      srcRaw={imageUrl}
                      alt={t("news:alt.editPreview")}
                      className="h-14 w-28 object-cover"
                    />
                  </div>
                )}
              </div>
              {previewUrl && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={resetPreview}
                  className="text-(--error-text)"
                >
                  {t("common:buttons.reset")}
                </Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
      <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
        <Button variant="ghost" onClick={handleClose} className="w-full sm:w-auto">
          {t("common:buttons.cancel")}
        </Button>
        <Button
          variant="solid"
          onClick={handleSave}
          disabled={!editData.title.trim() || !editData.content.trim() || saving}
          className="w-full sm:w-auto min-w-32"
        >
          {saving ? t("common:buttons.saving") : t("common:buttons.save")}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
