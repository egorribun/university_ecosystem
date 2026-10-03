import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { notifyManager, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosHeaders } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { LanguageProvider } from "@/contexts/LanguageContext"
import i18n from "@/i18n/config"
import { CANONICAL_NOTIFICATION_TOPICS } from "@/notifications/contract"
import { adminDeadLetterQueueQueryKey } from "@/api/hooks/adminNotifications"
import {
  fetchAdminUserTopics,
  fetchDeadLetterQueue,
  purgeDeadLetterJobs,
  retryDeadLetterJobs,
  updateAdminUserTopics,
} from "@/api/notifications"
import { AdminNotificationsFeature } from "../AdminNotificationsFeature"

vi.mock("@/api/notifications", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/notifications")>()
  return {
    ...actual,
    fetchAdminUserTopics: vi.fn(),
    fetchDeadLetterQueue: vi.fn(),
    purgeDeadLetterJobs: vi.fn(),
    retryDeadLetterJobs: vi.fn(),
    updateAdminUserTopics: vi.fn(),
  }
})

type Topics = Awaited<ReturnType<typeof fetchAdminUserTopics>>
type Queue = Awaited<ReturnType<typeof fetchDeadLetterQueue>>

const topics: Topics = {
  user_id: "11111111-1111-4111-8111-111111111111",
  email: "student@example.com",
  allowed_topics: ["news.published", "events.published"],
  topics: ["news.published"],
}

const queue: Queue = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      record_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      kind: "event",
      locale: "en",
      enqueued_at: "2026-10-02T12:00:00Z",
      attempts: 2,
      last_error: "Delivery failed",
    },
    {
      id: "22222222-2222-4222-8222-222222222222",
      record_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      kind: "news",
      locale: "ru",
      enqueued_at: "2026-10-01T12:00:00Z",
      attempts: 3,
      last_error: "Delivery failed",
    },
  ],
  total: 2,
}

const clients: QueryClient[] = []

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function renderFeature(language: "en" | "ru" = "en") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  clients.push(queryClient)
  window.localStorage.setItem("ue:language", language)
  render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <AdminNotificationsFeature />
      </LanguageProvider>
    </QueryClientProvider>
  )
  return { queryClient, user: userEvent.setup() }
}

async function settleQueue(queryClient: QueryClient) {
  await waitFor(() => {
    expect(queryClient.isMutating()).toBe(0)
    expect(queryClient.isFetching({ queryKey: adminDeadLetterQueueQueryKey })).toBe(0)
  })
  await act(async () => {
    await new Promise<void>((resolve) => notifyManager.schedule(resolve))
  })
}

async function loadTopics(user: ReturnType<typeof userEvent.setup>) {
  const input = screen.getByRole("textbox", { name: "User ID" })
  await user.click(input)
  await user.paste(topics.user_id)
  await user.click(screen.getByRole("button", { name: "Load topics" }))
  expect(screen.getByRole("checkbox", { name: "Published news" })).toBeChecked()
  return input
}

function queueActionResult(ids: string[]): Awaited<ReturnType<typeof retryDeadLetterJobs>> {
  return {
    data: { success: true, affected_count: ids.length, job_ids: ids },
    status: 200,
    statusText: "OK",
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  }
}

beforeEach(() => {
  vi.mocked(fetchAdminUserTopics).mockReset().mockResolvedValue(topics)
  vi.mocked(fetchDeadLetterQueue).mockReset().mockResolvedValue(queue)
  vi.mocked(updateAdminUserTopics).mockReset()
  vi.mocked(retryDeadLetterJobs).mockReset()
  vi.mocked(purgeDeadLetterJobs).mockReset()
})

afterEach(() => {
  cleanup()
  for (const client of clients.splice(0)) client.clear()
})

describe("Admin notification topic changes", () => {
  it.each([
    {
      language: "en" as const,
      inputLabel: "User ID",
      loadLabel: "Load topics",
      saveLabel: "Save topics",
      labels: [
        "Published news",
        "Schedule changes",
        "Published events",
        "Chat messages",
        "System releases",
      ],
    },
    {
      language: "ru" as const,
      inputLabel: "ID пользователя",
      loadLabel: "Загрузить темы",
      saveLabel: "Сохранить",
      labels: [
        "Опубликованные новости",
        "Изменения расписания",
        "Опубликованные мероприятия",
        "Сообщения чата",
        "Системные релизы",
      ],
    },
  ])(
    "translates canonical topics in $language without changing their saved IDs",
    async ({ language, inputLabel, loadLabel, saveLabel, labels }) => {
      const response: Topics = { ...topics, allowed_topics: [...CANONICAL_NOTIFICATION_TOPICS] }
      vi.mocked(fetchAdminUserTopics).mockResolvedValue(response)
      vi.mocked(updateAdminUserTopics).mockResolvedValue({
        ...response,
        topics: ["events.published"],
      })
      await i18n.changeLanguage(language)
      const { user } = renderFeature(language)
      await user.click(screen.getByRole("textbox", { name: inputLabel }))
      await user.paste(topics.user_id)
      await user.click(screen.getByRole("button", { name: loadLabel }))

      for (const label of labels) {
        expect(screen.getByRole("checkbox", { name: label })).toBeInTheDocument()
      }
      await user.click(screen.getByRole("checkbox", { name: labels[0]! }))
      await user.click(screen.getByRole("checkbox", { name: labels[2]! }))
      await user.click(screen.getByRole("button", { name: saveLabel }))
      expect(updateAdminUserTopics).toHaveBeenCalledExactlyOnceWith(topics.user_id, [
        "events.published",
      ])
    }
  )

  it("trims the requested user ID and prevents another load while the request is pending", async () => {
    const pending = deferred<Topics>()
    vi.mocked(fetchAdminUserTopics).mockReturnValueOnce(pending.promise)
    const { user } = renderFeature()
    const input = screen.getByRole("textbox", { name: "User ID" })
    const load = screen.getByRole("button", { name: "Load topics" })
    await user.click(input)
    await user.paste(`  ${topics.user_id}  `)
    await user.click(load)

    expect(fetchAdminUserTopics).toHaveBeenCalledExactlyOnceWith(topics.user_id)
    expect(input).toBeDisabled()
    expect(load).toBeDisabled()
    expect(load).toHaveTextContent("Loading")
    await user.click(load)
    expect(fetchAdminUserTopics).toHaveBeenCalledTimes(1)

    await act(async () => pending.resolve(topics))
    expect(input).toBeEnabled()
    expect(load).toBeEnabled()
    expect(screen.getByRole("checkbox", { name: "Published news" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Published events" })).not.toBeChecked()
    expect(screen.getByRole("alert")).toHaveTextContent(
      `Topics loaded for ${topics.email} (ID ${topics.user_id}).`
    )
  })

  it("saves only selected allowed topics for the loaded user and adopts the server response", async () => {
    const pending = deferred<Topics>()
    vi.mocked(updateAdminUserTopics).mockReturnValueOnce(pending.promise)
    const { user } = renderFeature()
    const input = await loadTopics(user)
    await user.clear(input)
    await user.paste("22222222-2222-4222-8222-222222222222")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await user.click(screen.getByRole("checkbox", { name: "Published news" }))
    await user.click(screen.getByRole("checkbox", { name: "Published events" }))
    const save = screen.getByRole("button", { name: "Save topics" })
    await user.click(save)

    expect(updateAdminUserTopics).toHaveBeenCalledExactlyOnceWith(topics.user_id, [
      "events.published",
    ])
    expect(input).toBeDisabled()
    expect(save).toBeDisabled()
    expect(screen.getByRole("button", { name: /Loading/ })).toBeDisabled()
    expect(screen.getByRole("checkbox", { name: "Published news" })).toBeDisabled()
    expect(screen.getByRole("checkbox", { name: "Published events" })).toBeDisabled()
    await user.click(save)
    expect(updateAdminUserTopics).toHaveBeenCalledTimes(1)

    await act(async () =>
      pending.resolve({
        ...topics,
        email: "updated@example.com",
        allowed_topics: ["news.published", "events.published", "schedule.changed"],
        topics: ["news.published", "schedule.changed"],
      })
    )
    expect(screen.getByRole("alert")).toHaveTextContent("Topics updated successfully.")
    expect(screen.getByText(/Managing topics for updated@example.com/)).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "Published news" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Published events" })).not.toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Schedule changes" })).toBeChecked()
    expect(save).toBeEnabled()
    expect(input).toBeEnabled()
  })

  it("clears loaded controls when a whitespace-only user ID is rejected without a request", async () => {
    const { user } = renderFeature()
    const input = await loadTopics(user)
    await user.clear(input)
    await user.paste("   ")
    await user.click(screen.getByRole("button", { name: "Load topics" }))

    expect(fetchAdminUserTopics).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a valid user ID.")
    expect(screen.queryByRole("checkbox", { name: "Published news" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save topics" })).not.toBeInTheDocument()
    await user.click(input)
    await user.paste(topics.user_id)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("clears old topics after a failed reload and resets the error when loading again", async () => {
    const failed = deferred<Topics>()
    const recovered = deferred<Topics>()
    vi.mocked(fetchAdminUserTopics)
      .mockResolvedValueOnce(topics)
      .mockReturnValueOnce(failed.promise)
      .mockReturnValueOnce(recovered.promise)
    const { user } = renderFeature()
    await loadTopics(user)
    await user.click(screen.getByRole("button", { name: "Load topics" }))
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await act(async () => failed.reject(new Error("Topic service is offline")))

    expect(screen.getByRole("alert")).toHaveTextContent("Topic service is offline")
    expect(screen.queryByRole("button", { name: "Save topics" })).not.toBeInTheDocument()
    expect(screen.queryByRole("checkbox", { name: "Published news" })).not.toBeInTheDocument()
    const load = screen.getByRole("button", { name: "Load topics" })
    expect(load).toBeEnabled()
    await user.click(load)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await act(async () => recovered.resolve({ ...topics, topics: [] }))
    expect(screen.getByRole("checkbox", { name: "Published news" })).not.toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Published events" })).not.toBeChecked()
    expect(screen.getByRole("alert")).toHaveTextContent("Topics loaded for")
  })

  it("preserves unsaved choices after a save failure and clears feedback before retrying", async () => {
    const failed = deferred<Topics>()
    const recovered = deferred<Topics>()
    vi.mocked(updateAdminUserTopics)
      .mockReturnValueOnce(failed.promise)
      .mockReturnValueOnce(recovered.promise)
    const { user } = renderFeature()
    await loadTopics(user)
    await user.click(screen.getByRole("checkbox", { name: "Published news" }))
    const save = screen.getByRole("button", { name: "Save topics" })
    await user.click(save)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await act(async () => failed.reject(new Error("Topic update failed")))

    expect(screen.getByRole("alert")).toHaveTextContent("Topic update failed")
    expect(screen.getByRole("checkbox", { name: "Published news" })).not.toBeChecked()
    expect(screen.getByRole("checkbox", { name: "Published news" })).toBeEnabled()
    expect(save).toBeEnabled()
    await user.click(save)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(updateAdminUserTopics).toHaveBeenNthCalledWith(2, topics.user_id, [])
    await act(async () => recovered.resolve({ ...topics, topics: [] }))
    expect(screen.getByRole("alert")).toHaveTextContent("Topics updated successfully.")
    expect(save).toBeEnabled()
  })
})

describe("Admin dead-letter queue actions", () => {
  it("keeps bulk actions disabled without selection and tracks partial versus complete selection", async () => {
    const { user, queryClient } = renderFeature()
    await settleQueue(queryClient)
    const all = screen.getByRole("checkbox", { name: "Select all jobs" })
    const first = screen.getByRole("checkbox", { name: `Select job ${queue.items[0]!.id}` })
    const second = screen.getByRole("checkbox", { name: `Select job ${queue.items[1]!.id}` })
    const retry = screen.getByRole("button", { name: "Retry selected" })
    const purge = screen.getByRole("button", { name: "Delete selected" })
    expect(retry).toBeDisabled()
    expect(purge).toBeDisabled()
    expect(all).not.toBeChecked()
    await user.click(first)
    expect(all).not.toBeChecked()
    expect(retry).toBeEnabled()
    expect(purge).toBeEnabled()
    await user.click(second)
    expect(all).toBeChecked()
    await user.click(first)
    expect(all).not.toBeChecked()
    await user.click(all)
    expect(first).toBeChecked()
    expect(second).toBeChecked()
    expect(all).toBeChecked()
    await user.click(all)
    expect(first).not.toBeChecked()
    expect(second).not.toBeChecked()
    expect(all).not.toBeChecked()
    expect(retry).toBeDisabled()
    expect(purge).toBeDisabled()
  })

  it.each([
    { label: "Retry selected", action: retryDeadLetterJobs },
    { label: "Delete selected", action: purgeDeadLetterJobs },
  ])(
    "locks all queue actions while $label is pending, then clears selection and refreshes jobs",
    async ({ label, action }) => {
      const pending = deferred<Awaited<ReturnType<typeof retryDeadLetterJobs>>>()
      vi.mocked(action).mockReturnValueOnce(pending.promise)
      const { user, queryClient } = renderFeature()
      await settleQueue(queryClient)
      await user.click(screen.getByRole("checkbox", { name: "Select all jobs" }))
      await user.click(screen.getByRole("button", { name: label }))
      const ids = queue.items.map((job) => job.id)
      expect(action).toHaveBeenCalledExactlyOnceWith(ids)
      for (const button of screen.getAllByRole("button", {
        name: /^(Retry|Delete)( selected)?$/,
      })) {
        expect(button).toBeDisabled()
        await user.click(button)
      }
      expect(action).toHaveBeenCalledTimes(1)

      vi.mocked(fetchDeadLetterQueue).mockResolvedValue({
        items: [
          {
            ...queue.items[0]!,
            id: "33333333-3333-4333-8333-333333333333",
            record_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            enqueued_at: "2026-10-03T12:00:00Z",
            last_error: "Delivery failed",
          },
        ],
        total: 1,
      })
      await act(async () => pending.resolve(queueActionResult(ids)))
      await settleQueue(queryClient)
      expect(fetchDeadLetterQueue).toHaveBeenCalledTimes(2)
      expect(screen.getByText("Total jobs: 1")).toBeInTheDocument()
      expect(
        screen.getByRole("checkbox", { name: "Select job 33333333-3333-4333-8333-333333333333" })
      ).not.toBeChecked()
      expect(screen.getByRole("checkbox", { name: "Select all jobs" })).not.toBeChecked()
      for (const job of queue.items) {
        expect(
          screen.queryByRole("checkbox", { name: `Select job ${job.id}` })
        ).not.toBeInTheDocument()
      }
      expect(screen.getByRole("button", { name: "Retry selected" })).toBeDisabled()
      expect(screen.getByRole("button", { name: "Delete selected" })).toBeDisabled()
      for (const button of screen.getAllByRole("button", { name: /^(Retry|Delete)$/ })) {
        expect(button).toBeEnabled()
      }
    }
  )

  it.each([
    { label: "Retry selected", action: retryDeadLetterJobs },
    { label: "Delete selected", action: purgeDeadLetterJobs },
  ])(
    "retains selection after $label fails and removes the old error when the action restarts",
    async ({ label, action }) => {
      const failed = deferred<Awaited<ReturnType<typeof retryDeadLetterJobs>>>()
      const recovered = deferred<Awaited<ReturnType<typeof retryDeadLetterJobs>>>()
      vi.mocked(action).mockReturnValueOnce(failed.promise).mockReturnValueOnce(recovered.promise)
      const { user, queryClient } = renderFeature()
      await settleQueue(queryClient)
      const row = screen.getByRole("checkbox", { name: `Select job ${queue.items[1]!.id}` })
      await user.click(row)
      const button = screen.getByRole("button", { name: label })
      await user.click(button)
      await act(async () => failed.reject(new Error("Queue action failed")))
      await settleQueue(queryClient)
      expect(screen.getByRole("alert")).toHaveTextContent("Queue action failed")
      expect(row).toBeChecked()
      expect(button).toBeEnabled()
      expect(fetchDeadLetterQueue).toHaveBeenCalledTimes(1)
      await user.click(button)
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
      expect(action).toHaveBeenNthCalledWith(2, [queue.items[1]!.id])
      vi.mocked(fetchDeadLetterQueue).mockResolvedValue({ items: [queue.items[0]!], total: 1 })
      await act(async () => recovered.resolve(queueActionResult([queue.items[1]!.id])))
      await settleQueue(queryClient)
      expect(
        screen.queryByRole("checkbox", { name: `Select job ${queue.items[1]!.id}` })
      ).not.toBeInTheDocument()
      expect(button).toBeDisabled()
    }
  )

  it("dismisses an action error when the administrator changes the selected job", async () => {
    vi.mocked(retryDeadLetterJobs).mockRejectedValueOnce(new Error("Retry failed"))
    const { user, queryClient } = renderFeature()
    await settleQueue(queryClient)
    const first = screen.getByRole("checkbox", { name: `Select job ${queue.items[0]!.id}` })
    await user.click(first)
    await user.click(screen.getByRole("button", { name: "Retry selected" }))
    await settleQueue(queryClient)
    expect(screen.getByRole("alert")).toHaveTextContent("Retry failed")
    await user.click(first)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(first).not.toBeChecked()
  })
})
