"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { TriangleAlert } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { formatConfidence, VIOLATION_LABEL, zoneLabel } from "@/lib/format";
import { playAlert, unlockAudio } from "@/lib/alert-sound";
import { connectRealtime } from "@/lib/websocket";
import type { RealtimeEvent } from "@/types";

type Listener = (event: RealtimeEvent) => void;

interface RealtimeState {
  connected: boolean;
  subscribe: (listener: Listener) => () => void;
}

const RealtimeContext = createContext<RealtimeState | null>(null);

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [connected, setConnected] = useState(false);
  const listeners = useRef(new Set<Listener>());
  const userId = user?.id;

  useEffect(() => {
    if (!userId) return;
    const unlock = () => unlockAudio(); // дуу гаргахыг browser зөвхөн хэрэглэгчийн үйлдлийн дараа зөвшөөрдөг
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    const client = connectRealtime(
      (event) => {
        if (event.type === "VIOLATION_CREATED") {
          const v = event.data;
          playAlert();
          toast.error("⚠️ PPE ЗӨРЧИЛ", {
            duration: 12_000,
            closeButton: true, // X дарж хаана
            icon: <TriangleAlert className="size-4" />,
            description: (
              <div className="space-y-0.5 text-xs">
                <div>Камер: <b>{v.camera_name}</b></div>
                <div>Зөрчил: <b>{VIOLATION_LABEL[v.violation_type].toUpperCase()}</b></div>
                <div>Бүс: <b>{zoneLabel(v.zone)}</b></div>
                <div>Итгэлцэл: <b>{formatConfidence(v.confidence)}</b></div>
              </div>
            ),
          });
        }
        listeners.current.forEach((listener) => listener(event));
      },
      setConnected,
    );
    return () => {
      client.close();
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, [userId]);

  const subscribe = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  const value = useMemo(() => ({ connected, subscribe }), [connected, subscribe]);
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtimeStatus(): boolean {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtimeStatus must be used within RealtimeProvider");
  return ctx.connected;
}

/** WebSocket event-д бүртгүүлнэ. handler өөрчлөгдөхөд дахин бүртгэх шаардлагагүй. */
export function useRealtimeEvents(handler: Listener): void {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtimeEvents must be used within RealtimeProvider");
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const { subscribe } = ctx;
  useEffect(() => subscribe((event) => latest.current(event)), [subscribe]);
}
