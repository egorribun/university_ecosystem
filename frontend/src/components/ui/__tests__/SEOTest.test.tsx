import { act, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { SEO, SeoReadinessProvider, usePageSeoReady } from "../SEO"
import {
  registerSeoReadinessInstance,
  unregisterSeoReadinessInstance,
} from "../seoReadinessRegistry"

describe("SEO Component", () => {
  it("renders with title only", () => {
    render(<SEO title="Home" />)
    expect(document.title).toBe("Home | University Ecosystem")
  })

  it("renders with all props (title, description, image, type)", () => {
    render(
      <SEO
        title="Custom Page"
        description="This is a test description"
        image="https://example.com/image.png"
        type="article"
      />
    )
    expect(document.title).toBe("Custom Page | University Ecosystem")
  })

  it("renders every social metadata field with the supplied values", () => {
    render(
      <SEO
        title="Article"
        description="A complete description"
        image="https://example.com/cover.png"
        type="article"
      />
    )

    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[property="og:type"]')).toHaveAttribute(
      "content",
      "article"
    )
    expect(document.head.querySelector('meta[property="og:description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
      "content",
      "https://example.com/cover.png"
    )
    expect(document.head.querySelector('meta[name="twitter:description"]')).toHaveAttribute(
      "content",
      "A complete description"
    )
    expect(document.head.querySelector('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      "https://example.com/cover.png"
    )
    expect(document.head.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary_large_image"
    )
  })

  it("uses localized root description and image fallbacks when optional metadata is absent", async () => {
    const originalLanguage = i18n.language
    await act(async () => {
      await i18n.changeLanguage("en")
    })

    render(<SEO title="Minimal" />)

    const englishDescription = i18n.t("navigation:brandDescription")
    const englishSocialDescription = i18n.t("navigation:socialDescription")
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      englishDescription
    )
    expect(document.head.querySelector('meta[property="og:description"]')).toHaveAttribute(
      "content",
      englishSocialDescription
    )
    expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
      "content",
      "/og-image.png"
    )
    expect(document.head.querySelector('meta[name="twitter:description"]')).toHaveAttribute(
      "content",
      englishSocialDescription
    )
    expect(document.head.querySelector('meta[name="twitter:image"]')).toHaveAttribute(
      "content",
      "/og-image.png"
    )

    await act(async () => {
      await i18n.changeLanguage("ru")
    })
    await waitFor(() => {
      expect(document.head.querySelector('meta[name="description"]')).toHaveAttribute(
        "content",
        i18n.t("navigation:brandDescription")
      )
    })

    await act(async () => {
      await i18n.changeLanguage(originalLanguage)
    })
  })

  it("defaults the Open Graph type to website", () => {
    render(<SEO title="Home" />)

    expect(document.head.querySelector('meta[property="og:type"]')).toHaveAttribute(
      "content",
      "website"
    )
  })
})

function SeoReadinessProbe() {
  const ready = usePageSeoReady()
  return <output data-testid="seo-readiness">{ready ? "ready" : "not-ready"}</output>
}

describe("SEO readiness registry", () => {
  it("keeps duplicate registration idempotent", () => {
    const empty = new Set<string>()
    const registered = registerSeoReadinessInstance(empty, "page")

    expect(registered).not.toBe(empty)
    expect([...registered]).toEqual(["page"])
    expect([...empty]).toEqual([])
    const beforeDuplicateRegistration = [...registered]
    const duplicateRegistration = registerSeoReadinessInstance(registered, "page")
    expect(duplicateRegistration).toBe(registered)
    expect([...duplicateRegistration]).toEqual(beforeDuplicateRegistration)
  })

  it("keeps absent unregistration idempotent and removes registered instances immutably", () => {
    const current = new Set(["root", "page"])

    const beforeAbsentUnregister = [...current]
    const absentUnregister = unregisterSeoReadinessInstance(current, "absent")
    expect(absentUnregister).toBe(current)
    expect([...absentUnregister]).toEqual(beforeAbsentUnregister)
    const next = unregisterSeoReadinessInstance(current, "page")
    expect(next).not.toBe(current)
    expect([...next]).toEqual(["root"])
    expect([...current]).toEqual(["root", "page"])
  })

  it("updates provider readiness when an SEO instance mounts and unmounts", () => {
    const { rerender } = render(
      <SeoReadinessProvider>
        <SeoReadinessProbe />
        <SEO title="Lifecycle" />
      </SeoReadinessProvider>
    )

    expect(screen.getByTestId("seo-readiness")).toHaveTextContent("ready")

    rerender(
      <SeoReadinessProvider>
        <SeoReadinessProbe />
      </SeoReadinessProvider>
    )

    expect(screen.getByTestId("seo-readiness")).toHaveTextContent("not-ready")
  })
})
