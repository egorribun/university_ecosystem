import { Users } from "lucide-react"

interface GroupAvatarProps {
  /** Tailwind sizing classes for the circle (default matches the ContactList row). */
  className?: string
  /** Lucide glyph px size (scale with the circle when overriding className). */
  iconSize?: number
}

/**
 * Wave 211 G4 — the avatar glyph for a group chat (no per-user photo). A Users
 * icon centered in the messenger violet→pink gradient circle (the same
 * `--messenger-send-bg` the send button uses, so groups read as "on-theme").
 *
 * The gradient is theme-INDEPENDENT (violet-400 → pink-400 are fixed primitives,
 * identical in light + dark), so the glyph is a CONSTANT `--color-white` — the
 * same rationale as the W175 `--text-on-footer` always-dark surface, NOT a
 * `--text-inverse` theme miss. `aria-hidden` — the chat row / header supplies the
 * accessible group name alongside it.
 */
export function GroupAvatar({ className = "w-12 h-12", iconSize = 22 }: GroupAvatarProps) {
  return (
    <div
      className={`${className} rounded-full flex items-center justify-center shadow-sm shrink-0`}
      style={{ background: "var(--messenger-send-bg)" }}
      aria-hidden="true"
    >
      <Users size={iconSize} className="text-(--color-white)" strokeWidth={2} aria-hidden="true" />
    </div>
  )
}
