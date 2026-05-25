import { render } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

import { TypingIndicator } from "@/components/messenger/TypingIndicator"

// Wave 182 SW6 — TypingIndicator unit tests. Closes W181 honest gap-list
// item #14 (TypingIndicator + ProfileModal + NewChatModal zero unit test
// coverage — TypingIndicator is the highest-value of the three since it's
// a NEW W181 SW4 component with non-trivial branching on prefersReducedMotion
// + single-vs-multi-user labels + interpolation args).
//
// Mocking strategy: `react-i18next` `useTranslation()` returns a `t(key, opts)`
// that serializes `${key} ${JSON.stringify(opts || {})}` so we can assert
// (a) the right i18n key was selected per scenario AND (b) interpolation
// args (name + count) were threaded correctly. This is tighter than the
// `t: (key) => key` shortcut in `MessengerVisuals.test.tsx` which would
// lose interpolation visibility.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

describe("TypingIndicator", () => {
  it("renders null when users array is empty", () => {
    const { container } = render(<TypingIndicator users={[]} />)

    // The component should produce zero DOM — TypingIndicator.tsx line 47
    // returns null when users.length === 0 (avoids reserving layout space
    // for an indicator that has nothing to indicate).
    expect(container.firstChild).toBeNull()
  })

  it("renders 3 .messenger-typing-dot spans when not reducedMotion", () => {
    const { container } = render(
      <TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} prefersReducedMotion={false} />
    )

    const dots = container.querySelectorAll(".messenger-typing-dot")
    expect(dots).toHaveLength(3)
    // Dots are decorative — each should be aria-hidden so they don't pollute
    // the accessible name (the sr-only label spans cover that).
    dots.forEach((dot) => expect(dot.getAttribute("aria-hidden")).toBe("true"))
  })

  it("renders static messenger:isTyping text under reducedMotion (skips animated dots)", () => {
    const { container } = render(
      <TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} prefersReducedMotion={true} />
    )

    // Under reduced motion, the animated dot spans should NOT render —
    // instead a static text span with i18n key `messenger:isTyping` swaps in.
    const dots = container.querySelectorAll(".messenger-typing-dot")
    expect(dots).toHaveLength(0)

    const staticTextNode = container.querySelector(".messenger-typing > span")
    expect(staticTextNode?.textContent).toBe("messenger:isTyping")
  })

  it("renders with role=status and aria-live=polite", () => {
    const { container } = render(<TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} />)

    // The outer wrapper provides the live region — screen readers should
    // announce typing-state changes as polite (non-interrupting). See
    // TypingIndicator.tsx line 60.
    const liveRegion = container.querySelector('[role="status"][aria-live="polite"]')
    expect(liveRegion).toBeTruthy()
  })

  it("single user emits messenger:typing key with name interpolation", () => {
    const { container } = render(
      <TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} prefersReducedMotion={false} />
    )

    // `.messenger-typing` container has aria-label = the i18n result.
    // Our mock `t()` serializes interpolation args as JSON so we can verify
    // BOTH the key selection AND the `name: "Alice"` interpolation arg
    // was correctly threaded.
    const bubble = container.querySelector(".messenger-typing")
    expect(bubble?.getAttribute("aria-label")).toBe('messenger:typing|{"name":"Alice"}')
  })

  it("multiple users emits messenger:typingMultiple key with count interpolation", () => {
    const { container } = render(
      <TypingIndicator
        users={[
          { userId: "u1", userName: "Alice" },
          { userId: "u2", userName: "Bob" },
          { userId: "u3", userName: "Charlie" },
        ]}
        prefersReducedMotion={false}
      />
    )

    // Multi-user path switches to messenger:typingMultiple with `count: N`
    // interpolation. Pluralization rules (1 vs 2 vs many) live in the
    // locale JSON's `_one` / `_few` / `_many` Russian plural suffixes,
    // not in component logic.
    const bubble = container.querySelector(".messenger-typing")
    expect(bubble?.getAttribute("aria-label")).toBe('messenger:typingMultiple|{"count":3}')
  })

  it("provides sr-only backup label spanning the full localized text", () => {
    const { container } = render(
      <TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} prefersReducedMotion={false} />
    )

    // Belt + suspenders: the bubble itself has aria-label, AND there's a
    // separate `.sr-only` span at the end that screen readers can pick up
    // if the aria-label on the visual bubble doesn't surface in their
    // navigation mode. Both should resolve to the same localized text.
    const srOnly = container.querySelector(".sr-only")
    expect(srOnly).toBeTruthy()
    expect(srOnly?.textContent).toBe('messenger:typing|{"name":"Alice"}')
  })

  it("defaults prefersReducedMotion to false (3 dots render when prop omitted)", () => {
    const { container } = render(<TypingIndicator users={[{ userId: "u1", userName: "Alice" }]} />)

    // TypingIndicator.tsx line 44 defaults `prefersReducedMotion = false`
    // in the destructured param signature. Omitting the prop should select
    // the animated 3-dot path.
    const dots = container.querySelectorAll(".messenger-typing-dot")
    expect(dots).toHaveLength(3)
  })
})
