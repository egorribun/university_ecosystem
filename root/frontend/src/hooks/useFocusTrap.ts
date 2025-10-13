import { useEffect, useRef } from "react";
import type { FocusTrap, Options as FocusTrapOptions } from "focus-trap";
import { createFocusTrap } from "focus-trap";

type FocusTarget = FocusTrapOptions["initialFocus"];

export interface UseFocusTrapOptions {
  /** Whether the focus trap should be active. */
  active: boolean;
  /** Callback invoked when the underlying trap deactivates. */
  onDeactivate?: () => void;
  /** Element focused when the trap activates. */
  initialFocus?: FocusTarget;
  /** Fallback target if no focusable element is found. */
  fallbackFocus?: FocusTarget;
  /** Allow clicks outside of the trap without deactivating it. */
  allowOutsideClick?: boolean;
  /** Whether focus should return to the previously focused element. */
  returnFocus?: boolean;
}

const isBrowser = typeof document !== "undefined";

export default function useFocusTrap<T extends HTMLElement>({
  active,
  onDeactivate,
  initialFocus,
  fallbackFocus,
  allowOutsideClick = true,
  returnFocus = true,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T | null>(null);
  const trapRef = useRef<FocusTrap | null>(null);
  const deactivateRef = useRef(onDeactivate);

  deactivateRef.current = onDeactivate;

  useEffect(() => {
    if (!isBrowser) return undefined;

    const container = containerRef.current;
    if (!container || !active) {
      if (trapRef.current) {
        trapRef.current.deactivate({ returnFocus });
        trapRef.current = null;
      }
      return undefined;
    }

    const fallbackTarget: FocusTarget =
      typeof fallbackFocus !== "undefined"
        ? fallbackFocus
        : (() => {
            if (container.tabIndex < 0) container.tabIndex = -1;
            return container;
          }) as FocusTarget;

    const options: FocusTrapOptions = {
      allowOutsideClick,
      escapeDeactivates: true,
      returnFocusOnDeactivate: returnFocus,
      fallbackFocus: fallbackTarget,
    };

    if (initialFocus) options.initialFocus = initialFocus;

    const trap = createFocusTrap(container, {
      ...options,
      onDeactivate: () => {
        deactivateRef.current?.();
      },
    });

    trap.activate();
    trapRef.current = trap;

    return () => {
      trap.deactivate();
      trapRef.current = null;
    };
  }, [active, allowOutsideClick, fallbackFocus, initialFocus, returnFocus]);

  return containerRef;
}
