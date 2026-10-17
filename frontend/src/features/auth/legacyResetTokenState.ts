export type CapturedLegacyResetToken = {
  key: string
  token: string
  expiresAt: number
  migrating: boolean
  migrationId: string
  sourceKey: string
  sourceIndex: number | null
  targetPath: string
  targetKey?: string
}

export function clearLegacyResetTokenForMigration(
  current: CapturedLegacyResetToken | null,
  migrationId: string
): CapturedLegacyResetToken | null {
  return current?.migrationId === migrationId ? null : current
}

export function bindLegacyResetTokenTarget(
  current: CapturedLegacyResetToken | null,
  migrationId: string,
  targetKey: string
): CapturedLegacyResetToken | null {
  return current?.migrationId === migrationId ? { ...current, targetKey } : current
}
