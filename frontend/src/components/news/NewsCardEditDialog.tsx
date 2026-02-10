import { FC, useState, useRef, useEffect, useCallback, useMemo, type ReactNode } from "react"
import { Camera as PhotoCamera } from "lucide-react"
import { useTranslation } from "react-i18next"
import api from "../../api/client"
import { Button } from "../ui"
import Dialog from "../Dialog"
import SmartImage from "../SmartImage"

interface NewsEditData {
  title: string
  content: string
  title_en: string
  content_en: string
  image_url: string
}

interface NewsCardEditDialogProps {
  id: string
  open: boolean
  onClose: () => void
  initialData: NewsEditData
  onSuccess?: () => void
}

const inputClass =
  "w-full rounded-xl border border-glass-border bg-input-mix px-4 py-2.5 text-[0.98rem] text-(--text-primary) shadow-inner-premium transition focus:border-(--primary-main) focus:outline-none focus:shadow-focus placeholder:text-(--text-secondary)"
const textareaClass = `${inputClass} min-h-(--space-32) resize-y leading-relaxed`

type FieldProps = {
  label: string
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-[color-mix(in_srgb,var(--text-secondary)_85%,white_15%)]"
      >
        {label}
        {required ? <span className="ml-1 text-(--error-text)">*</span> : null}
      </label>
      {children}
    </div>
  )
}

export const NewsCardEditDialog: FC<NewsCardEditDialogProps> = ({
  id,
  open,
  onClose,
  initialData,
  onSuccess,
}) => {
  const { t } = useTranslation(["news", "common"])
  const [editData, setEditData] = useState<NewsEditData>(initialData)
  const [loading, setLoading] = useState(false)
  const [imageLoading, setImageLoading] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setEditData(initialData)
    }
  }, [open, initialData])

  useEffect(() => {
    if (!newImage) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(newImage)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [newImage])

  const editImageUrl = useMemo(
    () => previewUrl || editData.image_url || "",
    [editData.image_url, previewUrl]
  )

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setNewImage(file)
  }

  const handleEdit = async () => {
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      if (newImage) {
        setImageLoading(true)
        try {
          const data = new FormData()
          data.append("file", newImage)
          const res = await api.post<{ url: string }>(`/news/upload_image`, data, {
            headers: { "Content-Type": "multipart/form-data" },
          })
          imgUrl = res.data.url
        } finally {
          setImageLoading(false)
        }
      }
      const payload = {
        ...editData,
        image_url: imgUrl,
      }
      await api.patch(`/news/${id}`, payload)
      onSuccess?.()
      onClose()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("news:dialogs.edit.title")}
      size="md"
      fullScreenOnMobile
      closeLabel={t("common:buttons.close")}
      bodyClassName="space-y-4"
      footerClassName="flex-col-reverse gap-3 sm:flex-row"
      footer={
        <>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={loading || imageLoading}
            className="w-full sm:w-auto"
          >
            {t("common:buttons.cancel")}
          </Button>
          <Button
            onClick={() => void handleEdit()}
            disabled={loading || imageLoading}
            loading={loading}
            className="w-full sm:w-auto"
          >
            {t("common:buttons.save")}
          </Button>
        </>
      }
      initialFocus={() => editTitleRef.current ?? undefined}
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          void handleEdit()
        }}
      >
        <Field label={t("news:form.title") ?? ""} htmlFor={`news-edit-title-${id}`} required>
          <input
            id={`news-edit-title-${id}`}
            ref={editTitleRef}
            type="text"
            value={editData.title}
            onChange={(e) => setEditData({ ...editData, title: e.target.value })}
            className={inputClass}
          />
        </Field>

        <Field label={t("news:form.text") ?? ""} htmlFor={`news-edit-content-${id}`} required>
          <textarea
            id={`news-edit-content-${id}`}
            value={editData.content}
            onChange={(e) => setEditData({ ...editData, content: e.target.value })}
            className={textareaClass}
            rows={4}
          />
        </Field>

        <Field
          label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
          htmlFor={`news-edit-title-en-${id}`}
        >
          <input
            id={`news-edit-title-en-${id}`}
            type="text"
            value={editData.title_en}
            onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
            className={inputClass}
          />
        </Field>

        <Field
          label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
          htmlFor={`news-edit-content-en-${id}`}
        >
          <textarea
            id={`news-edit-content-en-${id}`}
            value={editData.content_en}
            onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
            className={textareaClass}
            rows={4}
          />
        </Field>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            as="label"
            variant="outline"
            size="sm"
            leadingIcon={<PhotoCamera size={20} />}
            className="w-full sm:w-auto"
            disabled={imageLoading}
          >
            {imageLoading ? t("common:statuses.uploading") : t("news:form.changePhoto")}
            <input
              type="file"
              accept="image/*"
              hidden
              ref={imageInputRef}
              onChange={handleImageChange}
            />
          </Button>

          {editImageUrl ? (
            <SmartImage
              srcRaw={editImageUrl}
              alt={t("news:alt.preview")}
              className="h-20 w-full max-w-[180px] rounded-lg border border-white/10 object-cover shadow-surface"
            />
          ) : null}
        </div>
      </form>
    </Dialog>
  )
}





