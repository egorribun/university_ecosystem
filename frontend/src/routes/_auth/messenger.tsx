import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger")({
  // /messenger × 2 SSR — explicit defer-by-design (W161 SW2 closure of
  // W134 §Honesty #10 carry-forward since W133). Both `messenger.tsx`
  // (list) + `messenger.$chatId.tsx` (detail) stay client-only by design,
  // NOT "W129+ candidate after SSR-readiness audit" anymore.
  //
  // Decision rationale (W161 Phase 1 Agent audit + Phase 3 Review system-
  // design analysis; full detail in docs/audits/AUDIT_WAVE161.md):
  //
  //   (a) Query gate inconsistency — `useMessengerController.ts:68` fires
  //       `useQuery({ queryKey: ["chats"] })` WITHOUT `enabled: isAuth`
  //       gate (unlike `MessengerContext.tsx:66-70` which has the gate).
  //       SSR enable requires factory refactor to extract
  //       `chatsQueryOptions()` per W129 pattern + verified SSR cookie-
  //       forwarding for chat endpoint (W126 SW3 + W133 SW1 chain only
  //       exercised for /users/me + read-only public routes so far).
  //
  //   (b) Privacy/cache scoping — chat list + presence + counterpart
  //       names + last-message-preview is user-private relationship state.
  //       The 6 current SSR routes (/dashboard, /events × 2, /news × 2,
  //       /schedule, /profile, /settings) render either public-ish data
  //       (events, news) or user-shell-only (profile, settings prefetch
  //       /users/me without exposing other users). Chat differs: it
  //       exposes who you've been chatting with. Verifying Cache-Control
  //       + Vary headers across Caddy + Node SSR + browser for per-user
  //       scoping is a separate design effort, not 1-wave scope.
  //
  //   (c) UX/value tradeoff — chat is inherently interactive (WebSocket-
  //       driven presence + typing indicators + optimistic message UI).
  //       SSR LCP win on a chat list view is marginal — users expect
  //       real-time state immediately after mount, not server-rendered
  //       stale state. Client-only render with React Query placeholder +
  //       optimistic UI is the right UX for messaging.
  //
  // W162+ may revisit IF Phase 6 canary rollout (W132 SW6 runbook)
  // requires /messenger SSR for unauthenticated landing flows OR some
  // other concrete reason. Until then, this is a deliberate exception
  // to the W125-W149 SSR Phase 5 arc (closed at /profile + /settings;
  // remaining 2 ssr:false siblings are messenger × 2 BY DESIGN, not
  // pending audit).
  ssr: false,
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
