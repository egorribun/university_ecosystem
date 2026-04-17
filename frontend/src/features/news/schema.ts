import * as v from "valibot"

// Max file size 5MB
const MAX_FILE_SIZE = 5 * 1024 * 1024
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"]

export const newsFormSchema = v.object({
  title: v.pipe(
    v.string(),
    v.trim(),
    v.minLength(1, "Title is required"),
    v.maxLength(100, "Title must be less than 100 characters")
  ),
  content: v.pipe(
    v.string(),
    v.trim(),
    v.minLength(1, "Content is required"),
    v.maxLength(3000, "Content must be less than 3000 characters")
  ),
  title_en: v.optional(
    v.union([
      v.pipe(v.string(), v.trim(), v.maxLength(100, "Title (EN) must be less than 100 characters")),
      v.literal(""),
    ])
  ),
  content_en: v.optional(
    v.union([
      v.pipe(
        v.string(),
        v.trim(),
        v.maxLength(3000, "Content (EN) must be less than 3000 characters")
      ),
      v.literal(""),
    ])
  ),
  image: v.nullable(
    v.optional(
      v.pipe(
        v.instance(File),
        v.check((file) => file.size <= MAX_FILE_SIZE, "Max image size is 5MB."),
        v.check(
          (file) => ACCEPTED_IMAGE_TYPES.includes(file.type),
          "Only .jpg, .jpeg, .png and .webp formats are supported."
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

export type NewsSearch = v.InferOutput<typeof newsSearchSchema>
