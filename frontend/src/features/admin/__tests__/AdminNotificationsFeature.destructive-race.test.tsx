import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { LanguageProvider } from "@/contexts/LanguageContext"
import { adminDeadLetterQueueQueryKey } from "@/api/hooks/adminNotifications"
import { fetchDeadLetterQueue, purgeDeadLetterJobs } from "@/api/notifications"
import { AdminNotificationsFeature } from "../AdminNotificationsFeature"

vi.mock("@/api/notifications", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/notifications")>()
  return {
    ...actual,
    fetchDeadLetterQueue: vi.fn(),
    purgeDeadLetterJobs: vi.fn(),
  }
})

type Queue = Awaited<ReturnType<typeof fetchDeadLetterQueue>>

const jobId = "11111111-1111-4111-8111-111111111111"
const queue: Queue = {
  items: [
    {
      id: jobId,
      record_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      kind: "event",
      locale: "en",
      enqueued_at: "2026-10-02T12:00:00Z",
      attempts: 2,
      last_error: "Delivery failed",
    },
  ],
  total: 1,
}

const clients: QueryClient[] = []

function renderFeature() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  clients.push(queryClient)
  window.localStorage.setItem("ue:language", "en")
  render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <AdminNotificationsFeature />
      </LanguageProvider>
    </QueryClientProvider>
  )
  return { queryClient, user: userEvent.setup() }
}

beforeEach(() => {
  vi.mocked(fetchDeadLetterQueue).mockReset().mockResolvedValue(queue)
  vi.mocked(purgeDeadLetterJobs).mockReset()
})

afterEach(() => {
  cleanup()
  for (const client of clients.splice(0)) client.clear()
})

describe("admin notification purge races", () => {
  it("drops a confirmed job that disappears before the destructive action runs", async () => {
    const { queryClient, user } = renderFeature()
    await waitFor(() => {
      expect(queryClient.getQueryData(adminDeadLetterQueueQueryKey)).toEqual(queue)
    })

    await user.click(screen.getByRole("checkbox", { name: "Select job " + jobId }))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()

    await act(async () => {
      queryClient.setQueryData(adminDeadLetterQueueQueryKey, { items: [], total: 0 })
    })
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: /delete|purge/i })
    )

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    expect(purgeDeadLetterJobs).not.toHaveBeenCalled()
  })

  it("sends one purge request when the confirmation receives duplicate clicks", async () => {
    let resolvePurge!: (value: Awaited<ReturnType<typeof purgeDeadLetterJobs>>) => void
    const pendingPurge = new Promise<Awaited<ReturnType<typeof purgeDeadLetterJobs>>>((resolve) => {
      resolvePurge = resolve
    })
    vi.mocked(purgeDeadLetterJobs).mockReturnValueOnce(pendingPurge)

    const { queryClient, user } = renderFeature()
    await waitFor(() => {
      expect(queryClient.getQueryData(adminDeadLetterQueueQueryKey)).toEqual(queue)
    })

    await user.click(screen.getByRole("checkbox", { name: "Select job " + jobId }))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))
    const confirmButton = within(screen.getByRole("alertdialog")).getByRole("button", {
      name: /delete|purge/i,
    })

    await act(async () => {
      confirmButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      confirmButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    await waitFor(() => expect(purgeDeadLetterJobs).toHaveBeenCalledTimes(1))
    expect(purgeDeadLetterJobs).toHaveBeenCalledExactlyOnceWith([jobId])

    await act(async () => {
      resolvePurge(undefined as unknown as Awaited<ReturnType<typeof purgeDeadLetterJobs>>)
    })
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
  })
  it("disables purge controls while confirming and disables cancel during the request", async () => {
    let resolvePurge!: (value: Awaited<ReturnType<typeof purgeDeadLetterJobs>>) => void
    const pendingPurge = new Promise<Awaited<ReturnType<typeof purgeDeadLetterJobs>>>((resolve) => {
      resolvePurge = resolve
    })
    vi.mocked(purgeDeadLetterJobs).mockReturnValueOnce(pendingPurge)

    const { queryClient, user } = renderFeature()
    await waitFor(() => {
      expect(queryClient.getQueryData(adminDeadLetterQueueQueryKey)).toEqual(queue)
    })

    await user.click(screen.getByRole("checkbox", { name: "Select job " + jobId }))
    await user.click(screen.getByRole("button", { name: "Delete selected" }))

    const dialog = screen.getByRole("alertdialog")
    const cancelButton = within(dialog).getByRole("button", { name: /cancel/i })
    expect(cancelButton).toBeEnabled()
    expect(screen.getByRole("button", { name: "Delete selected" })).toBeDisabled()
    expect(
      within(screen.getByRole("table", { name: "Dead-letter queue" })).getByRole("button", {
        name: "Delete",
      })
    ).toBeDisabled()

    await user.click(within(dialog).getByRole("button", { name: /delete|purge/i }))
    await waitFor(() => expect(purgeDeadLetterJobs).toHaveBeenCalledOnce())

    expect(cancelButton).toBeDisabled()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()

    await act(async () => {
      resolvePurge(undefined as unknown as Awaited<ReturnType<typeof purgeDeadLetterJobs>>)
    })
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
    await waitFor(() => expect(queryClient.isMutating()).toBe(0))
  })
})
