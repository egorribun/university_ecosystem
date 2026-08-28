import type { ReactNode } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
  getChats: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: mocks.useAuth,
}))

vi.mock("@/api/chat", () => ({
  chatApi: {
    getChats: mocks.getChats,
  },
}))

import { MessengerShellProvider } from "../MessengerShellProvider"
import { useMessenger } from "../MessengerContextCore"

const Probe = () => {
  const { unreadCount, isConnected, getTypingUsersForChat, sendTyping } = useMessenger()
  return (
    <output
      data-testid="messenger-shell-state"
      data-unread={String(unreadCount)}
      data-connected={String(isConnected)}
      data-typing={String(getTypingUsersForChat("chat-1").length)}
      data-send={String(sendTyping("chat-1"))}
    />
  )
}

const renderShell = (children: ReactNode = <Probe />) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MessengerShellProvider>{children}</MessengerShellProvider>
      </QueryClientProvider>
    ),
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  Reflect.deleteProperty(window, "requestIdleCallback")
  Reflect.deleteProperty(window, "cancelIdleCallback")
  mocks.useAuth.mockReturnValue({ isAuth: true })
  mocks.getChats.mockResolvedValue({
    items: [{ unread_count: 2 }, { unread_count: 0 }, { unread_count: -3 }, { unread_count: 4 }],
    has_more: false,
    next_cursor: null,
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.clearAllMocks()
  Reflect.deleteProperty(window, "requestIdleCallback")
  Reflect.deleteProperty(window, "cancelIdleCallback")
})

describe("MessengerShellProvider", () => {
  it("keeps a dependency-free default context before the idle fetch", () => {
    renderShell()

    const state = screen.getByTestId("messenger-shell-state")
    expect(state).toHaveAttribute("data-unread", "0")
    expect(state).toHaveAttribute("data-connected", "false")
    expect(state).toHaveAttribute("data-typing", "0")
    expect(state).toHaveAttribute("data-send", "undefined")
    expect(mocks.getChats).not.toHaveBeenCalled()
  })

  it("loads and aggregates non-negative unread counts after idle", async () => {
    renderShell()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500)
    })
    await act(async () => {
      await vi.dynamicImportSettled()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
      await vi.runAllTimersAsync()
    })
    expect(mocks.getChats).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId("messenger-shell-state")).toHaveAttribute("data-unread", "6")
  })

  it("fails closed to zero unread chats when the optional chat payload has no items", async () => {
    vi.useRealTimers()
    const requestIdleCallback = vi.fn((callback: () => void) => {
      queueMicrotask(callback)
      return 1
    })
    Object.assign(window, { requestIdleCallback, cancelIdleCallback: vi.fn() })
    mocks.getChats.mockResolvedValueOnce({})
    const { queryClient } = renderShell()

    await waitFor(() => {
      expect(mocks.getChats).toHaveBeenCalledTimes(1)
      expect(queryClient.getQueryData(["chats"])).toEqual({})
    })

    await waitFor(() =>
      expect(screen.getByTestId("messenger-shell-state")).toHaveAttribute("data-unread", "0")
    )
  })

  it("does not fetch for signed-out users and cancels pending work on unmount", async () => {
    mocks.useAuth.mockReturnValue({ isAuth: false })
    const view = renderShell()
    await vi.advanceTimersByTimeAsync(1_500)
    expect(mocks.getChats).not.toHaveBeenCalled()

    mocks.useAuth.mockReturnValue({ isAuth: true })
    view.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MessengerShellProvider>
          <Probe />
        </MessengerShellProvider>
      </QueryClientProvider>
    )
    view.unmount()
    await vi.advanceTimersByTimeAsync(1_500)
    expect(mocks.getChats).not.toHaveBeenCalled()
  })

  it("does not hydrate the optional badge during Lighthouse audits", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    renderShell()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
      await vi.runAllTimersAsync()
    })
    expect(mocks.getChats).not.toHaveBeenCalled()
    expect(screen.getByTestId("messenger-shell-state")).toHaveAttribute("data-unread", "0")
  })

  it("cleans up a native requestIdleCallback handle", async () => {
    vi.useRealTimers()
    const requestIdleCallback = vi.fn((callback: () => void) => {
      callback()
      return 42
    })
    const cancelIdleCallback = vi.fn()
    Object.assign(window, { requestIdleCallback, cancelIdleCallback })

    const view = renderShell()
    await waitFor(() => expect(mocks.getChats).toHaveBeenCalledTimes(1))
    view.unmount()
    expect(cancelIdleCallback).toHaveBeenCalledWith(42)
  })
})
