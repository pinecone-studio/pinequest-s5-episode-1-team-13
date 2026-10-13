import { api } from "@/lib/api";
import type { RealtimeEvent } from "@/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8001/ws"; // worker.py-ийн backend порт

interface RealtimeClient {
  close: () => void;
}

/**
 * Auto-reconnect (exponential backoff) WebSocket. Нэвтрэлт: холбогдох бүрт /api/auth/ws-token-оос 60 сек-ийн токен авч
 * query-ээр өгнө (API нь Vercel proxy-оор явдаг тул session cookie backend-ийн домэйнд хүрэхгүй).
 */
export function connectRealtime(
  onEvent: (event: RealtimeEvent) => void,
  onStatus: (connected: boolean) => void,
): RealtimeClient {
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;

  const reconnect = () => {
    onStatus(false);
    const delay = Math.min(1000 * 2 ** attempt++, 15_000);
    timer = setTimeout(open, delay);
  };

  const open = async () => {
    let token: string;
    try {
      token = (await api.wsToken()).token;
    } catch {
      if (!closed) reconnect(); // нэвтрээгүй/сервер түр тасарсан
      return;
    }
    if (closed) return;
    socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);
    const current = socket;
    socket.onopen = () => {
      if (closed) return current.close();
      attempt = 0;
      onStatus(true);
      heartbeat = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 25_000);
    };
    socket.onmessage = (message) => {
      if (message.data === "pong") return;
      try {
        onEvent(JSON.parse(message.data) as RealtimeEvent);
      } catch {
        /* ignore malformed */
      }
    };
    socket.onclose = (event) => {
      clearInterval(heartbeat);
      if (closed) return; // хуучин (цэвэрлэгдсэн) холболтын дохио шинэ холболтын төлөвийг дарж болохгүй
      console.warn(`[realtime] WebSocket салсан (code=${event.code}) — ${Math.min(1000 * 2 ** attempt, 15_000) / 1000} сек дараа дахин оролдоно: ${WS_URL}`);
      reconnect();
    };
    socket.onerror = () => current.close();
  };

  void open();
  return {
    close: () => {
      closed = true;
      clearTimeout(timer);
      clearInterval(heartbeat);
      socket?.close();
    },
  };
}
