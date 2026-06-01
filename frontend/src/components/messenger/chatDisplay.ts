import type { TFunction } from "i18next"
import type { Chat } from "@/api/chat"
import type { User } from "@/types/User"

/**
 * Wave 211 G4 — resolved display identity for a chat row / header.
 *
 * Branches on `chat_type` (Wave 209 G1): a GROUP renders its `name` + a generic
 * GroupAvatar glyph (avatar = "" → the caller draws the matte Users circle); a DM
 * renders the OTHER participant's profile name + avatar. Centralizing this here
 * keeps the ContactList row, the ChatArea header, and the GroupInfoPanel in sync
 * instead of each re-deriving "is this a group?" from `chat_type`.
 */
export interface ChatDisplayInfo {
  name: string
  /** "" for a group (GroupAvatar renders the glyph); the DM peer's avatar_url otherwise. */
  avatar: string
  isGroup: boolean
  /** participants.length — drives the group header "{count} members" subtitle. */
  memberCount: number
  /** The DM counterpart (undefined for a group) — for presence + profile-view. */
  otherParticipant?: User
}

export function chatDisplayInfo(
  chat: Chat,
  currentUserId: string | undefined,
  t: TFunction
): ChatDisplayInfo {
  if (chat.chat_type === "group") {
    return {
      name: chat.name?.trim() || t("messenger:group.untitled"),
      avatar: "",
      isGroup: true,
      memberCount: chat.participants.length,
    }
  }
  const other = chat.participants.find((p) => p.id !== currentUserId)
  return {
    name: other?.full_name || t("messenger:unknownUser"),
    avatar: other?.avatar_url || "",
    isGroup: false,
    memberCount: chat.participants.length,
    otherParticipant: other,
  }
}
