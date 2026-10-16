"use client";

import { useState } from "react";
import { Video, VideoOff } from "lucide-react";

import { CameraTile } from "@/components/dashboard/camera-tile";
import { CAMERA_STATUS_LABEL, cameraTone, zoneLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Camera } from "@/types";

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

function CameraListItem({ camera, selected, onSelect }: { camera: Camera; selected: boolean; onSelect: (id: string) => void }) {
  const tone = cameraTone(camera.status);
  const unavailable = !camera.enabled || camera.status === "OFFLINE" || camera.status === "ERROR";
  const Icon = unavailable ? VideoOff : Video;

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
        <div className="grid aspect-video w-[7.25rem] shrink-0 place-items-center overflow-hidden rounded-lg bg-muted text-muted-foreground md:w-full lg:w-28">
          <Icon className="size-4" />
        </div>
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

/** Сонгосон камер л WHEP урсгал нээнэ. Жагсаалт нь төлөвийн зураг, урсгал давхардуулахгүй. */
export function CameraWorkspace({ cameras }: { cameras: Camera[] }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = cameras.find((camera) => camera.id === activeId) ?? cameras[0];
  if (!active) return null;

  return (
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
  );
}
