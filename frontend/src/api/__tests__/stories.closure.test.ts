import { beforeEach, describe, expect, it, vi } from "vitest"

const generated = vi.hoisted(() => ({
  createStoryApiV1StoriesPost: vi.fn(),
  deleteStoryApiV1StoriesStoryIdDelete: vi.fn(),
  listStoriesApiV1StoriesGet: vi.fn(),
  updateStoryApiV1StoriesStoryIdPatch: vi.fn(),
  uploadStoryCoverApiV1StoriesUploadCoverPost: vi.fn(),
}))

vi.mock("@/api/generated", () => generated)

import { createStory, deleteStory, fetchStories, updateStory, uploadStoryCover } from "../stories"

beforeEach(() => {
  vi.clearAllMocks()
})

describe("stories API wrappers", () => {
  it("fetches stories with the dashboard cache key", async () => {
    generated.listStoriesApiV1StoriesGet.mockResolvedValue({ data: [] })

    await fetchStories()

    expect(generated.listStoriesApiV1StoriesGet).toHaveBeenCalledWith({
      etagCacheKey: "dashboard:stories",
      throwOnError: true,
      validateStatus: expect.any(Function),
    })
    const options = generated.listStoriesApiV1StoriesGet.mock.calls[0]?.[0] as {
      validateStatus: (status: number) => boolean
    }
    expect(options.validateStatus(199)).toBe(false)
    expect(options.validateStatus(200)).toBe(true)
    expect(options.validateStatus(299)).toBe(true)
    expect(options.validateStatus(304)).toBe(true)
    expect(options.validateStatus(300)).toBe(false)
    expect(options.validateStatus(422)).toBe(false)
    expect(options.validateStatus(500)).toBe(false)
  })

  it("passes create and update payloads to the generated client", async () => {
    const createPayload = { title: "Campus update" }
    const updatePayload = { title: "Updated campus update" }
    generated.createStoryApiV1StoriesPost.mockResolvedValue({ data: { id: "story-1" } })
    generated.updateStoryApiV1StoriesStoryIdPatch.mockResolvedValue({ data: { id: "story-1" } })

    await createStory(createPayload as never)
    await updateStory("story-1", updatePayload as never)

    expect(generated.createStoryApiV1StoriesPost).toHaveBeenCalledWith({
      body: createPayload,
      throwOnError: true,
    })
    expect(generated.updateStoryApiV1StoriesStoryIdPatch).toHaveBeenCalledWith({
      path: { story_id: "story-1" },
      body: updatePayload,
      throwOnError: true,
    })
  })

  it("deletes by story id", async () => {
    generated.deleteStoryApiV1StoriesStoryIdDelete.mockResolvedValue({ data: undefined })

    await deleteStory("story-2")

    expect(generated.deleteStoryApiV1StoriesStoryIdDelete).toHaveBeenCalledWith({
      path: { story_id: "story-2" },
      throwOnError: true,
    })
  })

  it("returns an uploaded cover and rejects an empty response", async () => {
    const file = new File(["cover"], "cover.png", { type: "image/png" })
    const uploaded = { url: "/uploads/cover.png" }
    generated.uploadStoryCoverApiV1StoriesUploadCoverPost.mockResolvedValueOnce({ data: uploaded })
    generated.uploadStoryCoverApiV1StoriesUploadCoverPost.mockResolvedValueOnce({ data: undefined })

    await expect(uploadStoryCover(file)).resolves.toEqual(uploaded)
    await expect(uploadStoryCover(file)).rejects.toThrow("Upload failed")
    expect(generated.uploadStoryCoverApiV1StoriesUploadCoverPost).toHaveBeenNthCalledWith(1, {
      body: { file },
    })
  })

  it("classifies an empty cover response without losing the diagnostic message", async () => {
    const file = new File(["cover"], "cover.png", { type: "image/png" })
    generated.uploadStoryCoverApiV1StoriesUploadCoverPost.mockResolvedValueOnce({ data: undefined })

    await expect(uploadStoryCover(file)).rejects.toMatchObject({
      name: "StoryCoverUploadError",
      message: "Upload failed",
    })
  })

  it("preserves a rejected server error from cover upload", async () => {
    const file = new File(["cover"], "cover.png", { type: "image/png" })
    const serverError = { isAxiosError: true, response: { data: { detail: "cover rejected" } } }
    generated.uploadStoryCoverApiV1StoriesUploadCoverPost.mockRejectedValueOnce(serverError)

    await expect(uploadStoryCover(file)).rejects.toBe(serverError)
  })
})
