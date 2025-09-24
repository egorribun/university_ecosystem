declare module "workbox-precaching" {
  export const precacheAndRoute: (...args: any[]) => void
  export const cleanupOutdatedCaches: (...args: any[]) => void
}

declare module "workbox-routing" {
  export const registerRoute: (...args: any[]) => void
}

declare module "workbox-strategies" {
  export class CacheFirst {
    constructor(options?: any)
  }
  export class NetworkFirst {
    constructor(options?: any)
    handle?(...args: any[]): Promise<Response>
  }
  export class StaleWhileRevalidate {
    constructor(options?: any)
  }
}

declare module "workbox-recipes" {
  export const warmStrategyCache: (...args: any[]) => void
}
