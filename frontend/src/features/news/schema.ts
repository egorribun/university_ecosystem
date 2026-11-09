import * as v from "valibot"
import { MAX_IMAGE_UPLOAD_BYTES } from "@/constants/uploads"

const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"]

export const newsFormSchema = v.object({
  title: v.pipe(
    v.string(),
    v.trim(),
    v.minLength(1, "news:form.validation.titleRequired"),
    v.maxLength(100, "news:form.validation.titleMaxLength")
  ),
  content: v.pipe(
    v.string(),
    v.trim(),
    v.minLength(1, "news:form.validation.contentRequired"),
    v.maxLength(3000, "news:form.validation.contentMaxLength")
  ),
  title_en: v.optional(
    v.pipe(v.string(), v.trim(), v.maxLength(100, "news:form.validation.titleEnMaxLength"))
  ),
  content_en: v.optional(
    v.pipe(v.string(), v.trim(), v.maxLength(3000, "news:form.validation.contentEnMaxLength"))
  ),
  image: v.nullable(
    v.optional(
      v.pipe(
        v.instance(File),
        v.check((file) => file.size <= MAX_IMAGE_UPLOAD_BYTES, "news:form.validation.imageMaxSize"),
        v.check(
          (file) => ACCEPTED_IMAGE_TYPES.includes(file.type),
          "news:form.validation.imageFormats"
        )
      )
    )
  ),
})

export type NewsFormValues = v.InferInput<typeof newsFormSchema>

/**
 * News route search-param schema — Wave 112 SW3 URL-sync.
 *
 * Mirrors Events' convention (`q/cat/sort/...`) so cross-page UX is
 * consistent: refresh preserves filters, share links preserve filters,
 * and users can bookmark a filtered view.
 *
 * Keys intentionally short — the URL bar has limited screen real estate
 * on mobile and these surface in share-sheet previews.
 *
 *   q    — free-text search query (no length cap — client-side validates)
 *   cat  — category slug | "all" | "saved" (bookmarks view)
 *   sort — "newest" | "popular"
 */
export const newsSearchSchema = v.object({
  q: v.optional(v.string()),
  cat: v.optional(v.string()),
  sort: v.optional(v.picklist(["newest", "popular"])),
})
