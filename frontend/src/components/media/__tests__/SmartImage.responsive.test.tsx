import { act, StrictMode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { expect, it } from "vitest"

import SmartImage from "@/components/media/SmartImage"
import NewsCardHero from "@/components/news/NewsCardHero"
import { StoryList } from "@/components/stories/StoryList"
import type { DashboardStory } from "@/hooks/useDashboardStories"

const exampleStory: DashboardStory = {
  id: "story-fixture",
  title: "A dashboard story",
  short_text: "A fixture",
  created_at: "2026-01-15T10:00:00Z",
  published_at: "2026-01-15T10:00:00Z",
  expires_at: "2027-01-15T10:00:00Z",
  is_active: true,
}

function OrdinaryMedia({ origin }: { origin: string }) {
  return (
    <StrictMode>
      <StoryList
        stories={[
          {
            ...exampleStory,
            cover_url: `${origin}/api/v1/img/story_covers/demo_fixture.webp`,
          },
        ]}
        onOpenStory={() => undefined}
      />
      <NewsCardHero
        image_url={`${origin}/api/v1/img/news_images/demo_fixture.webp`}
        title="A news item"
        created_at=""
        priority
      />
    </StrictMode>
  )
}

function renderOnServer(origin: string): string {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window")!
  Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
  try {
    return renderToString(<OrdinaryMedia origin={origin} />)
  } finally {
    Object.defineProperty(globalThis, "window", originalWindow)
  }
}

it("keeps ordinary dashboard and news images valid through SSR and hydration", async () => {
  const origin = window.location.origin
  const container = document.createElement("div")
  const recoverableErrors: unknown[] = []
  let root: Root | undefined
  container.innerHTML = renderOnServer(origin)

  const checkImages = () => {
    const images = container.querySelectorAll("img")
    expect(images).toHaveLength(2)
    expect(images[0]).toHaveAttribute("src", `${origin}/api/v1/img/story_covers/demo_fixture.webp`)
    expect(images[1]).toHaveAttribute("src", `${origin}/api/v1/img/news_images/demo_fixture.webp`)
    for (const image of images) {
      expect(image).not.toHaveAttribute("srcset")
      expect(image).not.toHaveAttribute("sizes")
    }
  }

  try {
    checkImages()
    document.body.append(container)
    await act(async () => {
      root = hydrateRoot(container, <OrdinaryMedia origin={origin} />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })
    checkImages()
    expect(recoverableErrors).toEqual([])

    const story = within(container).getByAltText("A dashboard story")
    fireEvent.error(story)
    expect(new URL(story.getAttribute("src")!, origin).pathname).toBe("/fallbacks/placeholder.png")
    expect(story).not.toHaveAttribute("srcset")
    expect(story).not.toHaveAttribute("sizes")
  } finally {
    await act(async () => root?.unmount())
    container.remove()
  }
})

it.each([
  { label: "same-origin proxy", url: "/api/v1/img/story_covers/demo_fixture.webp" },
  { label: "external image", url: "https://images.example.test/photo.webp" },
  {
    label: "signed image",
    url: "https://images.example.test/photo.webp?policy=read&signature=demo",
  },
])("omits identical candidates for $label without changing the source", ({ url }) => {
  // Absolute proxy URLs are the form emitted by the ordinary S3-backed fixture.
  const source = url.startsWith("/") ? `${window.location.origin}${url}` : url
  const { rerender } = render(<SmartImage srcRaw={source} alt="image" />)
  const image = screen.getByRole("img", { name: "image" })
  expect(image).toHaveAttribute("src", source)
  expect(image).not.toHaveAttribute("srcset")
  expect(image).not.toHaveAttribute("sizes")

  rerender(<SmartImage srcRaw={source} responsiveWidths={[400]} alt="image" />)
  expect(image).toHaveAttribute("src", source)
  expect(image).not.toHaveAttribute("srcset")
  expect(image).not.toHaveAttribute("sizes")
})

it("retains single and multiple relative proxy width candidates", () => {
  const { rerender } = render(
    <SmartImage srcRaw="/media/photo.webp" responsiveWidths={[400]} alt="image" />
  )
  const image = screen.getByRole("img", { name: "image" })
  expect(image).toHaveAttribute("srcset", "/api/v1/img/media/photo.webp?w=400 400w")
  expect(image).toHaveAttribute("sizes")

  rerender(<SmartImage srcRaw="/media/photo.webp" responsiveWidths={[800, 400]} alt="image" />)
  expect(image).toHaveAttribute(
    "srcset",
    "/api/v1/img/media/photo.webp?w=400 400w, /api/v1/img/media/photo.webp?w=800 800w"
  )
  expect(image).toHaveAttribute("sizes")

  // A relative proxy URL may already contain its sole requested width.
  rerender(
    <SmartImage srcRaw="/api/v1/img/media/photo.webp?w=400" responsiveWidths={[400]} alt="image" />
  )
  expect(image).toHaveAttribute("srcset", "/api/v1/img/media/photo.webp?w=400 400w")
  expect(image).toHaveAttribute("sizes")

  rerender(
    <SmartImage srcRaw="/api/v1/img/media/photo.webp?w=1" responsiveWidths={[1]} alt="image" />
  )
  expect(image).toHaveAttribute("srcset", "/api/v1/img/media/photo.webp?w=1 1w")
})
