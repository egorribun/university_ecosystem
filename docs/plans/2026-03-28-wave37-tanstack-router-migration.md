# Wave 37 — TanStack Router Migration Design

## Goal
Replace React Router DOM 7 (library mode) with TanStack Router (file-based) for type-safe routing, automatic prefetching, and validated search params.

## Approach: File-Based Routing with Vite Plugin

### New Route Structure
```
src/routes/
├── __root.tsx          # Root layout (MainLayout, BackToTop, LivePushToasts, etc.)
├── index.tsx           # / → redirect to /dashboard
├── _auth.tsx           # Pathless layout: beforeLoad checks isAuth
├── _auth/dashboard.tsx ... messenger.$chatId.tsx
├── _public.tsx         # Pathless layout: beforeLoad redirects if authed
├── _public/login.tsx ... reset-password.$token.tsx
├── _admin.tsx          # Pathless layout: beforeLoad checks admin role
├── _admin/admin.*.tsx
```

### Auth: beforeLoad replaces RouteGuards.tsx
### Search Params: Valibot validateSearch replaces useSearchParams
### Prefetch: defaultPreload 'intent' replaces prefetchRouteModules.ts
### Context: auth + queryClient injected via router context

## Files to delete: AppRoutes.tsx, RouteGuards.tsx, prefetchRoutes.ts
## Files to create: ~25 route files, router.ts, routeTree.gen.ts (auto)
## Files to modify: ~64 files (react-router-dom → @tanstack/react-router imports)

## Migration mapping
- useNavigate() → useNavigate() (import change)
- useParams() → useParams({ from: '/route/$param' })
- useSearchParams() → useSearch({ from: '/route' })
- useLocation() → useRouterState({ select: s => s.location })
- Link → Link with params prop
- NavLink → Link with activeProps
