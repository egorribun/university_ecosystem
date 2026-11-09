import { CancelledError, MutationCache } from "@tanstack/react-query"
import { captureSessionEpoch } from "@/stores/sessionEpoch"

const SESSION_GENERATION_STORAGE_KEY = "ecosystem.session.generation.v1"

/** Bind mutation functions, lifecycle options and per-call observer callbacks
 * to the account that created them. Removing a MutationCache entry alone does
 * not cancel any of these callbacks in TanStack Query. */
export function createSessionMutationCache() {
  const cache = new MutationCache()
  type Owner = { owns: () => boolean; retire: () => void }
  const mutationOwners = new WeakMap<object, Owner>()
  const observerOwners = new WeakMap<object, () => boolean>()
  const wrappedObservers = new WeakSet<object>()
  const activeOwners = new Set<Owner>()
  let detachStorage: (() => void) | undefined
  const releaseOwner = (owner: Owner) => {
    activeOwners.delete(owner)
    if (activeOwners.size === 0) {
      detachStorage?.()
      detachStorage = undefined
    }
  }
  const retainOwner = (owner: Owner) => {
    activeOwners.add(owner)
    if (activeOwners.size !== 1 || typeof window === "undefined") return
    const onStorage = (event: StorageEvent) => {
      if (event.key !== null && event.key !== SESSION_GENERATION_STORAGE_KEY) return
      try {
        if (event.storageArea && event.storageArea !== window.localStorage) return
      } catch {
        // Unavailable local storage cannot prove the session is current.
      }
      activeOwners.forEach((current) => current.retire())
    }
    window.addEventListener("storage", onStorage)
    detachStorage = () => window.removeEventListener("storage", onStorage)
  }
  cache.subscribe((event) => {
    if (event.type === "added") {
      const mutation = event.mutation
      const ownsEpoch = captureSessionEpoch()
      let retired = false
      const owner: Owner = {
        owns: () => {
          if (!ownsEpoch()) retired = true
          return !retired
        },
        retire: () => {
          retired = true
        },
      }
      const owns = owner.owns
      mutationOwners.set(mutation, owner)
      retainOwner(owner)
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
    if (event.type === "removed" && event.mutation.state.status !== "pending") {
      const owner = mutationOwners.get(event.mutation)
      if (owner) releaseOwner(owner)
    }
    if (
      event.type === "updated" &&
      (event.action.type === "success" || event.action.type === "error")
    ) {
      const owner = mutationOwners.get(event.mutation)
      if (owner) releaseOwner(owner)
    }
    if (event.type === "observerAdded") {
      const observer = event.observer
      observerOwners.set(
        observer,
        mutationOwners.get(event.mutation)?.owns ?? captureSessionEpoch()
      )
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
