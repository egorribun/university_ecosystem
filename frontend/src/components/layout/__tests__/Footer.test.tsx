import { describe, expect, it } from "vitest"

import Footer from "@/components/layout/Footer"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// Wave 176 SW5 — Footer regression tests. Mounted via `renderWithRouter`
// helper (Wave 114 SW1) so TanStack Router's `<Link>` + `data-status`
// attribute resolve correctly. Covers:
//   • Render contract (ARIA role, brand text, 7 footer-link-premium links,
//     copyright year)
//   • Social buttons (aria-labels, security attrs target+rel)
//   • Decorative layers aria-hidden (FooterBackdrop, accent stripe)
//   • Active-route indicator via data-status="active" (TanStack canonical)
//   • Prefix-match active state (W176 SW4 activeOptions={{ exact: false }})

/**
 * Locale-agnostic link finder. Searches by `href` attribute prefix only —
 * intentionally does NOT match by visible text, because i18n locale can
 * flip between EN ("Dashboard") and RU ("Главная") depending on test-env
 * initial language. Text-based matching is covered by i18n parity tests.
 */
const findLinkByHref = (container: HTMLElement, hrefStartsWith: string): HTMLAnchorElement => {
  const anchors = container.querySelectorAll("a.footer-link-premium")
  for (const a of Array.from(anchors)) {
    const href = a.getAttribute("href") ?? ""
    if (href.startsWith(hrefStartsWith)) return a as HTMLAnchorElement
  }
  throw new Error(`Could not find <Link> with href starting "${hrefStartsWith}"`)
}

describe("Footer", () => {
  it("renders with role=contentinfo and brand block", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    const footer = container.querySelector("footer[role='contentinfo']")
    expect(footer).toBeTruthy()

    // Brand heading <h2> with brand name
    const h2 = container.querySelector("h2")
    expect(h2?.textContent?.trim().length ?? 0).toBeGreaterThan(0)
  })

  it("renders all 7 footer navigation links with footer-link-premium class", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    const links = container.querySelectorAll("a.footer-link-premium")
    // Navigation column: dashboard + news + schedule + events + map (5)
    // Profile column: profile + settings (2)
    // Total: 7
    expect(links.length).toBe(7)

    // Spot-check href attributes — they must start with the expected route
    findLinkByHref(container, "/dashboard")
    findLinkByHref(container, "/news")
    findLinkByHref(container, "/schedule")
    findLinkByHref(container, "/events")
    findLinkByHref(container, "/map")
    findLinkByHref(container, "/profile")
    findLinkByHref(container, "/settings")
  })

  it("renders copyright with the current year", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    const currentYear = new Date().getFullYear()
    const copyright = Array.from(container.querySelectorAll("p")).find((p) =>
      p.textContent?.includes(`${currentYear}`)
    )
    expect(copyright).toBeTruthy()
  })

  it("renders 2 social buttons (Telegram + Email) with aria-labels + security attrs", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    const socials = container.querySelectorAll("a.footer-social-btn")
    expect(socials.length).toBe(2)

    const telegram = Array.from(socials).find((link) =>
      link.getAttribute("href")?.startsWith("https://t.me/")
    )
    const email = Array.from(socials).find(
      (link) => link.getAttribute("href") === "mailto:inf@guu.ru"
    )

    expect(telegram).toHaveAttribute("target", "_blank")
    expect(telegram).toHaveAttribute("rel", expect.stringContaining("noopener"))
    expect(telegram).toHaveAccessibleName(/opens in a new tab|новой вкладке/i)
    expect(telegram?.querySelector("svg[data-icon='telegram']")).toBeInTheDocument()

    expect(email).toBeInTheDocument()
    expect(email).not.toHaveAttribute("target")
    expect(email).toHaveAccessibleName(/send an email|отправить письмо/i)

    for (const link of Array.from(socials)) {
      expect(link).toHaveClass("min-h-11", "min-w-11")
    }
  })

  it("uses a filled four-track grid without media-query-driven glow", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    expect(container.querySelector(".grid")).toHaveClass("@lg:grid-cols-4")
    expect(container.querySelector("[style*='radial-gradient']")).not.toBeInTheDocument()
    expect(container.querySelector(".footer-stagger-item")).not.toBeInTheDocument()
  })

  it("marks the static accent divider as decorative", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    expect(container.querySelector("footer > .footer-accent-stripe")).toHaveAttribute(
      "aria-hidden",
      "true"
    )
  })

  it("applies data-status='active' to /dashboard link when mounted on /dashboard", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/dashboard" })

    const link = findLinkByHref(container, "/dashboard")
    expect(link.dataset.status).toBe("active")
  })

  it("applies data-status='active' to /news link when on /news article via prefix-match", async () => {
    // activeOptions={{ exact: false }} should mark /news active on /news/$slug
    const { container } = await renderWithRouter({
      ui: Footer,
      path: "/news/$slug",
      initialPath: "/news/sample-article",
    })

    const link = findLinkByHref(container, "/news")
    expect(link.dataset.status).toBe("active")
  })

  it("does NOT mark inactive links with data-status='active'", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/dashboard" })

    // /events link should NOT have data-status="active" when on /dashboard
    const events = findLinkByHref(container, "/events")
    expect(events.dataset.status).toBeUndefined()

    const schedule = findLinkByHref(container, "/schedule")
    expect(schedule.dataset.status).toBeUndefined()
  })
})
