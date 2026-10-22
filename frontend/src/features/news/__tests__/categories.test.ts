import { describe, expect, it } from "vitest"
import { inferCategory, inferNewsCategory } from "../categories"

const RUSSIAN_TITLE = "ГУУ вошёл в топ-20 лучших университетов страны"
const RUSSIAN_CONTENT =
  "Научных публикаций стало больше; гранты и стипендии поддерживают исследования."
const ENGLISH_TITLE = "GUU ranks among the country's top 20 universities"
const ENGLISH_CONTENT = "Research publications helped raise the result."

describe("inferNewsCategory", () => {
  it("keeps a mixed-keyword article in Science for RU and EN API responses", () => {
    const russianResponse = {
      title: RUSSIAN_TITLE,
      content: RUSSIAN_CONTENT,
      title_en: ENGLISH_TITLE,
      content_en: ENGLISH_CONTENT,
    }
    const englishResponse = {
      ...russianResponse,
      title: ENGLISH_TITLE,
      content: ENGLISH_CONTENT,
    }

    expect(inferCategory(russianResponse.title, russianResponse.content)).toBe("education")
    expect(inferCategory(englishResponse.title, englishResponse.content)).toBe("science")
    expect(inferNewsCategory(russianResponse)).toBe("science")
    expect(inferNewsCategory(englishResponse)).toBe("science")
  })

  it.each([
    ["missing translations", null, undefined],
    ["blank translations", "  ", "   "],
  ] as const)("falls back to the localized primary fields for %s", (_label, titleEn, contentEn) => {
    expect(
      inferNewsCategory({
        title: "Лекция для студентов",
        content: "Расписание экзамена и семинара",
        title_en: titleEn,
        content_en: contentEn,
      })
    ).toBe("education")
  })

  it("falls back per field when only one English translation is available", () => {
    expect(
      inferNewsCategory({
        title: RUSSIAN_TITLE,
        content: "Научных публикаций стало больше.",
        title_en: ENGLISH_TITLE,
        content_en: "   ",
      })
    ).toBe("science")
  })
})
