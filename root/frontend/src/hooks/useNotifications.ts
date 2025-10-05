import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationListResponse,
} from "@/api/notifications";

export type AppNotification = {
  id: number | string;
  title: string;
  body?: string;
  type?: string;
  url?: string;
  created_at: string;
  read: boolean;
  read_at?: string;
  avatar_url?: string;
  icon?: string;
};

const PAGE_SIZE = 20;

type LoadMode = "reset" | "append";

function normalizeItem(item: NotificationListResponse["items"][number]): AppNotification {
  return {
    id: item.id,
    title: item.title,
    body: item.body ?? undefined,
    type: item.type ?? undefined,
    url: item.url ?? undefined,
    created_at: item.created_at,
    read: Boolean(item.read),
    read_at: item.read_at ?? undefined,
  };
}

export function useNotifications() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const unreadFromServer = useRef(0);
  const seenIds = useRef<Set<string | number>>(new Set());
  const nextCursorRef = useRef<string | null>(null);
  const loadingRef = useRef(false);
  const hasMoreRef = useRef(false);
  const initializedRef = useRef(false);

  const unreadCount = useMemo(() => {
    const local = items.reduce((acc, n) => acc + (n.read ? 0 : 1), 0);
    return Math.max(local, unreadFromServer.current);
  }, [items]);

  const load = useCallback(async (mode: LoadMode = "reset") => {
    if (mode === "append" && (loadingRef.current || !hasMoreRef.current)) {
      return;
    }

    loadingRef.current = true;
    setFetching(true);
    const showLoader = !initializedRef.current || mode === "reset";
    if (showLoader) {
      setLoading(true);
    }

    try {
      const cursor = mode === "append" ? nextCursorRef.current : null;
      const page = await fetchNotifications({ limit: PAGE_SIZE, cursor });
      unreadFromServer.current = page.unread_count ?? 0;
      setHasMore(Boolean(page.has_more));
      hasMoreRef.current = Boolean(page.has_more);
      nextCursorRef.current = page.next_cursor ?? null;

      const mapped = page.items.map(normalizeItem);

      setItems(prev => {
        if (mode === "reset") {
          seenIds.current = new Set();
        }

        const map = new Map<string | number, AppNotification>();
        if (mode !== "reset") {
          for (const it of prev) {
            map.set(it.id, it);
          }
        }

        for (const it of mapped) {
          map.set(it.id, it);
          seenIds.current.add(it.id);
        }

        const next = Array.from(map.values());
        next.sort((a, b) => {
          const diff = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
          if (diff !== 0) return diff;
          const aId = typeof a.id === "number" ? a.id : Number.parseInt(String(a.id), 10);
          const bId = typeof b.id === "number" ? b.id : Number.parseInt(String(b.id), 10);
          if (Number.isFinite(aId) && Number.isFinite(bId)) return bId - aId;
          return String(b.id).localeCompare(String(a.id));
        });
        return next;
      });
    } catch (error) {
      console.error("Failed to load notifications", error);
      if (mode === "append") {
        setHasMore(false);
        hasMoreRef.current = false;
      }
    } finally {
      loadingRef.current = false;
      setFetching(false);
      if (showLoader) {
        setLoading(false);
      }
      if (!initializedRef.current) {
        initializedRef.current = true;
        setInitialized(true);
      }
    }
  }, []);

  const loadMore = useCallback(async () => {
    await load("append");
  }, [load]);

  const markRead = useCallback(async (id: number | string) => {
    const nowIso = new Date().toISOString();
    setItems(prev =>
      prev.map(n => (n.id === id ? { ...n, read: true, read_at: n.read_at ?? nowIso } : n))
    );
    if (unreadFromServer.current > 0) unreadFromServer.current -= 1;
    if (typeof id === "number") {
      try {
        await markNotificationRead(id);
      } catch (error) {
        console.error("Failed to mark notification read", error);
      }
    }
  }, []);

  const markAllRead = useCallback(async () => {
    const nowIso = new Date().toISOString();
    setItems(prev => prev.map(n => ({ ...n, read: true, read_at: n.read_at ?? nowIso })));
    unreadFromServer.current = 0;
    try {
      await markAllNotificationsRead();
    } catch (error) {
      console.error("Failed to mark all notifications read", error);
    }
  }, []);

  const refresh = useCallback(async () => {
    await load("reset");
  }, [load]);

  useEffect(() => {
    void load("reset");
  }, [load]);

  useEffect(() => {
    if ("setAppBadge" in navigator) {
      try {
        const nav: any = navigator;
        if (unreadCount > 0) nav.setAppBadge(unreadCount);
        else nav.clearAppBadge?.();
      } catch {}
    }
  }, [unreadCount]);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const onMsg = (e: MessageEvent) => {
      const msg: any = e.data ?? {};
      if (msg?.type === "PUSH_NOTIFICATION") {
        void refresh();
      }
      if (msg?.type === "NOTIFICATION_MARK_READ" && msg.id != null) {
        void markRead(msg.id);
      }
    };
    navigator.serviceWorker.addEventListener("message", onMsg);
    return () => navigator.serviceWorker.removeEventListener("message", onMsg);
  }, [markRead, refresh]);

  return {
    items,
    loading: loading && !initialized,
    unreadCount,
    hasMore,
    loadMore,
    markRead,
    markAllRead,
    refresh,
    fetching,
  };
}