import * as v from "valibot"
import { describe, expect, it } from "vitest"

import { MAX_IMAGE_UPLOAD_BYTES } from "@/constants/uploads"
import { newsFormSchema, newsSearchSchema } from "@/features/news/schema"

const validForm = (overrides: Record<string, unknown> = {}) => ({
  title: "Campus update",
  content: "A short announcement",
  title_en: "",
  content_en: "",
  image: null,
  ...overrides,
})

describe("news public schemas", () => {
  describe("news form values", () => {
    it("trims submitted text and accepts the documented maximum lengths", () => {
      const parsed = v.parse(
        newsFormSchema,
        validForm({
          title: `  ${"t".repeat(100)}  `,
          content: ` ${"c".repeat(3000)} `,
          title_en: "  English title  ",
          content_en: " English content ",
        })
      )

      expect(parsed.title).toBe("t".repeat(100))
      expect(parsed.content).toBe("c".repeat(3000))
      expect(parsed.title_en).toBe("English title")
      expect(parsed.content_en).toBe("English content")
    })

    it("preserves optional English fields when omitted, undefined, empty, or whitespace", () => {
      const omitted = v.parse(newsFormSchema, {
        title: "Campus update",
        content: "A short announcement",
        image: null,
      })
      expect(omitted).not.toHaveProperty("title_en")
      expect(omitted).not.toHaveProperty("content_en")

      const undefinedFields = v.parse(
        newsFormSchema,
        validForm({ title_en: undefined, content_en: undefined })
      )
      expect(undefinedFields.title_en).toBeUndefined()
      expect(undefinedFields.content_en).toBeUndefined()

      const emptyAndWhitespace = v.parse(
        newsFormSchema,
        validForm({ title_en: "", content_en: "   " })
      )
      expect(emptyAndWhitespace.title_en).toBe("")
      expect(emptyAndWhitespace.content_en).toBe("")
    })

    it.each([
      {
        field: "title_en" as const,
        max: 100,
        message: "Title (EN) must be less than 100 characters",
      },
      {
        field: "content_en" as const,
        max: 3000,
        message: "Content (EN) must be less than 3000 characters",
      },
    ])("preserves the $field length boundary", ({ field, max, message }) => {
      const atLimit = v.parse(newsFormSchema, validForm({ [field]: `${"x".repeat(max)} ` }))
      expect(atLimit[field]).toBe("x".repeat(max))

      const overLimit = v.safeParse(newsFormSchema, validForm({ [field]: "x".repeat(max + 1) }))
      expect(overLimit.success).toBe(false)
      if (overLimit.success) return
      expect(overLimit.issues.map((issue) => issue.message)).toContain(message)
    })

    it.each(["title_en", "content_en"] as const)(
      "rejects null for optional $field text",
      (field) => {
        expect(v.safeParse(newsFormSchema, validForm({ [field]: null })).success).toBe(false)
      }
    )

    it("reports the title and content limits when input exceeds them", () => {
      const result = v.safeParse(
        newsFormSchema,
        validForm({ title: "t".repeat(101), content: "c".repeat(3001) })
      )

      expect(result.success).toBe(false)
      if (result.success) return

      expect(result.issues.map((issue) => issue.message)).toEqual(
        expect.arrayContaining([
          "Title must be less than 100 characters",
          "Content must be less than 3000 characters",
        ])
      )
    })

    it.each(["image/jpeg", "image/jpg", "image/webp"] as const)(
      "accepts supported image type %s",
      (type) => {
        const result = v.safeParse(
          newsFormSchema,
          validForm({ image: new File(["image"], "cover", { type }) })
        )

        expect(result.success).toBe(true)
      }
    )

    it("allows the image-size limit and rejects the first byte above it", () => {
      const atLimit = v.safeParse(
        newsFormSchema,
        validForm({
          image: new File([new Uint8Array(MAX_IMAGE_UPLOAD_BYTES)], "cover.png", {
            type: "image/png",
          }),
        })
      )
      expect(atLimit.success).toBe(true)

      const overLimit = v.safeParse(
        newsFormSchema,
        validForm({
          image: new File([new Uint8Array(MAX_IMAGE_UPLOAD_BYTES + 1)], "cover.png", {
            type: "image/png",
          }),
        })
      )

      expect(overLimit.success).toBe(false)
      if (overLimit.success) return
      expect(overLimit.issues.map((issue) => issue.message)).toContain("Max image size is 5MB.")
    })
  })

  describe("news route search values", () => {
    it.each(["newest", "popular"] as const)("preserves the %s sort in search params", (sort) => {
      expect(v.parse(newsSearchSchema, { q: "campus", cat: "saved", sort })).toEqual({
        q: "campus",
        cat: "saved",
        sort,
      })
    })

    it("rejects a sort mode the news route does not support", () => {
      expect(v.safeParse(newsSearchSchema, { sort: "oldest" }).success).toBe(false)
    })
  })
})
