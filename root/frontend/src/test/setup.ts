import { afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

afterEach(() => {
  cleanup();
});

beforeAll(() => {
  if (!("scrollTo" in window)) {
    Object.defineProperty(window, "scrollTo", {
      value: () => {},
      configurable: true,
      writable: true,
    });
  }

  if (typeof window.scrollTo !== "function") {
    Object.defineProperty(window, "scrollTo", {
      value: () => {},
      configurable: true,
      writable: true,
    });
  }

  if (!("matchMedia" in window)) {
    Object.defineProperty(window, "matchMedia", {
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
      configurable: true,
    });
  }

  if (typeof window.requestAnimationFrame !== "function") {
    window.requestAnimationFrame = (cb: FrameRequestCallback) =>
      setTimeout(() => cb(Date.now()), 0) as unknown as number;
  }

  if (typeof window.cancelAnimationFrame !== "function") {
    window.cancelAnimationFrame = (id: number) => {
      clearTimeout(id);
    };
  }

  if (!("scrollTo" in Element.prototype)) {
    Object.defineProperty(Element.prototype, "scrollTo", {
      value: function scrollTo(this: Element, options?: ScrollToOptions | number, y?: number) {
        if (typeof options === "object" && options !== null) {
          (this as unknown as { scrollTop: number }).scrollTop = options.top ?? 0;
        } else if (typeof options === "number") {
          (this as unknown as { scrollTop: number }).scrollTop = options;
          if (typeof y === "number") {
            (this as unknown as { scrollLeft: number }).scrollLeft = y;
          }
        }
      },
      configurable: true,
    });
  }
});
