/// <reference types="vite/client" />

interface SyncManager {
  getTags(): Promise<string[]>;
  register(tag: string): Promise<void>;
}

interface ServiceWorkerRegistration {
  readonly sync: SyncManager;
}

interface Window {
  otel?: {
    recordMetric?: (name: string, value: number, tags?: Record<string, string>) => void;
  };
}

// Service Worker Globals
interface ServiceWorkerGlobalScope {
  __SW_TESTING__?: {
    storePendingNavigation: unknown;
    storePendingReport: unknown;
    readPendingNavigations: unknown;
    readPendingReports: unknown;
    processPendingNavigations: unknown;
    processPendingReports: unknown;
    processAllQueues: unknown;
    handleMediaRequest: unknown;
  };
}
