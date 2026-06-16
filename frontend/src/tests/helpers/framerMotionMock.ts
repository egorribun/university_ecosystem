import { createElement, Fragment, type ElementType, type ReactNode } from "react"

/**
 * Shared framer-motion mock for jsdom render-tests (SESSION 13 sweep).
 *
 * Storybook stories prove a component renders in real Chromium, but a jsdom
 * render-test still needs framer-motion stubbed out: `m.*` / `motion.*` become
 * plain host elements (animation props stripped), `AnimatePresence` / `LazyMotion`
 * / `MotionConfig` become passthroughs, and the motion-value hooks return inert
 * stubs. Mirrors the inline mock in `NotificationsBell.test.tsx` but de-duplicated
 * across the ~25 sweep files via an async `vi.mock` factory:
 *
 *   vi.mock("framer-motion", async () =>
 *     (await import("@/tests/helpers/framerMotionMock")).framerMotionMock())
 *
 * (`vi.mock` is hoisted above imports, so the factory must be async + import the
 * helper lazily rather than closing over a top-level import.)
 */

type MotionLikeProps = Record<string, unknown> & { children?: ReactNode }

// framer-motion-only props that must NOT reach the DOM element.
const MOTION_ONLY_PROPS = new Set<string>([
  "initial",
  "animate",
  "exit",
  "variants",
  "transition",
  "whileHover",
  "whileTap",
  "whileFocus",
  "whileDrag",
  "whileInView",
  "whilePress",
  "viewport",
  "layout",
  "layoutId",
  "layoutScroll",
  "layoutDependency",
  "layoutRoot",
  "drag",
  "dragConstraints",
  "dragElastic",
  "dragMomentum",
  "dragSnapToOrigin",
  "dragTransition",
  "dragControls",
  "onAnimationStart",
  "onAnimationComplete",
  "onUpdate",
  "onHoverStart",
  "onHoverEnd",
  "onTap",
  "onTapStart",
  "onTapCancel",
  "onDrag",
  "onDragStart",
  "onDragEnd",
  "onDirectionLock",
  "custom",
  "transformTemplate",
  "transformValues",
  "inherit",
])

const componentCache = new Map<string, ReturnType<typeof buildMotionComponent>>()

function buildMotionComponent(tag: string) {
  function MotionMock(props: MotionLikeProps) {
    const cleaned: Record<string, unknown> = {}
    for (const key of Object.keys(props)) {
      if (key === "children") continue
      if (MOTION_ONLY_PROPS.has(key)) continue
      cleaned[key] = props[key]
    }
    return createElement(tag as ElementType, cleaned, props.children)
  }
  MotionMock.displayName = `motion.${tag}`
  return MotionMock
}

const motionProxy = new Proxy(
  {},
  {
    get(_target, key) {
      if (typeof key !== "string") return undefined
      let cached = componentCache.get(key)
      if (!cached) {
        cached = buildMotionComponent(key)
        componentCache.set(key, cached)
      }
      return cached
    },
  }
) as Record<string, ReturnType<typeof buildMotionComponent>>

function motionValue(initial: unknown) {
  return {
    get: () => initial,
    set: () => {},
    on: () => () => {},
    destroy: () => {},
    clearListeners: () => {},
  }
}

function Passthrough({ children }: { children?: ReactNode }) {
  return createElement(Fragment, null, children)
}

export function framerMotionMock() {
  return {
    motion: motionProxy,
    m: motionProxy,
    AnimatePresence: Passthrough,
    LazyMotion: Passthrough,
    MotionConfig: Passthrough,
    LayoutGroup: Passthrough,
    domAnimation: {},
    domMax: {},
    useReducedMotion: () => true,
    useMotionValue: (initial: unknown) => motionValue(initial),
    useTransform: () => motionValue(0),
    useSpring: (value: unknown) =>
      value && typeof value === "object" ? value : motionValue(value),
    useScroll: () => ({
      scrollX: motionValue(0),
      scrollY: motionValue(0),
      scrollXProgress: motionValue(0),
      scrollYProgress: motionValue(0),
    }),
    useVelocity: () => motionValue(0),
    useMotionTemplate: () => "",
    useInView: () => true,
    useAnimation: () => ({ start: () => Promise.resolve(), stop: () => {}, set: () => {} }),
    useAnimationControls: () => ({ start: () => Promise.resolve(), stop: () => {}, set: () => {} }),
  }
}
