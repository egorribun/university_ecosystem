import { createContext, useContext } from "react"

/** The initial profile/key request is still settling in the surrounding provider. */
export const AuthBootstrapContext = createContext(false)

/** Standalone consumers retain their existing behavior outside an auth provider. */
export const useAuthBootstrapPending = () => useContext(AuthBootstrapContext)
