import { CancelledError, MutationCache } from "@tanstack/react-query"
import { captureSessionEpoch } from "@/stores/sessionEpoch"

/** Bind mutation functions, lifecycle options and per-call observer callbacks
 * to the account that created them. Removing a MutationCache entry alone does
 * not cancel any of these callbacks in TanStack Query. */
export function createSessionMutationCache() {
  const cache = new MutationCache()
  const mutationOwners = new WeakMap<object, () => boolean>()
  const observerOwners = new WeakMap<object, () => boolean>()
  const wrappedObservers = new WeakSet<object>()
  cache.subscribe((event) => {
    if (event.type === "added") {
      const mutation = event.mutation
      const owns = captureSessionEpoch()
      mutationOwners.set(mutation, owns)
      const setOptions = mutation.setOptions.bind(mutation)
      // MutationObserver updates options during rerenders, even after a request
      // starts. Retain the original lifetime fence across those replacements.
      mutation.setOptions = (options) => {
        setOptions({
          ...options,
          mutationFn: options.mutationFn
            ? (...args) => {
                if (!owns()) return Promise.reject(new CancelledError({ silent: true }))
                return options.mutationFn!(...args)
              }
            : undefined,
          onMutate: options.onMutate
            ? (...args) => {
                if (!owns()) throw new CancelledError({ silent: true })
                return options.onMutate!(...args)
              }
            : undefined,
          onSuccess: (...args) => (owns() ? options.onSuccess?.(...args) : undefined),
          onError: (...args) => (owns() ? options.onError?.(...args) : undefined),
          onSettled: (...args) => (owns() ? options.onSettled?.(...args) : undefined),
        })
      }
      mutation.setOptions(mutation.options)
    }
    if (event.type === "observerAdded") {
      const observer = event.observer
      observerOwners.set(observer, mutationOwners.get(event.mutation) ?? captureSessionEpoch())
      if (wrappedObservers.has(observer)) return
      wrappedObservers.add(observer)
      const update = observer.onMutationUpdate.bind(observer)
      observer.onMutationUpdate = (action) => {
        if (!observerOwners.get(observer)?.()) {
          observer.reset()
          return
        }
        update(action)
      }
    }
  })
  return cache
}
