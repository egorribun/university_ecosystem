import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/api/axios";

export type AppNotification = {
  id: number | string;
  title: string;
  body?: string;
  type?: string;
  url?: string;
  created_at: string;
  read?: boolean;
  avatar_url?: string;
  icon?: string;
};

type Page = {
  items: AppNotification[];
  unread_count: number;
  has_more: boolean;
};

async function fetchPage(limit: number, offset: number): Promise<Page> {
  const r = await api.get("/notifications", { params: { limit, offset } });
  return r.data;
}

async function markReadApi(ids: Array<number | string>) {
  await api.post("/notifications/mark-read", { ids });
}

async function markAllReadApi() {
  await api.post("/notifications/mark-all-read");
}

const PAGE_SIZE = 20;

export function useNotifications() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const unreadFromServer = useRef(0);
  const seenIds = useRef<Set<string | number>>(new Set());

  const unreadCount = useMemo(() => {
    const local = items.reduce((acc, n) => acc + (n.read ? 0 : 1), 0);
    return Math.max(local, unreadFromServer.current);
  }, [items]);

  const load = useCallback(
    async (reset = false) => {
      setLoading(true);
      try {
        const curOffset = reset ? 0 : offset;
        const page = await fetchPage(PAGE_SIZE, curOffset);
        unreadFromServer.current = page.unread_count ?? 0;
        setItems(prev => {
          const base = reset ? [] : prev;
          const next: AppNotification[] = [];
          for (const n of page.items) {
            if (!seenIds.current.has(n.id)) {
              seenIds.current.add(n.id);
              next.push(n);
            }
          }
          return [...base, ...next];
        });
        setHasMore(Boolean(page.has_more));
        setOffset(curOffset + page.items.length);
      } finally {
        setLoading(false);
        setInitialized(true);
      }
    },
    [offset]
  );

  const loadMore = useCallback(async () => {
    if (!hasMore || loading) return;
    await load(false);
  }, [hasMore, loading, load]);

  const markRead = useCallback(async (id: number | string) => {
    setItems(prev => prev.map(n => (n.id === id ? { ...n, read: true } : n)));
    if (unreadFromServer.current > 0) unreadFromServer.current -= 1;
    try {
      await markReadApi([id]);
    } catch {}
  }, []);

  const markAllRead = useCallback(async () => {
    setItems(prev => prev.map(n => ({ ...n, read: true })));
    unreadFromServer.current = 0;
    try {
      await markAllReadApi();
    } catch {}
  }, []);

  useEffect(() => {
    load(true);
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
        const n = msg.payload;
        const id = n?.data?.id ?? n?.id ?? crypto.randomUUID();
        if (!seenIds.current.has(id)) {
          const at = new Date(n?.timestamp || Date.now()).toISOString();
          const next: AppNotification = {
            id,
            title: n.title || "Уведомление",
            body: n.body || "",
            url: n.data?.url || n.url || "/",
            type: n.data?.type || n.type,
            created_at: at,
            read: false,
            icon: n.icon
          };
          seenIds.current.add(id);
          setItems(prev => [next, ...prev]);
          unreadFromServer.current += 1;
        }
      }
      if (msg?.type === "NOTIFICATION_MARK_READ" && msg.id != null) {
        setItems(prev => prev.map(n => (n.id === msg.id ? { ...n, read: true } : n)));
        markRead(msg.id);
      }
    };
    navigator.serviceWorker.addEventListener("message", onMsg);
    return () => navigator.serviceWorker.removeEventListener("message", onMsg);
  }, [markRead]);

  return { items, loading: loading && !initialized, unreadCount, hasMore, loadMore, markRead, markAllRead };
}