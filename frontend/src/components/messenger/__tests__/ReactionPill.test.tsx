import { render, screen, fireEvent, act } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { ReactionPill } from "@/components/messenger/ReactionPill"
import { reactorsQueryKey, reactorsQueryOptions } from "@/api/hooks/messenger"

/**
 * Wave 207 SW9 (coverage follow-up) — ReactionPill unit tests.
 *
 * ReactionPill (W207 SW6) shipped as the highest-LoC untested FE file (the
 * per-pill `useFloating` + long-press + on-demand reactor popover), which dropped
 * the global functions coverage 0.04% under the 70% gate (CI caught it; local
 * `vitest run` without `--coverage` did not — the W198 §Honesty lesson). These
 * cover ReactionPill's own functions (render + clearLongPress + handlePointerDown
 * + handleClick + the long-press timer/popover branch) so the new feature code is
 * genuinely tested, not gate-gamed.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt ?? ""} />,
}))

const getReactors = vi.fn()
vi.mock("@/api/chat", () => ({
  chatApi: { getReactors: (...args: unknown[]) => getReactors(...args) },
}))

function renderPill(overrides: Partial<Parameters<typeof ReactionPill>[0]> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onToggle = vi.fn()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const utils = render(
    <ReactionPill
      chatId="chat-1"
      messageId="msg-1"
      emoji="👍"
      count={3}
      reactedByMe={false}
      onToggle={onToggle}
      {...overrides}
    />,
    { wrapper }
  )
  return { ...utils, onToggle, queryClient }
}

describe("ReactionPill", () => {
  it("renders the emoji + count with aria-pressed=false by default", () => {
    renderPill()
    const btn = screen.getByRole("button")
    expect(btn).toHaveAttribute("aria-pressed", "false")
    expect(btn.textContent).toContain("👍")
    expect(btn.textContent).toContain("3")
  })

  it("reflects reactedByMe via aria-pressed=true", () => {
    renderPill({ reactedByMe: true })
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true")
  })

  it("fires onToggle(emoji) on a plain click (tap = toggle, W206 preserved)", () => {
    const { onToggle } = renderPill()
    fireEvent.click(screen.getByRole("button"))
    expect(onToggle).toHaveBeenCalledWith("👍")
  })

  it("a pointerDown→pointerUp→click still toggles (clearLongPress cancels the timer)", () => {
    const { onToggle } = renderPill()
    const btn = screen.getByRole("button")
    fireEvent.pointerDown(btn, { pointerType: "touch" })
    fireEvent.pointerUp(btn) // clearLongPress
    fireEvent.click(btn)
    expect(onToggle).toHaveBeenCalledWith("👍")
  })

  it("a mouse pointerDown does not arm the long-press timer (early-return branch)", () => {
    const { onToggle } = renderPill()
    const btn = screen.getByRole("button")
    fireEvent.pointerDown(btn, { pointerType: "mouse" })
    fireEvent.pointerMove(btn) // clearLongPress
    fireEvent.click(btn)
    expect(onToggle).toHaveBeenCalledWith("👍")
  })

  it("does NOT fetch reactors while the popover is closed (enabled gate)", () => {
    renderPill()
    expect(getReactors).not.toHaveBeenCalled()
  })

  it("long-press opens the reactor popover + lists the cached reactor + suppresses the toggle-click", () => {
    vi.useFakeTimers()
    try {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      // Pre-seed the cache so the popover renders synchronously (fresh data, staleTime 30s
      // → useQuery returns it on the enable-flip render without an async queryFn under fake timers).
      queryClient.setQueryData(reactorsQueryKey("chat-1", "msg-1", "👍"), [
        { user_id: "u1", name: "Alice", avatar_url: null },
      ])
      const onToggle = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <ReactionPill
            chatId="chat-1"
            messageId="msg-1"
            emoji="👍"
            count={3}
            reactedByMe={false}
            onToggle={onToggle}
          />
        </QueryClientProvider>
      )
      const btn = screen.getByRole("button")
      fireEvent.pointerDown(btn, { pointerType: "touch" })
      act(() => {
        vi.advanceTimersByTime(600) // > LONG_PRESS_MS (500) → setIsOpen(true) + longPressFiredRef
      })
      // FloatingPortal renders to document.body; screen searches the whole document.
      expect(screen.getByText("Alice")).toBeInTheDocument()
      expect(screen.getByText(/reactions\.whoReacted/)).toBeInTheDocument()
      // The long-press that opened the popover must NOT also toggle the reaction.
      fireEvent.click(btn)
      expect(onToggle).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it("shows the loading state while reactors are being fetched", () => {
    vi.useFakeTimers()
    try {
      getReactors.mockReturnValueOnce(new Promise(() => undefined))
      renderPill()
      const btn = screen.getByRole("button")

      fireEvent.pointerDown(btn, { pointerType: "touch" })
      act(() => {
        vi.advanceTimersByTime(600)
      })

      expect(screen.getByText("messenger:reactions.reactorsLoading")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("shows the empty state when the reactor response has no users", () => {
    vi.useFakeTimers()
    try {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      queryClient.setQueryData(reactorsQueryKey("chat-1", "msg-1", "👍"), [])
      const onToggle = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <ReactionPill
            chatId="chat-1"
            messageId="msg-1"
            emoji="👍"
            count={3}
            reactedByMe={false}
            onToggle={onToggle}
          />
        </QueryClientProvider>
      )

      fireEvent.pointerDown(screen.getByRole("button"), { pointerType: "touch" })
      act(() => {
        vi.advanceTimersByTime(600)
      })

      expect(screen.getByText("messenger:reactions.reactorsEmpty")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("uses the unknown-sender label when a reactor has no name", () => {
    vi.useFakeTimers()
    try {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      queryClient.setQueryData(reactorsQueryKey("chat-1", "msg-1", "👍"), [
        { user_id: "u2", name: null, avatar_url: null },
      ])
      const onToggle = vi.fn()
      render(
        <QueryClientProvider client={queryClient}>
          <ReactionPill
            chatId="chat-1"
            messageId="msg-1"
            emoji="👍"
            count={3}
            reactedByMe={false}
            onToggle={onToggle}
          />
        </QueryClientProvider>
      )

      fireEvent.pointerDown(screen.getByRole("button"), { pointerType: "touch" })
      act(() => {
        vi.advanceTimersByTime(600)
      })

      expect(screen.getByText("messenger:replyTo.unknownSender")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("reactorsQueryOptions.queryFn delegates to chatApi.getReactors (the on-demand fetch)", async () => {
    getReactors.mockResolvedValueOnce([{ user_id: "u1", name: "Bob", avatar_url: null }])
    const opts = reactorsQueryOptions("c", "m", "😮")
    const queryFn = opts.queryFn as (ctx: { signal: AbortSignal }) => Promise<unknown>
    const signal = new AbortController().signal
    const result = await queryFn({ signal })
    expect(getReactors).toHaveBeenCalledWith("c", "m", "😮", signal)
    expect(result).toEqual([{ user_id: "u1", name: "Bob", avatar_url: null }])
  })
})
