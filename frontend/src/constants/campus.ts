export type CampusCoordinates = { readonly lat: number; readonly lon: number }

export const CAMPUS_COORDINATES: CampusCoordinates = Object.freeze({
  lat: 55.7144,
  lon: 37.81478,
})

/** Detail level where 44px campus markers remain individually operable. */
export const CAMPUS_DETAIL_ZOOM = 17

/** Minimum pointer and keyboard target size required by the map UI contract. */
export const MAP_INTERACTIVE_TARGET_PX = 44
