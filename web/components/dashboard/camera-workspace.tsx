"use client";

import { useEffect, useState } from "react";
import { Video, VideoOff } from "lucide-react";

import { BrowserPublisherProvider, usePublishPreview } from "@/components/dashboard/browser-publisher";
import { CameraTile } from "@/components/dashboard/camera-tile";
import { api, ApiError } from "@/lib/api";
import { CAMERA_STATUS_LABEL, cameraTone, zoneLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { startWhep } from "@/lib/webrtc";
import type { Camera } from "@/types";

const PREVIEW_RETRY_MS = 2000;
const PREVIEW_OFFLINE_RETRY_MS = 5000;

const STATUS_DOT = {
  good: "bg-success",
  warn: "bg-warning",
  bad: "bg-danger",
  idle: "bg-muted-foreground/70",
} as const;

const STATUS_TEXT = {
  good: "text-success",
  warn: "text-warning",
  bad: "text-danger",
  idle: "text-muted-foreground",
} as const;

function ListPreview({ camera, previewStream }: { camera: Camera; previewStream: MediaStream | null }) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const live = camera.enabled && (camera.status === "STREAMING" || camera.status === "ONLINE");
  const mirror = (camera.camera_type === "LOCAL_WEBCAM" || camera.camera_type === "BROWSER") && camera.mirror;
  const Icon = !camera.enabled || camera.status === "OFFLINE" || camera.status === "ERROR" ? VideoOff : Video;

  useEffect(() => {
    if (!video || !previewStream) return;
    video.srcObject = previewStream;
    void video.play().catch(() => undefined);
    return () => {
      video.srcObject = null;
    };
  }, [video, previewStream]);

  useEffect(() => {
    if (previewStream || !live || !video) return;
    let cancelled = false;
    let pc: RTCPeerConnection | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const retry = (wait = PREVIEW_RETRY_MS) => {
      pc?.close();
      pc = null;
      if (!cancelled) timer = setTimeout(connect, wait);
    };
    const connect = async () => {
      try {
        const access = await api.webrtc(camera.id);
        if (cancelled) return;
        pc = await startWhep(access.whep_url, access.token, (stream) => { video.srcObject = stream; }, () => retry(), access.ice_servers);
        if (cancelled) pc.close();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return;
        retry(err instanceof ApiError && err.status === 503 ? PREVIEW_OFFLINE_RETRY_MS : PREVIEW_RETRY_MS);
      }
    };
    connect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      pc?.close();
      video.srcObject = null;
    };
  }, [previewStream, live, video, camera.id]);

  return (
    <div className="relative grid aspect-video w-[7.25rem] shrink-0 place-items-center overflow-hidden rounded-lg bg-muted text-muted-foreground md:w-full lg:w-28">
      {(previewStream || live) && (
        <video
          ref={setVideo}
          autoPlay
          muted
          playsInline
          onPlaying={() => setPlaying(true)}
          onEmptied={() => setPlaying(false)}
          className={cn("absolute inset-0 size-full object-cover", mirror && "-scale-x-100")}
        />
      )}
      {!playing && <Icon className="relative size-4" />}
    </div>
  );
}

function CameraListItem({ camera, selected, onSelect }: { camera: Camera; selected: boolean; onSelect: (id: string) => void }) {
  const tone = cameraTone(camera.status);
  const previewStream = usePublishPreview(camera.id);

  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(camera.id)}
        className={cn(
          "flex w-full min-w-0 flex-row items-center gap-2.5 rounded-xl border border-border bg-card p-2 text-left shadow-surface transition-colors hover:bg-muted md:flex-col md:items-stretch lg:flex-row lg:items-center",
          selected && "border-foreground/20 bg-muted hover:bg-muted",
        )}
      >
        <ListPreview camera={camera} previewStream={previewStream} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{camera.name}</div>
          <div className="mt-0.5 truncate text-[13px] text-muted-foreground">{camera.zone ? zoneLabel(camera.zone) : "Бүсгүй"}</div>
          <div className="mt-1.5 flex min-w-0 items-center gap-1.5">
            <span className={cn("size-1.5 shrink-0 rounded-full", STATUS_DOT[tone])} />
            <span className={cn("truncate text-xs font-medium", STATUS_TEXT[tone])}>{CAMERA_STATUS_LABEL[camera.status]}</span>
          </div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">{camera.ai_enabled ? "AI асаалттай" : "AI унтраалттай"}</div>
        </div>
      </button>
    </li>
  );
}

/** Том дэлгэц сонгосон камерыг тоглуулна. Хажуугийн жижиг камер дамжуулалтаа тусад нь тоглуулна.
 * Browser камерын дамжуулалт (WHIP) энд амьдарна: өөр камер сонгоход тасрахгүй. */
export function CameraWorkspace({ cameras }: { cameras: Camera[] }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = cameras.find((camera) => camera.id === activeId) ?? cameras[0];
  if (!active) return null;

  return (
    <BrowserPublisherProvider>
      <div className="grid grid-cols-1 items-start gap-5 md:grid-cols-[minmax(0,1fr)_minmax(8.75rem,30%)] lg:grid-cols-[minmax(0,1fr)_minmax(16rem,28%)] lg:gap-6">
        <div className="min-w-0">
          <CameraTile key={active.id} camera={active} />
        </div>
        <ul aria-label="Камерууд" className="flex min-h-0 min-w-0 flex-col gap-3 md:max-h-[calc(100dvh-7rem)] md:overflow-y-auto">
          {cameras.map((camera) => (
            <CameraListItem key={camera.id} camera={camera} selected={camera.id === active.id} onSelect={setActiveId} />
          ))}
        </ul>
      </div>
    </BrowserPublisherProvider>
  );
}
