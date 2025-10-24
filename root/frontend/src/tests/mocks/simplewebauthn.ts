export const startAuthentication = async () => ({
  id: "test-credential",
  rawId: "dGVzdC1jcmVkZW50aWFs",
  response: {
    clientDataJSON: "",
    authenticatorData: "",
    signature: "",
    userHandle: null,
  },
  type: "public-key",
  clientExtensionResults: () => ({}),
  authenticatorAttachment: "platform",
  toJSON() {
    return {
      id: "test-credential",
      rawId: "dGVzdC1jcmVkZW50aWFs",
      response: {
        clientDataJSON: "",
        authenticatorData: "",
        signature: "",
        userHandle: null,
      },
      type: "public-key",
      clientExtensionResults: {},
      authenticatorAttachment: "platform",
    }
  },
})

export const startRegistration = async () => ({
  id: "test-registration",
  rawId: "dGVzdC1yZWc=",
  response: {
    clientDataJSON: "",
    attestationObject: "",
  },
  type: "public-key",
  clientExtensionResults: () => ({}),
  authenticatorAttachment: "platform",
  toJSON() {
    return {
      id: "test-registration",
      rawId: "dGVzdC1yZWc=",
      response: {
        clientDataJSON: "",
        attestationObject: "",
      },
      type: "public-key",
      clientExtensionResults: {},
      authenticatorAttachment: "platform",
    }
  },
})
