import { describe, expect, it } from "vitest"

import {
  bindLegacyResetTokenTarget,
  clearLegacyResetTokenForMigration,
  type CapturedLegacyResetToken,
} from "../legacyResetTokenState"

function capturedToken(migrationId: string, expiresAt: number): CapturedLegacyResetToken {
  return {
    key: `entry-${migrationId}`,
    token: `secret-${migrationId}`,
    expiresAt,
    migrating: true,
    migrationId,
    sourceKey: `source-${migrationId}`,
    sourceIndex: 1,
    targetPath: "/reset",
  }
}

describe("legacy reset-token state transitions", () => {
  it("preserves a newer token when older expiry and target-bind events arrive out of order", () => {
    const newer = capturedToken("migration-new", 2_000)

    expect(clearLegacyResetTokenForMigration(newer, "migration-old")).toBe(newer)
    expect(bindLegacyResetTokenTarget(newer, "migration-old", "stale-target")).toBe(newer)
    expect(newer).toEqual(capturedToken("migration-new", 2_000))
  })

  it("clears or binds only the current migration and handles null without mutation", () => {
    const current = capturedToken("migration-current", 1_000)
    const bound = bindLegacyResetTokenTarget(current, "migration-current", "target-current")

    expect(bound).toEqual({ ...current, targetKey: "target-current" })
    expect(bound).not.toBe(current)
    expect(current).not.toHaveProperty("targetKey")
    expect(clearLegacyResetTokenForMigration(current, "migration-current")).toBeNull()
    expect(clearLegacyResetTokenForMigration(null, "migration-current")).toBeNull()
    expect(bindLegacyResetTokenTarget(null, "migration-current", "target-current")).toBeNull()
  })
})
