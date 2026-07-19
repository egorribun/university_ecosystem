import { renderHook, act, waitFor } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { useEventCardLogic } from "../useEventCardLogic"

// Mock dependencies (mirrors the existing useEventCardLogic.test.tsx scaffold).
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(() => ({ user: { id: 1, role: "admin" } })),
}))

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: vi.fn(() => mockNavigate),
}))

vi.mock("react-i18next", () => ({
  useTranslation: vi.fn(() => ({ t: (s: string) => s })),
}))

vi.mock("@/components/ui/Spotlight", () => ({
  useSpotlight: vi.fn(() => ({})),
}))

const mockRegistration = {
  isRegistered: false,
  participantCount: 0,
  register: vi.fn(),
  unregister: vi.fn(),
}
vi.mock("@/hooks/useEventRegistration", () => ({
  useEventRegistration: vi.fn(() => mockRegistration),
}))

const mockPost = vi.fn(async (..._a: unknown[]) => ({ data: { url: "uploaded.png" } }) as any)
const mockPatch = vi.fn(async (..._a: unknown[]) => ({ data: {} }) as any)
const mockApiDelete = vi.fn(async (..._a: unknown[]) => ({ data: {} }) as any)
vi.mock("@/api/client", () => ({
  default: {
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
}))

describe("useEventCardLogic (branches)", () => {
  const eventProps = {
    id: "event-1",
    title: "Initial Title",
    starts_at: "2026-12-01T10:00:00Z",
    ends_at: "2026-12-01T12:00:00Z",
  }

  let createObjectURL: ReturnType<typeof vi.fn>
  let revokeObjectURL: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    createObjectURL = vi.fn(() => "blob:preview-url")
    revokeObjectURL = vi.fn()
    ;(globalThis.URL as any).createObjectURL = createObjectURL
    ;(globalThis.URL as any).revokeObjectURL = revokeObjectURL
    mockPost.mockResolvedValue({ data: { url: "uploaded.png" } } as any)
    mockPatch.mockResolvedValue({ data: {} } as any)
    mockApiDelete.mockResolvedValue({ data: {} } as any)
  })

  afterEach(() => {
    // Reset to safe no-ops (NOT delete): React flushes the newImage-effect
    // cleanup (URL.revokeObjectURL) during testing-library's auto-unmount, which
    // runs AFTER this afterEach (LIFO) — deleting the method would crash that
    // cleanup with "URL.revokeObjectURL is not a function".
    ;(globalThis.URL as any).createObjectURL = () => "blob:noop"
    ;(globalThis.URL as any).revokeObjectURL = () => {}
  })

  // ---- newImage preview effect (lines 113-120) ----

  it("setNewImage(File) → creates object URL + cardImageUrl reflects preview (113-118)", async () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))

    const file = new File(["x"], "p.png", { type: "image/png" })
    act(() => {
      result.current.setNewImage(file)
    })

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(file))
    expect(result.current.previewUrl).toBe("blob:preview-url")
    expect(result.current.cardImageUrl).toBe("blob:preview-url")
  })

  it("clearing newImage revokes the object URL (cleanup 117) + resets previewUrl (119)", async () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))

    const file = new File(["x"], "p.png", { type: "image/png" })
    act(() => {
      result.current.setNewImage(file)
    })
    await waitFor(() => expect(result.current.previewUrl).toBe("blob:preview-url"))

    act(() => {
      result.current.setNewImage(null)
    })

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:preview-url"))
    expect(result.current.previewUrl).toBeNull()
  })

  // ---- handleEdit (lines 123-150) ----

  it("handleEdit: with new image → uploads then patches with returned url (126-144)", async () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useEventCardLogic({ ...eventProps, onChange }))

    const file = new File(["img"], "new.png", { type: "image/png" })
    act(() => {
      result.current.setNewImage(file)
      result.current.setEditOpen(true)
    })

    await act(async () => {
      await result.current.handleEdit()
    })

    expect(mockPost).toHaveBeenCalledWith("/events/upload_image", expect.any(FormData))
    expect(mockPatch).toHaveBeenCalledWith(
      "/events/event-1",
      expect.objectContaining({ image_url: "uploaded.png" })
    )
    expect(onChange).toHaveBeenCalled()
    await waitFor(() => expect(result.current.snackbar).toBe("events:card.messages.saveSuccess"))
    expect(result.current.editOpen).toBe(false)
    expect(result.current.loading).toBe(false)
  })

  it("handleEdit: no new image → patches with existing image_url, no upload (126 false, 135-144)", async () => {
    const onChange = vi.fn()
    const { result } = renderHook(() =>
      useEventCardLogic({ ...eventProps, image_url: "existing.png", onChange })
    )

    act(() => {
      result.current.setEditOpen(true)
    })

    await act(async () => {
      await result.current.handleEdit()
    })

    expect(mockPost).not.toHaveBeenCalled()
    expect(mockPatch).toHaveBeenCalledWith(
      "/events/event-1",
      expect.objectContaining({ image_url: "existing.png" })
    )
    expect(onChange).toHaveBeenCalled()
    await waitFor(() => expect(result.current.snackbar).toBe("events:card.messages.saveSuccess"))
  })

  it("handleEdit: api failure → saveFailure snackbar + loading reset (145-149)", async () => {
    mockPatch.mockRejectedValue(new Error("save boom"))
    const { result } = renderHook(() => useEventCardLogic(eventProps))

    await act(async () => {
      await result.current.handleEdit()
    })

    await waitFor(() => expect(result.current.snackbar).toBe("events:card.messages.saveFailure"))
    expect(result.current.loading).toBe(false)
    // editOpen stays unchanged (default false) since the catch ran before setEditOpen(false)
    expect(result.current.editOpen).toBe(false)
  })

  // ---- handleDelete (lines 152-164) ----

  it("handleDelete: success → deletes, closes confirm, onChange, deleteSuccess (154-158)", async () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useEventCardLogic({ ...eventProps, onChange }))

    act(() => {
      result.current.setConfirmDeleteOpen(true)
    })

    await act(async () => {
      await result.current.handleDelete()
    })

    expect(mockApiDelete).toHaveBeenCalledWith("/events/event-1")
    expect(onChange).toHaveBeenCalled()
    await waitFor(() => expect(result.current.snackbar).toBe("events:card.messages.deleteSuccess"))
    expect(result.current.confirmDeleteOpen).toBe(false)
    expect(result.current.loading).toBe(false)
  })

  it("handleDelete: failure → deleteFailure snackbar + loading reset (159-163)", async () => {
    mockApiDelete.mockRejectedValue(new Error("del boom"))
    const onChange = vi.fn()
    const { result } = renderHook(() => useEventCardLogic({ ...eventProps, onChange }))

    await act(async () => {
      await result.current.handleDelete()
    })

    await waitFor(() => expect(result.current.snackbar).toBe("events:card.messages.deleteFailure"))
    expect(onChange).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
  })
})
