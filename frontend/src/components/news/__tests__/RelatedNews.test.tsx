import { screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import { RelatedNews } from "@/components/news/RelatedNews"
import type { NewsItem } from "@/api/news"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const ITEMS = [
  {
    id: "n1",
    title: "Новая исследовательская лаборатория",
    title_en: "New Interdisciplinary Research Lab",
    content: "Lab opens this spring.",
    created_at: "2026-05-20T09:00:00Z",
    image_url: "https://picsum.photos/seed/related-n1/400/300",
    image_url_optimized: null,
  },
  {
    id: "n2",
    title: "Старт набора в студсовет",
    title_en: "Student council applications open",
    content: "Apply by month end.",
    created_at: "2026-05-18T09:00:00Z",
    image_url: null,
    image_url_optimized: null,
  },
] as unknown as NewsItem[]

const extraRoutes = [{ path: "/news/$id", Component: () => <div>News detail</div> }]

describe("RelatedNews", () => {
  it("renders one linked card per item", async () => {
    await renderWithRouter({ ui: () => <RelatedNews items={ITEMS} />, extraRoutes })
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(ITEMS.length)
    expect(links[0]!.getAttribute("href")).toContain("/news/n1")
    expect(links[1]!.getAttribute("href")).toContain("/news/n2")
  })

  it("renders nothing when there are no related items", async () => {
    await renderWithRouter({ ui: () => <RelatedNews items={[]} />, extraRoutes })
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("uses empty-title and missing-date fallbacks for sparse related items", async () => {
    const sparse = {
      ...ITEMS[0],
      id: "sparse",
      title: "",
      title_en: "",
      created_at: null,
    } as unknown as NewsItem

    await renderWithRouter({ ui: () => <RelatedNews items={[sparse]} />, extraRoutes })

    expect(screen.getByRole("img", { name: "News cover image" })).toBeInTheDocument()
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument()
  })
})
