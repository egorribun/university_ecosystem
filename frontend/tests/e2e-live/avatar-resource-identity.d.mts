export interface PersistedAvatarIdentityInput {
  readonly savedProfileAvatarUrl: string | null
  readonly reloadedProfileAvatarUrl: string | null
  readonly savedRenderedSrc: string | null
  readonly reloadedRenderedSrc: string | null
  readonly baseUrl: string
}

export interface PersistedAvatarIdentityComparison {
  readonly profileValueMatches: boolean
  readonly renderedSourceMatches: boolean
}

export function renderedAvatarResourceMatches(
  savedRenderedSrc: string | null,
  reloadedRenderedSrc: string | null,
  baseUrl: string
): boolean
export function comparePersistedAvatarIdentity(
  input: PersistedAvatarIdentityInput
): PersistedAvatarIdentityComparison
