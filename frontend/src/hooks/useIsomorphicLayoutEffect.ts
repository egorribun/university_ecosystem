import { useEffect, useLayoutEffect } from "react"

/**
 * @fileoverview Wave 128 SW3 — SSR-warning-free useLayoutEffect.
 *
 * `useLayoutEffect` throws a React SSR warning ("useLayoutEffect does
 * nothing on the server. To avoid this, use useEffect instead."). This
 * helper picks `useEffect` on the server (same skip behavior, no warning)
 * and `useLayoutEffect` on the client (still runs synchronously after
 * DOM mutation as designed).
 *
 * Selector executes ONCE at module load — `typeof window` evaluation is
 * stable per-runtime: undefined on Node SSR, defined in browsers + jsdom.
 * The chosen ref is captured for all consumers.
 *
 * Used by `MobileBottomNav.tsx` for sessionStorage scroll-restore handling
 * surfaced as SSR-warning during W128 plan exploration.
 */
export const useIsomorphicLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect
