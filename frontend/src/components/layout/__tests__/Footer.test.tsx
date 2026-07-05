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

    // Each social link must have aria-label, target=_blank, rel="noopener noreferrer"
    for (const a of Array.from(socials)) {
      expect(a.getAttribute("aria-label")?.length ?? 0).toBeGreaterThan(0)
      expect(a.getAttribute("target")).toBe("_blank")
      expect(a.getAttribute("rel")).toContain("noopener")
      expect(a.getAttribute("rel")).toContain("noreferrer")
    }

    // Confirm hrefs target Telegram + Gmail
    const hosts = Array.from(socials).map((a) => new URL((a as HTMLAnchorElement).href).hostname)
    expect(hosts).toContain("t.me")
    expect(hosts).toContain("mail.google.com")
  })

  it("marks decorative layers (FooterBackdrop, accent stripe) aria-hidden", async () => {
    const { container } = await renderWithRouter({ ui: Footer, path: "/" })

    // FooterBackdrop is a div with aria-hidden="true" containing 3 orbs
    const ariaHiddenDivs = container.querySelectorAll(
      "footer > div[aria-hidden='true'], footer > .footer-accent-stripe[aria-hidden='true']"
    )
    // Should find at least FooterBackdrop wrapper + accent stripe
    expect(ariaHiddenDivs.length).toBeGreaterThanOrEqual(2)
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
