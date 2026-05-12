/**
 * Messenger Feature
 *
 * Handles real-time chat: WebSocket connection, messages, conversations.
 *
 * Wave 145 SW2 — MessengerFeature orchestrator added (mirror of
 * features/activity/index.ts + features/events/index.ts W112 SW2 pattern).
 * pages/Messenger.tsx is now a thin FeatureErrorBoundary wrapper that
 * delegates to MessengerFeature.
 */

// Re-export hooks from existing locations
export { useChatWebSocket } from "@/hooks/useChatWebSocket"

// API
export * from "@/api/chat"

// Orchestrator (W145 SW2)
export { default as MessengerFeature } from "./MessengerFeature"
