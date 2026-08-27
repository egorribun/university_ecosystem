import { beforeEach, describe, expect, it } from "vitest"

import { resetAdminDeadLetterJobs } from "./handlers"

const VALID_JOB_ID = "550e8400-e29b-41d4-a716-446655440000"

describe("admin dead-letter mutation handlers", () => {
  beforeEach(() => {
    resetAdminDeadLetterJobs()
  })

  it.each(["retry", "purge"] as const)(
    "returns the canonical mutation envelope for %s",
    async (operation) => {
      const response = await fetch(
        `http://localhost/api/v1/notifications/admin/dead-letter/${operation}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ job_ids: [VALID_JOB_ID, "not-a-uuid"] }),
        }
      )

      expect(response.ok).toBe(true)
      await expect(response.json()).resolves.toEqual({
        success: true,
        affected_count: 1,
        job_ids: [VALID_JOB_ID],
      })
    }
  )
})
