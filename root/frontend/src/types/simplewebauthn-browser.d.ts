declare module "@simplewebauthn/browser" {
  export type AuthenticationResponseJSON = {
    id: string
    rawId: string
    response: Record<string, unknown>
    type: string
    authenticatorAttachment?: string | null
    clientExtensionResults?: Record<string, unknown>
    userHandle?: string | null
  }

  export type PublicKeyCredentialRequestOptionsJSON = Record<string, unknown>
  export type PublicKeyCredentialCreationOptionsJSON = Record<string, unknown>

  export type RegistrationResponseJSON = {
    id: string
    rawId: string
    response: Record<string, unknown>
    type: string
    authenticatorAttachment?: string | null
    clientExtensionResults?: Record<string, unknown>
  }

  export type StartAuthenticationOptions = {
    optionsJSON: PublicKeyCredentialRequestOptionsJSON
    useBrowserAutofill?: boolean
  }

  export type StartRegistrationOptions = {
    optionsJSON: PublicKeyCredentialCreationOptionsJSON
    useBrowserAutofill?: boolean
  }

  export function startAuthentication(
    options: StartAuthenticationOptions
  ): Promise<AuthenticationResponseJSON>

  export function startRegistration(
    options: StartRegistrationOptions
  ): Promise<RegistrationResponseJSON>
}
