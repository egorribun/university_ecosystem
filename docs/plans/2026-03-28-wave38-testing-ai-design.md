# Wave 38 — Visual Regression + AI Features Design

## 1. Visual Regression Testing
- Activate Chromatic CI pipeline for Storybook visual regression
- Add stories for Wave 36 glass morphism components
- Snapshot tests via @storybook/addon-vitest

## 2. Semantic Search UI (Cmd+K)
- Backend: GET /api/v1/search endpoint (Elasticsearch + pgvector fusion)
- Frontend: SearchDialog with glass morphism, keyboard nav, debounced query
- Navbar integration with search icon

## 3. Content Summaries
- Backend: summary field on News/Event models (LLM-generated)
- Frontend: ContentSummary expandable component with "AI Summary" badge

## 4. Smart Notifications Foundation
- Frontend: NotificationRelevanceScore visual indicator
- Sort by relevance score (UI-ready, backend scoring later)
