/*
 * Native transition selection adapted from @tanstack/router-core 1.171.32,
 * src/router.ts, RouterCore.startViewTransition (MIT).
 * Repository: https://github.com/TanStack/router (packages/router-core)
 *
 * Copyright (c) 2021-present Tanner Linsley
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
import { getLocationChangeInfo, type AnyRouter } from "@tanstack/router-core"
import { isServer } from "@tanstack/router-core/isServer"

/** Own each router's native animation promise without changing DOM update errors. */
export function configureRouterViewTransitions(router: AnyRouter): void {
  router.startViewTransition = (update) => {
    const option = router.shouldViewTransition ?? router.options.defaultViewTransition
    router.shouldViewTransition = undefined

    if (
      !option ||
      (isServer ?? typeof document === "undefined") ||
      typeof document.startViewTransition !== "function"
    ) {
      return update()
    }

    let parameters: (() => Promise<void>) | { update: () => Promise<void>; types: string[] } =
      update
    if (
      typeof option === "object" &&
      window.CSS?.supports?.("selector(:active-view-transition-type(a))")
    ) {
      const types =
        typeof option.types === "function"
          ? option.types(
              getLocationChangeInfo(router.latestLocation, router.stores.resolvedLocation.get())
            )
          : option.types
      if (types === false) return update()
      parameters = { update, types }
    }

    let callbackFailed = false
    let callbackFailure: unknown
    const updateNative = async () => {
      try {
        await update()
      } catch (error: unknown) {
        callbackFailed = true
        callbackFailure = error
        throw error
      }
    }
    const transition = document.startViewTransition(
      typeof parameters === "function" ? updateNative : { ...parameters, update: updateNative }
    )
    // A superseding navigation rejects ready with a native AbortError even
    // though its DOM update still runs. TanStack awaits updateCallbackDone
    // only, leaving ready unobserved. Handle that animation cancellation here;
    // callback failures still reject the original navigation promise below.
    // The browser also mirrors callback failure into ready, marking it handled
    // to avoid a duplicate error. Preserve that ownership without observing
    // updateCallbackDone here; an unhandled callback failure must stay visible.
    // Independent readiness failures remain observable.
    // https://www.w3.org/TR/css-view-transitions-1/#viewtransition
    void transition.ready.catch((error: unknown) => {
      if (callbackFailed && Object.is(error, callbackFailure)) return
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error
    })
    return transition.updateCallbackDone
  }
}
