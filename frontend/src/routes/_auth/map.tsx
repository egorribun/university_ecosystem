import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { mapSearchSchema } from "@/features/map/schema"
import { loadMapLibre } from "@/features/map/loadMapLibre"

const MapPage = lazy(() => import("@/pages/Map"))

export const Route = createFileRoute("/_auth/map")({
  beforeLoad: ({ cause }) =>
    cause === "preload"
      ? loadMapLibre().then(
          () => undefined,
          () => undefined
        )
      : undefined,
  // Wave 127 SW6 — explicit 'data-only' override. Currently SILENTLY IGNORED
  // because parent `_auth.tsx` is `ssr: false` (more restrictive); per
  // TanStack Start v1 SSR inheritance contract, a child can only make SSR
  // MORE restrictive than its parent — `'data-only'` is more permissive than
  // `false`, so this annotation has no runtime effect today.
  //
  // Documented in code so the intent is preserved for W128+ work: when
  // `_auth.tsx` flips to `'data-only'` (or `true`), this child stays at
  // `'data-only'` rather than getting promoted, because /map mounts
  // maplibre-gl-js (heavy WebGL/canvas) + WeatherParticles canvas — components
  // unsafe for SSR rendering. data-only is the right escape hatch per
  // selective-ssr docs: loader + beforeLoad run server-side, component on
  // client.
  ssr: "data-only",
  validateSearch: (search: Record<string, unknown>) => v.parse(mapSearchSchema, search),
  component: MapPage,
})
