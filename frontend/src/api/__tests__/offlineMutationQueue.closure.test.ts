import { beforeEach, describe, expect, it, vi } from "vitest"

const offline = vi.hoisted(() => ({
  storePendingMutation: vi.fn(),
}))

vi.mock("@/sw/offline", () => offline)

import { SERVICE_WORKER_MESSAGE_TYPES } from "@/constants/serviceWorkerMessages"
import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { enqueueOfflineMutation } from "../offlineMutationQueue"

const mutation = {
  url: "/api/v1/events/1",
  method: "PATCH" as const,
  payload: { title: "Updated" },
}

beforeEach(() => {
  vi.clearAllMocks()
  offline.storePendingMutation.mockResolvedValue(undefined)
  vi.stubGlobal("navigator", {})
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

describe("enqueueOfflineMutation", () => {
  it("stores a general mutation when no service worker is available", async () => {
    await enqueueOfflineMutation(mutation)

    expect(offline.storePendingMutation).toHaveBeenCalledWith({
      ...mutation,
      category: "general",
      sessionNonce: null,
    })
  })

  it("stores the mutation before returning when navigator has no serviceWorker member", async () => {
    vi.stubGlobal("navigator", { userAgent: "test" })

    await enqueueOfflineMutation({ ...mutation, category: "profile" })

    expect(offline.storePendingMutation).toHaveBeenCalledWith({
      ...mutation,
      category: "profile",
      sessionNonce: null,
    })
  })

  it("stores the mutation before returning when navigator is unavailable", async () => {
    vi.stubGlobal("navigator", undefined)

    await enqueueOfflineMutation(mutation)

    expect(offline.storePendingMutation).toHaveBeenCalledWith({
      ...mutation,
      category: "general",
      sessionNonce: null,
    })
  })

  it("binds the mutation to the verified browser session it was created under", async () => {
    rotateBrowserSession()
    const nonce = getBrowserSessionGeneration()

    await enqueueOfflineMutation(mutation)

    expect(nonce).not.toBeNull()
    expect(offline.storePendingMutation).toHaveBeenCalledWith({
      ...mutation,
      category: "general",
      sessionNonce: nonce,
    })
  })

  it("leaves the mutation unbound when the browser session cannot be verified", async () => {
    rotateBrowserSession()
    localStorage.setItem(
      "ecosystem.session.generation.v1",
      JSON.stringify({ nonce: "foreign-session", hash: null })
    )

    await enqueueOfflineMutation(mutation)

    expect(offline.storePendingMutation).toHaveBeenCalledWith({
      ...mutation,
      category: "general",
      sessionNonce: null,
    })
  })

  it("does not post work when a service worker exists without an active controller", async () => {
    const postMessage = vi.fn()
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller: null,
        ready: Promise.resolve({ sync: { register: vi.fn() } }),
      },
    })

    await enqueueOfflineMutation(mutation)

    expect(offline.storePendingMutation).toHaveBeenCalledOnce()
    expect(postMessage).not.toHaveBeenCalled()
  })

  it("registers a background sync when the service worker exposes sync", async () => {
    const controller = { postMessage: vi.fn() }
    const register = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller,
        ready: Promise.resolve({ sync: { register } }),
      },
    })

    await enqueueOfflineMutation({ ...mutation, category: "events", headers: { "x-test": "1" } })

    expect(register).toHaveBeenCalledWith("sync-offline-mutations")
    expect(controller.postMessage).not.toHaveBeenCalled()
  })

  it("posts a process message when background sync is unavailable", async () => {
    const controller = { postMessage: vi.fn() }
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller,
        ready: Promise.resolve({}),
      },
    })

    await enqueueOfflineMutation(mutation)

    expect(controller.postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
    })
  })

  it("posts a process message when service worker readiness fails", async () => {
    const controller = { postMessage: vi.fn() }
    vi.stubGlobal("navigator", {
      serviceWorker: {
        controller,
        ready: Promise.reject(new Error("worker unavailable")),
      },
    })

    await enqueueOfflineMutation(mutation)

    expect(controller.postMessage).toHaveBeenCalledWith({
      type: SERVICE_WORKER_MESSAGE_TYPES.PROCESS_OFFLINE_QUEUES,
    })
  })
})
