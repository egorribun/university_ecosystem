import type { Message } from "@/api/chat"

export function messageEpochMicroseconds(createdAt: string): bigint | null {
  const epochMilliseconds = Date.parse(createdAt)
  if (!Number.isFinite(epochMilliseconds)) return null

  // Date.parse keeps only millisecond precision. Preserve the final three
  // fractional digits so the cursor exactly matches the backend's integer
  // microsecond keyset contract.
  const fractional = /\.(\d{1,6})(?:Z|[+-]\d{2}:\d{2})/u.exec(createdAt)?.[1] ?? ""
  const subMillisecondDigits = fractional.padEnd(6, "0").slice(3, 6)
  return BigInt(epochMilliseconds) * 1000n + BigInt(subMillisecondDigits)
}

export function compareMessageOrder(
  left: Pick<Message, "id" | "created_at">,
  right: Pick<Message, "id" | "created_at">
): number | null {
  const leftEpoch = messageEpochMicroseconds(left.created_at)
  const rightEpoch = messageEpochMicroseconds(right.created_at)
  if (leftEpoch === null || rightEpoch === null) return null
  if (leftEpoch < rightEpoch) return -1
  if (leftEpoch > rightEpoch) return 1

  const leftId = String(left.id)
  const rightId = String(right.id)
  if (leftId < rightId) return -1
  if (leftId > rightId) return 1
  return 0
}
