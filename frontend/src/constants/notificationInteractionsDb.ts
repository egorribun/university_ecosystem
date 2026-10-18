/**
 * IndexedDB database shared by the page (useNewsInteraction) and the service
 * worker (sw/offline). Both must open the same version: once the service worker
 * upgrades the database, a page that still opens an older version fails with
 * VersionError and its offline queue stops working.
 */
export const NOTIFICATION_INTERACTIONS_DB_NAME = "notification-interactions"
export const NOTIFICATION_INTERACTIONS_DB_VERSION = 4
