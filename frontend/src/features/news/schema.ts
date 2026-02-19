
import { z } from "zod"

// Max file size 5MB
const MAX_FILE_SIZE = 5 * 1024 * 1024
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"]

export const newsFormSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Title is required")
    .max(100, "Title must be less than 100 characters"),
  content: z
    .string()
    .trim()
    .min(1, "Content is required")
    .max(3000, "Content must be less than 3000 characters"),
  title_en: z
    .string()
    .trim()
    .max(100, "Title (EN) must be less than 100 characters")
    .optional()
    .or(z.literal("")),
  content_en: z
    .string()
    .trim()
    .max(3000, "Content (EN) must be less than 3000 characters")
    .optional()
    .or(z.literal("")),
  image: z
    .instanceof(File)
    .refine((file) => file.size <= MAX_FILE_SIZE, `Max image size is 5MB.`)
    .refine(
      (file) => ACCEPTED_IMAGE_TYPES.includes(file.type),
      "Only .jpg, .jpeg, .png and .webp formats are supported."
    )
    .optional()
    .nullable(),
})

export type NewsFormValues = z.infer<typeof newsFormSchema>
