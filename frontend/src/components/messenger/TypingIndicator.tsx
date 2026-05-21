import { useTranslation } from "react-i18next"

interface TypingIndicatorProps {
  /**
   * Users currently typing in the visible chat. Empty array → component
   * returns null (no DOM). Single user → "Name is typing...". Multiple →
   * "N people are typing...".
   *
   * Source: `useMessenger().getTypingUsersForChat(chatId)` exposes this
   * via the existing WebSocket presence channel (W134+ MessengerContext);
   * no backend changes needed for W181 SW4.
   */
  users: { userId: string; userName: string }[]

  /**
   * When true, replaces the animated 3-dot pulse with static text per
   * `messenger:isTyping` i18n key. The CSS `@media (prefers-reduced-motion)`
   * block in `tokens/messenger.css` ALSO stops the dot animation
   * defensively (belt + suspenders) — this prop additionally swaps the
   * visual representation so the user sees something semantically clearer
   * than static dots that look broken.
   */
  prefersReducedMotion?: boolean
}

/**
 * TypingIndicator — Wave 181 SW4. Renders a small bubble-styled chip
 * showing who is currently typing in the open chat.
 *
 * a11y: `role="status"` + `aria-live="polite"` so screen readers announce
 * the change but don't interrupt active reading. Static text mode under
 * reduced motion keeps the same semantic ARIA pattern.
 *
 * Visual: 3 dots with staggered pulse (animation in tokens/messenger.css
 * `.messenger-typing-dot` + `@keyframes messenger-typing-pulse`).
 * Container uses `.messenger-typing` matte styling (received-bubble lookalike
 * with tail aligned to the bottom-left).
 *
 * Placement convention: between `<ChatWindow>` and `<MessageInput>` in
 * `ChatArea.tsx`. Padded with `px-4 py-1` to align with the chat-window
 * inner padding so the indicator visually anchors to the bottom of the
 * message log.
 */
export function TypingIndicator({ users, prefersReducedMotion = false }: TypingIndicatorProps) {
  const { t } = useTranslation(["messenger"])

  if (users.length === 0) return null

  // Compose label: single → name; multiple → count.
  // i18n keys live in en/ru messenger.json (added W181 SW4). translationParity
  // test guards key existence; no defaultValue: fallback needed (avoids the
  // anti-pattern that masks missing-key bugs from the parity walker).
  const firstUser = users[0]
  const label =
    users.length === 1 && firstUser
      ? t("messenger:typing", { name: firstUser.userName })
      : t("messenger:typingMultiple", { count: users.length })

  return (
    <div className="px-4 py-1 shrink-0" aria-live="polite" role="status">
      <div className="inline-flex items-center gap-2 max-w-fit">
        <div className="messenger-typing" aria-label={label}>
          {prefersReducedMotion ? (
            <span className="text-xs font-medium text-(--text-secondary)">
              {t("messenger:isTyping")}
            </span>
          ) : (
            <>
              <span className="messenger-typing-dot" aria-hidden="true" />
              <span className="messenger-typing-dot" aria-hidden="true" />
              <span className="messenger-typing-dot" aria-hidden="true" />
            </>
          )}
        </div>
        <span className="text-xs font-medium text-(--text-secondary) sr-only">{label}</span>
      </div>
    </div>
  )
}

export default TypingIndicator
