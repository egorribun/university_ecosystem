import { fireEvent, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  isOnline: true,
  syncState: "idle" as "offline" | "syncing" | "synced" | "idle",
  totalPendingCount: 0,
  triggerManualSync: vi.fn(),
  t: vi.fn(),
  useTranslation: vi.fn(),
  useSyncStatus: vi.fn(),
}))

vi.mock("@/hooks/useSyncStatus", () => ({
  useSyncStatus: state.useSyncStatus,
}))

vi.mock("react-i18next", () => ({
  useTranslation: state.useTranslation,
}))

vi.mock("lucide-react", () => ({
  Cloud: ({ className }: { className?: string }) => (
    <svg data-testid="sync-icon-cloud" className={className} />
  ),
  CloudUpload: ({ className }: { className?: string }) => (
    <svg data-testid="sync-icon-cloud-upload" className={className} />
  ),
  RefreshCw: ({ className }: { className?: string }) => (
    <svg data-testid="sync-icon-refresh" className={className} />
  ),
  CheckCircle2: ({ className }: { className?: string }) => (
    <svg data-testid="sync-icon-check" className={className} />
  ),
}))

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  m: {
    div: ({
      children,
      initial,
      animate,
      exit,
      transition,
      ...props
    }: {
      children?: ReactNode
      initial?: Record<string, unknown>
      animate?: Record<string, unknown>
      exit?: Record<string, unknown>
      transition?: Record<string, unknown>
      className?: string
      role?: string
      title?: string
      onClick?: () => void
    }) => (
      <div
        {...props}
        data-testid={transition ? "sync-offline-motion" : "sync-status-motion"}
        data-motion-animate={JSON.stringify(animate)}
        data-motion-exit={JSON.stringify(exit)}
        data-motion-initial={JSON.stringify(initial)}
        data-motion-transition={JSON.stringify(transition, (_key, value) =>
          value === Infinity ? "Infinity" : value
        )}
      >
        {children}
      </div>
    ),
  },
}))

import { SyncStatus } from "@/components/feedback/SyncStatus"

describe("SyncStatus mutation contracts", () => {
  beforeEach(() => {
    state.isOnline = true
    state.syncState = "idle"
    state.totalPendingCount = 0
    state.triggerManualSync.mockReset()
    state.t.mockReset().mockImplementation((key: string) => key)
    state.useTranslation.mockReset().mockReturnValue({ t: state.t })
    state.useSyncStatus.mockReset().mockImplementation(() => ({
      isOnline: state.isOnline,
      syncState: state.syncState,
      totalPendingCount: state.totalPendingCount,
      triggerManualSync: state.triggerManualSync,
    }))
  })

  it("requests common translations, renders the idle cloud, and keeps the base contract", () => {
    render(<SyncStatus />)

    expect(state.useTranslation).toHaveBeenCalledWith(["common"])
    expect(state.t).toHaveBeenCalledWith("common:sync.online")
    const status = screen.getByRole("status", { name: "common:sync.online" })
    expect(status).toHaveClass(
      "flex",
      "items-center",
      "gap-1.5",
      "px-2.5",
      "py-1",
      "rounded-full",
      "transition-all",
      "duration-base",
      "cursor-pointer",
      "select-none",
      "bg-glass-subtle",
      "border",
      "border-border-subtle",
      "shadow-sm",
      "hover:bg-glass-hover"
    )
    expect(status).not.toHaveClass(
      "border-warning-border/(--opacity-dim)",
      "bg-warning-bg/(--opacity-subtle)",
      "border-brand/30",
      "bg-brand/10",
      "border-success-border",
      "bg-success-bg/20"
    )
    expect(screen.getByTestId("sync-icon-cloud")).toHaveClass("h-4", "w-4")
    expect(status).toHaveAttribute("data-motion-initial", '{"opacity":0,"scale":0.8}')
    expect(status).toHaveAttribute("data-motion-animate", '{"opacity":1,"scale":1}')
    expect(status).toHaveAttribute("data-motion-exit", '{"opacity":0,"scale":0.8}')

    fireEvent.click(status)
    expect(state.triggerManualSync).toHaveBeenCalledOnce()
  })

  it("renders the offline queue count, warning state, and animated upload icon", () => {
    state.isOnline = false
    state.syncState = "offline"
    state.totalPendingCount = 2
    state.t.mockImplementation((key: string, options?: { count?: number }) =>
      options ? `${key}:${options.count}` : key
    )

    render(<SyncStatus />)

    expect(state.t).toHaveBeenCalledWith("common:sync.offline", { count: 2 })
    const status = screen.getByRole("status", { name: "common:sync.offline:2" })
    expect(status).toHaveClass(
      "border-warning-border/(--opacity-dim)",
      "bg-warning-bg/(--opacity-subtle)"
    )
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByTestId("sync-icon-cloud-upload")).toHaveClass(
      "h-4",
      "w-4",
      "text-(--warning-text)"
    )
    expect(screen.getByTestId("sync-offline-motion")).toHaveAttribute(
      "data-motion-animate",
      '{"opacity":[1,0.5,1]}'
    )
    expect(screen.getByTestId("sync-offline-motion")).toHaveAttribute(
      "data-motion-transition",
      '{"repeat":"Infinity","duration":2}'
    )
  })

  it("renders syncing state only while work is pending", () => {
    state.syncState = "syncing"
    state.totalPendingCount = 1
    render(<SyncStatus />)

    const status = screen.getByRole("status", { name: "common:sync.online" })
    expect(status).toHaveClass("border-brand/30", "bg-brand/10")
    expect(status).not.toHaveClass("border-success-border", "bg-success-bg/20")
    expect(screen.getByTestId("sync-icon-refresh")).toHaveClass("animate-spin", "text-brand")
    expect(screen.queryByTestId("sync-icon-cloud")).not.toBeInTheDocument()
    expect(screen.queryByTestId("sync-icon-check")).not.toBeInTheDocument()
  })

  it("renders the transient synced state and does not use it for idle work", () => {
    state.syncState = "synced"
    state.totalPendingCount = 1
    render(<SyncStatus />)

    const status = screen.getByRole("status", { name: "common:sync.online" })
    expect(status).toHaveClass("border-success-border", "bg-success-bg/20")
    expect(status).not.toHaveClass("border-brand/30", "bg-brand/10")
    expect(screen.getByTestId("sync-icon-check")).toHaveClass("h-4", "w-4", "text-success-text")
    expect(screen.queryByTestId("sync-icon-refresh")).not.toBeInTheDocument()
  })

  it("returns no status when offline with no pending work", () => {
    state.isOnline = false
    state.syncState = "offline"
    render(<SyncStatus />)

    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(state.t).not.toHaveBeenCalled()
  })
})
