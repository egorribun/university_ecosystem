# AGENTS.md — Frontend Domain Standards (`frontend/`)

This document defines the architectural invariants, framework constraints, accessibility (WCAG 2.2 AA) rules, and code conventions for the TypeScript/React 19 frontend (`frontend/`). All agents modifying frontend code must adhere strictly to these rules.

---

## 1. Tech Stack & Environment Standards

- **Core Frameworks**: React 19.2+, TypeScript 5.7+ (strict mode), TanStack Router 1.168+, TanStack Query 5.90+, Zustand 5.0+.
- **Bundler & Build**: Vite 8 with Rolldown / `@rolldown/plugin-babel` and `babel-plugin-react-compiler`.
- **Validation Library**: **Valibot 1.3+ ONLY** (`valibot`). Zod is completely forbidden and was excised from the codebase in Wave 21.
- **Type Checking**: `cd frontend && npx tsc --noEmit` must pass with zero errors.
- **Linting**: `cd frontend && npm run lint` must pass with zero warnings.

---

## 2. Schema Validation (Valibot Exclusivity)

### 2.1. Strict Valibot Usage

- All form validation, route search parameters, local storage schemas, and API payload schemas must be defined using `valibot` (`v.*`).
- **Zod is Forbidden**: Do not import or introduce `zod`.

### 2.2. TanStack Router Search Params Schema Unions

- `stringifySearch` serializes numeric and boolean parameters as JSON-encoded strings in URLs (e.g. `?zoom="16"` -> `?zoom=%2216%22`).
- **Invariant**: Search schemas must handle both string and primitive types via `v.union()`:
  ```typescript
  import * as v from "valibot"

  export const MapSearchSchema = v.object({
    zoom: v.optional(v.union([v.number(), v.string()])),
    buildingId: v.optional(v.string()),
  })
  ```

---

## 3. Routing & State Management

### 3.1. Route Guards & Client State Access

- **SSR Context vs. Client State**: Router context `.auth` is reserved for server-side initial render (`globalThis.__ssrAuthGetter__()` in `server.ts`).
- **Client Route Guards**: Guard files (`_auth.tsx`, `_public.tsx`, `_admin.tsx`) **MUST** read live authentication state directly from Zustand via `useAuthStore.getState()` inside `beforeLoad`.
- **Rationale**: Relying on stale router context on the client causes race conditions, improper redirects, and desynchronized authentication state.

```typescript
// src/routes/_auth.tsx
import { createFileRoute, redirect } from "@tanstack/react-router"
import { useAuthStore } from "@/stores/authStore"

export const Route = createFileRoute("/_auth")({
  beforeLoad: ({ location }) => {
    const { user, loading } = useAuthStore.getState()
    if (!loading && !user) {
      throw redirect({
        to: "/login",
        search: { redirect: location.href },
      })
    }
  },
})
```

### 3.2. Open-Redirect Prevention

- All post-login or callback redirects must be sanitized through `resolveRedirectPath(targetPath)` to prevent open-redirect vulnerabilities.

### 3.3. Navigation & Route Params

- Always use typed navigation: `navigate({ to: "/events/$id", params: { id: eventId } })`.

---

## 4. TanStack Query & Suspense Invariants

### 4.1. Suspense vs. Fallback Queries

- `useSuspenseMyEventsQuery` and other `useSuspense*` hooks must be used **ONLY** within components wrapped by a `<Suspense>` boundary.
- Components requiring graceful offline fallback states or non-blocking background fetching must use standard `useQuery` hooks with explicit `isLoading` / `isError` handling.

### 4.2. Infinite Query Items Access

- Data pagination in infinite queries must access elements via `page.items` (not raw root array).

### 4.3. Referential Stability in Mutations

- **CRITICAL INVARIANT**: **NEVER** pass the entire `useMutation()` result object into `useEffect` or `useCallback` dependency arrays.
- Extract and use the referentially-stable `mut.mutate` or `mut.mutateAsync` function directly.

```typescript
// CORRECT
const createItem = useMutation({ mutationFn: api.createItem })
const handleSubmit = useCallback(() => {
  createItem.mutate(payload)
}, [createItem.mutate]) // Stable reference

// FORBIDDEN (createItem object changes every render -> triggers infinite loop)
useEffect(() => {
  if (condition) createItem.mutate(payload)
}, [createItem])
```

---

## 5. React Compiler & Performance Guidelines

### 5.1. Ref Reading Rules (React Compiler Safety)

- Direct reading of `ref.current` during component render is strictly forbidden by the React Compiler.
- Extract primitive values outside render or store reactive UI state in `useState` / `useMemo`:
  ```typescript
  // CORRECT
  const userId = user?.id
  const isOwner = userId === authorId

  // FORBIDDEN
  const isOwner = userRef.current?.id === authorId
  ```
- If a ref must be accessed in exceptional non-reactive scenarios, use `"use no memo"` with `// eslint-disable-next-line react-compiler/react-compiler`.

### 5.2. Memoization on Heavy Components

- Wrap list items, complex grid cards, and dashboard widgets in `React.memo()` to eliminate unnecessary DOM reconciliation cycles.

### 5.3. Bundle Budget & Dynamic Imports

- **Main JS Chunk Budget**: Main JS bundle chunk must remain strictly **<500 KB** (enforced by CI bundle-analysis gate MOD-23-06).
- **Dynamic Imports**: Large third-party libraries must be dynamically imported on demand:
  - PDF Generation: `await import("jspdf")`
  - Map Engine: `React.lazy(() => import("@/components/map/MapLibreMap"))`
- Assets $\le$ 4 KB should be inlined; larger assets must use CDN or chunked static loading.

### 5.4. Debounce Presets (`useDebounced`)

Use the standardized `useDebounced` hook from `@/hooks/useDebounced` with strategy presets (PERF-23-04):

- `"search"`: 200ms (fast typeahead autocomplete)
- `"default"`: 300ms (general input handling)
- `"validation"`: 350ms (expensive async schema/field validation)

---

## 6. SSR & Hydration Invariants

### 6.1. Hydration Initialization

- React 19 mounts with `hydrateRoot` when server markup is present (`hasRealSsrContent`) and falls back to `createRoot` for SPA client rendering.
- `window.__APP_HYDRATED` flag is set in `AppProviders.tsx` once the hydration lifecycle completes.

### 6.2. Browser-Only State (`mounted` Pattern)

- Components utilizing portals, `window.matchMedia()`, or `localStorage` must use the `mounted` state pattern to prevent hydration mismatch errors (#418):
  ```typescript
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <SkeletonLoader aria-busy="true" />;
  ```
- Never mutate the DOM before hydration finishes. If SSR markup intentionally diverges from browser values, apply `suppressHydrationWarning`.

### 6.3. Service Worker Cache Exclusion

- The Service Worker (`/sw.js`) must **NEVER** cache sensitive or dynamic endpoints: `/users/me`, `/auth/*`, `/csrf`.

---

## 7. Accessibility (WCAG 2.2 AA) & Design System Standards

### 7.1. Interactive Targets & Touch Sizes

- **Buttons / Controls**: Minimum touch target size of **44x44px**.
- **Text Links**: Must be styled with `inline-block min-h-[24px] px-2 py-1.5` to ensure adequate hit surface.

### 7.2. Dialogs & Modals

- All modals and overlays must specify `role="dialog"` or `role="alertdialog"`.
- Must declare `aria-labelledby` and `aria-describedby` pointing to header and description elements.
- Must set `aria-modal="true"` and enforce focus containment with `useFocusTrap`.

### 7.3. Forms & Live Regions

- **Form Inputs**: Helper text linked via `aria-describedby`; validation errors rendered with `role="alert"`.
- **Radios / Selection**: `role="radiogroup"` / `role="radio"` with `aria-checked`.
- **Chat & Messages**: Message feed requires `role="log"` and `aria-live="polite"`. Typing indicator requires `role="status"`.
- **Skeletons**: Must include `aria-busy="true"`.
- **Charts / Visualizations**: Must provide an accessible hidden tabular alternative: `<table className="sr-only"/>`.

### 7.4. Motion Safety (`useReducedMotion`)

- All Framer Motion animations must respect the user's OS-level motion preference:
  ```typescript
  import { useReducedMotion } from "@/hooks/useReducedMotion"

  const prefersReduced = useReducedMotion()
  const transition = prefersReduced
    ? { duration: 0 }
    : { type: "spring", stiffness: 300, damping: 25 }
  ```

---

## 8. Frontend Security & Sanitization

- **HTML Sanitization (`SafeHtml`)**: Uses the WASM-based sanitizer (`wasm-sanitizer`) with an ammonia fallback (`nh3`) so that any WASM initialization error safely strips tags rather than rendering a blank screen (RZ-24-04).
- **Cookie & Token Safety**: Never expose access tokens to `globalThis.__ssrCookieGetter()`.
- **CSRF Cookie Guarantee**: Unsafe HTTP mutations (POST, PUT, DELETE, PATCH) must invoke `ensureCsrfCookie()` before sending requests if the cookie is missing.
- **Cross-Tab Synchronization**:
  - Idempotency deduplication: `BroadcastChannel("ecosystem.idempotency.dedup")` (TD-31-04).
  - News bookmarks sync: `BroadcastChannel("ecosystem.news.bookmarks")`.
- **Blob URLs**: Never construct `URL.createObjectURL()` during render; store active URLs in `useRef<Set<string>>` and revoke them upon component unmount.

---

## 9. Frontend Anti-Patterns Summary

| Anti-Pattern                                     | Why It Is Forbidden                                        | Correct Pattern                                   |
| ------------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------- |
| Importing `zod`                                  | Zod was removed in Wave 21; adds bloat and breaks contract | Use `valibot` (`v.*`) exclusively                 |
| Reading router context `.auth` in client guards  | Context is server-only; causes stale auth state            | Read `useAuthStore.getState()` in `beforeLoad`    |
| `useMutation` result object in hook dependencies | Breaks referential stability, causes infinite re-renders   | Depend only on `mut.mutate`                       |
| Reading `ref.current` during render              | Violates React Compiler contract                           | Extract primitives or store in `useState`         |
| Monolithic import of `jspdf` / `MapLibre`        | Blows past 500 KB bundle budget                            | Use dynamic `import()` or `React.lazy()`          |
| Interactive controls < 44x44px                   | Violates WCAG 2.2 AA target size criteria                  | Set minimum dimension `min-w-[44px] min-h-[44px]` |
| Unguarded Framer Motion animations               | Induces motion sickness for vestibular disorder users      | Wrap animation props with `useReducedMotion()`    |
| Blob URLs created during render                  | Memory leaks and unpredictable garbage collection          | Allocate in effects/handlers; revoke on unmount   |
