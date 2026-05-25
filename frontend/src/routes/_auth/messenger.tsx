import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger")({
  // Wave 180 SW3 — /messenger Phase 5 SSR enabled via `ssr: 'data-only'`
  // (W127 SW6 pattern). Closes W134 §Honesty #10 (carry-forward from W133
  // → W161 SW2 by-design defer → W180 user-directive full closure).
  //
  // PRE-W180 STATE (W161 SW2 by-design defer; full history retained for
  // posterity below — DO NOT remove this block, it documents the 3
  // concerns that W180 addressed):
  //
  //   (a) Query gate inconsistency — `useMessengerController.ts:68` fired
  //       `useQuery({ queryKey: ["chats"] })` WITHOUT `enabled: isAuth`
  //       gate (unlike `MessengerContext.tsx:66-70` which had the gate).
  //       Pre-W180 SSR enable required factory refactor.
  //       ✅ W180 SW3 closure: NEW `frontend/src/api/hooks/messenger.ts`
  //       extracts `chatsQueryOptions()` + `chatQueryOptions()` +
  //       `messagesQueryOptions()` factories per W129 (events) / W130
  //       (schedule) / W133 (users) / W134 SW2 (sessions) convention.
  //       `useMessengerController.ts` refactored to spread factories +
  //       add `enabled: !!user` gate matching MessengerContext pattern.
  //       Cache identity preserved via unchanged queryKey tuples.
  //
  //   (b) Privacy/cache scoping — chat list + presence + counterpart
  //       names + last-message-preview is user-private relationship
  //       state. SSR exposure of this in HTML risks cache poisoning if
  //       intermediaries cache responses by URL only.
  //       ✅ W180 SW3 closure: TWO-LAYER privacy posture in
  //       `frontend/src/server.ts`:
  //         (1) Structural: `ssr: 'data-only'` annotation below means SSR
  //             renders the route SHELL (MainLayout + provider tree) but
  //             does NOT call `ensureQueryData(chatsQueryOptions())` in
  //             any loader → no chat data in HTML stream.
  //         (2) Defense-in-depth: `augmentResponseForMessenger()` injects
  //             `Cache-Control: no-store, private, max-age=0` + `Vary:
  //             Cookie` response headers on every /messenger* SSR
  //             response, ensuring browser + CDN + intermediary proxies
  //             cannot cache the response even if it ever did contain
  //             per-user state.
  //
  //   (c) UX/value tradeoff — chat is inherently interactive (WebSocket-
  //       driven presence + typing indicators + optimistic message UI).
  //       SSR LCP win on a chat data view is marginal.
  //       ✅ W180 SW3 closure (accepted as-designed): `ssr: 'data-only'`
  //       still gives shell-render LCP win (MainLayout + nav + footer +
  //       provider tree all SSR'd) without trying to pre-render chat
  //       data (which would conflict with WebSocket-driven UX). Real-
  //       time state still loads client-side post-hydration as before.
  //       This matches /profile + /settings Phase 5 SSR pattern.
  //
  // Per W127 SW6 inheritance contract: child can ONLY make more
  // restrictive (`false > 'data-only' > true`). Parent `_auth.tsx`
  // current state (W128 SW2 + W174 SW1) is `ssr: true` so this child's
  // `'data-only'` annotation IS active runtime (W127 SW6 carries had
  // been silently demoted under `_auth.tsx ssr: false`).
  ssr: "data-only",
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
