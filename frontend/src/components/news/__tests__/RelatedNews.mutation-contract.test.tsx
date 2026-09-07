import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const translationState = vi.hoisted(() => ({ namespaces: [] as unknown[] }))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationState.namespaces.push(namespaces)
    return {
      t: (key: string, options?: { title?: string }) =>
        options?.title ? `${key}:${options.title}` : key,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    params,
    ...rest
  }: { children?: ReactNode; params?: { id?: string } } & Record<string, unknown>) => (
    <a href={`/news/${params?.id ?? ""}`} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: (props: { srcRaw?: string; alt?: string; sizes?: string; className?: string }) => (
    <img {...props} src={props.srcRaw} alt={props.alt ?? ""} />
  ),
}))

vi.mock("@/components/news/NewsCategoryBadge", () => ({
  NewsCategoryBadge: ({ category }: { category: string }) => (
    <span data-testid="category-badge">{category}</span>
  ),
}))

vi.mock("@/features/news/categories", () => ({
  inferCategory: () => "science",
}))

vi.mock("@/utils/date", () => ({
  getMoscowDate: (value: string) => `DATE:${value}`,
}))

import type { NewsItem } from "@/api/news"
import { RelatedNews } from "@/components/news/RelatedNews"

const withImage = {
  id: "n1",
  title: "Лаборатория",
  title_en: "Laboratory",
  content: "Описание",
  created_at: "2026-05-20T09:00:00Z",
  image_url: "https://example.test/news.png",
} as unknown as NewsItem

const withoutImage = {
  ...withImage,
  id: "n2",
  title: "Без изображения",
  title_en: "No image",
  image_url: null,
  created_at: null,
} as unknown as NewsItem

describe("RelatedNews mutation contracts", () => {
  beforeEach(() => {
    translationState.namespaces = []
  })

  it("keeps namespace, heading, card, image, and date contracts exact", () => {
    render(<RelatedNews items={[withImage, withoutImage]} />)

    expect(translationState.namespaces).toContainEqual(["news"])
    expect(translationState.namespaces).toContainEqual(["news", "common"])
    expect(screen.getByRole("region", { name: "news:related.title" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "news:related.title" })).toBeInTheDocument()

    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute("href", "/news/n1")
    expect(links[0]).toHaveClass(
      "group",
      "flex",
      "flex-col",
      "rounded-xl",
      "overflow-hidden",
      "card-matte",
      "glass-noise",
      "border",
      "border-glass-border/(--opacity-soft)",
      "transition-all",
      "duration-base",
      "hover:shadow-premium-lift",
      "hover:-translate-y-1"
    )
    expect(screen.getByRole("img", { name: "news:alt.hero:Laboratory" })).toHaveAttribute(
      "sizes",
      "(min-width: 640px) 33vw, 100vw"
    )
    expect(screen.getByText("DATE:2026-05-20T09:00:00Z")).toHaveClass(
      "text-[11px]",
      "font-medium",
      "uppercase",
      "tracking-wider"
    )
    expect(screen.getAllByTestId("category-badge")).toHaveLength(2)
    expect(screen.getAllByTestId("category-badge")[0]).toHaveTextContent("science")
    expect(links[1]?.querySelector("svg")).toBeInTheDocument()
    expect(screen.queryByText(/DATE:null/)).not.toBeInTheDocument()
  })

  it("returns no region for an empty related collection", () => {
    const { container } = render(<RelatedNews items={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("uses localized fallback alt text and omits a missing date", () => {
    const sparse = { ...withImage, title: "", title_en: "", created_at: null }
    render(<RelatedNews items={[sparse as unknown as NewsItem]} />)
    expect(screen.getByRole("img", { name: "news:alt.heroFallback" })).toBeInTheDocument()
    expect(screen.queryByText(/DATE:/)).not.toBeInTheDocument()
  })
})
