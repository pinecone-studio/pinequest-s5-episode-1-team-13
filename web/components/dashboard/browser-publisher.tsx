"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { IN_APP_HINT, isInAppBrowser } from "@/lib/in-app-browser";
import { startWhip } from "@/lib/webrtc";

const PUBLISH_RETRY_MS = 3000;

export type PublishState = "off" | "starting" | "on";

type Publisher = { wanted: boolean; stream: MediaStream | null; pc: RTCPeerConnection | null; timer?: ReturnType<typeof setTimeout> };

/**
 * BROWSER камер: энэ browser-ийн камерыг WHIP-ээр MediaMTX руу дамжуулна. Камерын tile-аас тусдаа: live view-д өөр камер
 * сонгоход (tile unmount) дамжуулалт тасрахгүй, AI видеогоо алдахгүй. Dashboard-оос гарахад (provider unmount) бүгд зогсоно.
 * Тасарвал (сүлжээ, backend redeploy) зогсоох хүртэл автоматаар дахин холбогдоно.
 */
class BrowserPublishers {
  private publishers = new Map<string, Publisher>();

  constructor(private onChange: (cameraId: string, state: PublishState, stream: MediaStream | null) => void) {}

  async start(cameraId: string) {
    if (this.publishers.get(cameraId)?.wanted) return; // давхар дарахаас хамгаална
    const p: Publisher = { wanted: true, stream: null, pc: null };
    this.publishers.set(cameraId, p);
    this.onChange(cameraId, "starting", null);
    if (isInAppBrowser(navigator.userAgent)) toast.warning("Энэ browser камер дамжуулахгүй байж магадгүй", { description: IN_APP_HINT });
    try {
      p.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    } catch (err) {
      this.stop(cameraId);
      const denied = err instanceof DOMException && err.name === "NotAllowedError";
      toast.error(denied ? "Камерын зөвшөөрөл олгогдсонгүй (browser-ийн хаягийн мөрөнд зөвшөөрнө үү)" : "Камерыг нээж чадсангүй");
      return;
    }
    if (!p.wanted) return this.release(p); // камерын зөвшөөрөл хүлээх зуур зогсоосон
    this.onChange(cameraId, "starting", p.stream);
    await this.connect(cameraId, p, true);
  }

  stop(cameraId: string) {
    const p = this.publishers.get(cameraId);
    if (p) {
      this.release(p);
      this.publishers.delete(cameraId);
    }
    this.onChange(cameraId, "off", null);
  }

  stopAll() {
    for (const cameraId of [...this.publishers.keys()]) this.stop(cameraId);
  }

  private release(p: Publisher) {
    p.wanted = false;
    clearTimeout(p.timer);
    p.pc?.close();
    p.pc = null;
    p.stream?.getTracks().forEach((t) => t.stop());
    p.stream = null;
  }

  private async connect(cameraId: string, p: Publisher, first: boolean) {
    if (!p.wanted || !p.stream) return;
    const retry = () => {
      if (!p.wanted) return;
      this.onChange(cameraId, "starting", p.stream);
      clearTimeout(p.timer);
      p.timer = setTimeout(() => void this.connect(cameraId, p, false), PUBLISH_RETRY_MS);
    };
    try {
      const access = await api.publish(cameraId);
      if (!p.wanted) return;
      const pc = await startWhip(
        access.whip_url,
        access.token,
        p.stream,
        () => {
          if (p.pc !== pc) return; // хуучин (солигдсон) session-ий event — одоогийнхыг хаахгүй
          pc.close();
          p.pc = null;
          retry();
        },
        access.ice_servers,
      );
      if (!p.wanted) return pc.close();
      p.pc = pc;
      this.onChange(cameraId, "on", p.stream);
      if (first) toast.success("Энэ төхөөрөмжийн камерыг дамжуулж байна");
    } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) { // эрхгүй/олдсонгүй — дахин оролдох утгагүй
        this.stop(cameraId);
        toast.error(err.message);
        return;
      }
      if (first) {
        const reason = err instanceof ApiError && err.status === 503 ? err.message : undefined;
        toast.error("Холбогдож чадсангүй — дахин оролдож байна…", { description: reason });
      }
      retry();
    }
  }
}

const PublisherContext = createContext<{ publishers: BrowserPublishers; states: Record<string, PublishState>; streams: Record<string, MediaStream | null> } | null>(null);

export function BrowserPublisherProvider({ children }: { children: React.ReactNode }) {
  const [states, setStates] = useState<Record<string, PublishState>>({});
  const [streams, setStreams] = useState<Record<string, MediaStream | null>>({});
  const [publishers] = useState(
    () => new BrowserPublishers((cameraId, state, stream) => {
      setStates((prev) => (prev[cameraId] === state ? prev : { ...prev, [cameraId]: state }));
      setStreams((prev) => (prev[cameraId] === stream ? prev : { ...prev, [cameraId]: stream }));
    }),
  );
  useEffect(() => () => publishers.stopAll(), [publishers]);
  return <PublisherContext.Provider value={{ publishers, states, streams }}>{children}</PublisherContext.Provider>;
}

export function useBrowserPublish(cameraId: string) {
  const ctx = useContext(PublisherContext);
  if (!ctx) throw new Error("useBrowserPublish: BrowserPublisherProvider дотор ашиглана");
  return {
    publishing: ctx.states[cameraId] ?? "off",
    startPublish: () => void ctx.publishers.start(cameraId),
    stopPublish: () => ctx.publishers.stop(cameraId),
  };
}

/** Энэ browser-ээс дамжуулж буй камерын урсгал. Хажуугийн жижиг дэлгэц WHIP-ийг дахин нээхгүй. */
export function usePublishPreview(cameraId: string): MediaStream | null {
  const ctx = useContext(PublisherContext);
  if (!ctx) throw new Error("usePublishPreview: BrowserPublisherProvider дотор ашиглана");
  return ctx.streams[cameraId] ?? null;
}
