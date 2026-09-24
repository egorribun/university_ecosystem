import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { HttpResponse, http } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/api/notifications", async () => {
  const actual = await vi.importActual<typeof import("@/api/notifications")>("@/api/notifications")
  return { ...actual, announcePlatformRelease: vi.fn(actual.announcePlatformRelease) }
})

import { announcePlatformRelease, isReleaseVersion } from "@/api/notifications"
import i18n from "@/i18n/config"
import { server } from "@/tests/mocks/server"
import { ReleaseAnnouncementCard } from "../ReleaseAnnouncementCard"

const RELEASES = "*/api/v1/push/admin/releases"

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ReleaseAnnouncementCard />
    </QueryClientProvider>
  )
  return userEvent.setup()
}

function captureRelease(response: () => Response) {
  const bodies: unknown[] = []
  server.use(
    http.post(RELEASES, async ({ request }) => {
      bodies.push(await request.json())
      return response()
    })
  )
  return bodies
}

describe("isReleaseVersion", () => {
  it.each(["1.4.0", "0.0.1", "2.0.0-rc.1", "10.20.300-beta-2"])("accepts %s", (value) => {
    expect(isReleaseVersion(value)).toBe(true)
  })

  it.each(["", "1.4", "v1.4.0", "1.4.0-", "1.4.0+build", "1.4.0 beta", "12345.0.0", "1.4.0-.x"])(
    "rejects %s",
    (value) => {
      expect(isReleaseVersion(value)).toBe(false)
    }
  )
})

describe("ReleaseAnnouncementCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("explains the format until the field is left with an invalid version", async () => {
    const user = renderCard()
    expect(
      screen.getByText("Semantic version, for example 1.4.0 or 2.0.0-rc.1.")
    ).toBeInTheDocument()

    await user.type(screen.getByLabelText("Version"), "v1")
    expect(screen.queryByText("Enter a semantic version such as 1.4.0.")).toBeNull()
    await user.tab()

    expect(screen.getByText("Enter a semantic version such as 1.4.0.")).toBeInTheDocument()
  })

  it("blocks submission until the version is semantic", async () => {
    const bodies = captureRelease(() =>
      HttpResponse.json({ version: "1.4.0", created: 1, already_announced: false })
    )
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    expect(screen.getByText("Enter a semantic version such as 1.4.0.")).toBeInTheDocument()
    expect(bodies).toEqual([])
  })

  it("announces the trimmed version with the provided notes", async () => {
    const bodies = captureRelease(() =>
      HttpResponse.json({ version: "1.4.0", created: 12, already_announced: false })
    )
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), " 1.4.0 ")
    await user.type(screen.getByLabelText("Release notes (Russian, optional)"), "Новый мессенджер")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    const outcome = await screen.findByRole("alert")
    expect(outcome).toHaveTextContent("Version 1.4.0 announced to 12 users.")
    expect(outcome.className).toContain("text-(--success-bg)")
    expect(bodies).toEqual([{ version: "1.4.0", notes_ru: "Новый мессенджер" }])
  })

  it.each([
    [0, "Version 1.4.0 was already announced; nobody new needed the notification."],
    [3, "Version 1.4.0 was already announced; 3 users who missed it were notified."],
  ])("reports a repeated version with %s new recipients", async (created, message) => {
    captureRelease(() => HttpResponse.json({ version: "1.4.0", created, already_announced: true }))
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    const outcome = await screen.findByRole("alert")
    expect(outcome).toHaveTextContent(message)
    expect(outcome.className).toContain("text-(--brand-main)")
  })

  it("omits blank notes from the request", async () => {
    const bodies = captureRelease(() =>
      HttpResponse.json({ version: "1.4.0", created: 1, already_announced: false })
    )
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.type(screen.getByLabelText("Release notes (Russian, optional)"), "   ")
    await user.type(screen.getByLabelText("Release notes (English, optional)"), " Notes ")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    await screen.findByRole("alert")
    expect(bodies).toEqual([{ version: "1.4.0", notes_en: "Notes" }])
  })

  it("explains rate limiting and clears the error when the form changes", async () => {
    captureRelease(() => HttpResponse.json({ detail: { error: "rate_limited" } }, { status: 429 }))
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.click(screen.getByRole("button", { name: "Announce release" }))
    expect(await screen.findByText("Too many announcements. Try again later.")).toBeInTheDocument()

    await user.type(screen.getByLabelText("Version"), "1")
    await waitFor(() =>
      expect(screen.queryByText("Too many announcements. Try again later.")).toBeNull()
    )
  })

  it("shows the server message for other failures", async () => {
    captureRelease(() =>
      HttpResponse.json({ detail: { error: "forbidden", message: "Admins only" } }, { status: 403 })
    )
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    expect(await screen.findByText("Admins only")).toBeInTheDocument()
  })

  it.each([
    [400, { detail: "Bad version" }, "Bad version"],
    [500, { detail: { error: "boom" } }, "Failed to announce the release."],
    [500, { unexpected: true }, "Failed to announce the release."],
  ])("maps a %s response to a readable error", async (status, body, message) => {
    captureRelease(() => HttpResponse.json(body, { status }))
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    const outcome = await screen.findByRole("alert")
    expect(outcome).toHaveTextContent(message)
    expect(outcome.className).toContain("text-(--error-text)")
  })

  it("reports a non-HTTP failure such as a rejected response contract", async () => {
    // The wrapper's own contract rejection is covered in api/__tests__; MSW
    // responses must stay contract-valid for the global validator.
    vi.mocked(announcePlatformRelease).mockRejectedValueOnce(new Error("Invalid response"))
    const user = renderCard()

    await user.type(screen.getByLabelText("Version"), "1.4.0")
    await user.click(screen.getByRole("button", { name: "Announce release" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to announce the release.")
  })
})
