export {}

declare global {
  interface Window {
    trustedTypes?: TrustedTypePolicyFactory
  }
}
