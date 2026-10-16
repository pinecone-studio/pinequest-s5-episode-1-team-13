"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ShieldBan, Trash2, Undo2, X } from "lucide-react";
import { toast } from "sonner";

import { useRealtimeEvents } from "@/components/providers/realtime-provider";
import { api } from "@/lib/api";
import { useElementSize } from "@/lib/use-element-size";
import type { AreaPoint } from "@/types";

const RED = "#e5202e";

/**
 * Хориотой бүс: видеоны дээр улаан олон өнцөгт. Хүний хөл (боксын доод төв) дотор нь орвол AI зөрчил гэж үзнэ.
 * Координат нь AI-ийн харж буй зураг дээр (эргүүлсний дараа, толин тусгалаас өмнө) 0..1 — тиймээс mirror үед x-ийг эргүүлнэ.
 * Засах горимд видео дээр дарж цэг нэмнэ (дор хаяж 3), «Хадгалах» дарвал AI ~10 сек дотор шинэ бүсийг ашиглана.
 */
export function RestrictedAreaLayer({
  cameraId, video, mirror, rotation, editing, onDone,
}: {
  cameraId: string;
  video: HTMLVideoElement | null;
  mirror: boolean;
  rotation: number;
  editing: boolean;
  onDone: () => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const size = useElementSize(boxRef);
  const [areas, setAreas] = useState<AreaPoint[][]>([]);
  const [draft, setDraft] = useState<AreaPoint[]>([]);
  const [saving, setSaving] = useState(false);
  const [videoSize, setVideoSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    let cancelled = false;
    api.restrictedArea(cameraId).then((r) => { if (!cancelled) setAreas(r.areas); }).catch(() => { });
    return () => { cancelled = true; };
  }, [cameraId]);

  useRealtimeEvents((event) => {
    if (event.type === "RESTRICTED_AREA_UPDATED" && event.data.camera_id === cameraId) setAreas(event.data.areas);
  });

  useEffect(() => {
    if (!video) return;
    const update = () => setVideoSize({ w: video.videoWidth, h: video.videoHeight });
    update();
    video.addEventListener("loadedmetadata", update);
    video.addEventListener("resize", update);
    return () => { video.removeEventListener("loadedmetadata", update); video.removeEventListener("resize", update); };
  }, [video]);

  // DetectionOverlay-тэй ижил: object-contain, 90/270°-д өргөн, өндөр солигдоно
  const sideways = rotation === 90 || rotation === 270;
  const vw = (sideways ? videoSize.h : videoSize.w) || 16, vh = (sideways ? videoSize.w : videoSize.h) || 9;
  const scale = size.w && size.h ? Math.min(size.w / vw, size.h / vh) : 0;
  const dw = vw * scale, dh = vh * scale;
  const ox = (size.w - dw) / 2, oy = (size.h - dh) / 2;

  const toScreen = ([x, y]: AreaPoint): [number, number] => [(mirror ? 1 - x : x) * dw, y * dh];
  const path = (poly: AreaPoint[]) => poly.map((p) => toScreen(p).join(",")).join(" ");

  function addPoint(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const snap = (v: number) => (v < 0.02 ? 0 : v > 0.98 ? 1 : v); // ирмэгт ойрхон дарвал яг ирмэг дээр
    const sx = snap((e.clientX - rect.left) / rect.width), sy = snap((e.clientY - rect.top) / rect.height);
    if (sx < 0 || sx > 1 || sy < 0 || sy > 1) return;
    const x = mirror ? 1 - sx : sx; // дэлгэц -> AI-ийн зураг
    setDraft((d) => (d.length >= 30 ? d : [...d, [Math.round(x * 10000) / 10000, Math.round(sy * 10000) / 10000]]));
  }

  function finish() {
    setDraft([]);
    onDone();
  }

  async function save(next: AreaPoint[][]) {
    setSaving(true);
    try {
      const saved = await api.saveRestrictedArea(cameraId, next);
      setAreas(saved.areas);
      toast.success(next.length ? "Хориотой бүсийг хадгаллаа · AI 10 секундэд ашиглаж эхэлнэ" : "Хориотой бүсийг устгалаа");
      finish();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Хадгалж чадсангүй");
    } finally {
      setSaving(false);
    }
  }

  const shown = editing ? (draft.length ? [] : areas) : areas;

  return (
    <div ref={boxRef} className="pointer-events-none absolute inset-0">
      {scale > 0 && (
        <svg
          width={dw} height={dh} viewBox={`0 0 ${dw} ${dh}`}
          style={{ left: ox, top: oy }}
          className={`absolute ${editing ? "pointer-events-auto cursor-crosshair" : ""}`}
          onPointerDown={editing ? addPoint : undefined}
          role={editing ? "application" : undefined}
          aria-label={editing ? "Хориотой бүс зурах талбай: дарж цэг нэмнэ" : undefined}
        >
          {shown.map((poly, i) => (
            <polygon key={i} points={path(poly)} fill={RED} fillOpacity={editing ? 0.1 : 0.16} stroke={RED} strokeWidth={2} strokeDasharray="8 5" />
          ))}
          {editing && draft.length > 0 && (
            <>
              <polygon points={path(draft)} fill={RED} fillOpacity={draft.length >= 3 ? 0.22 : 0} stroke={RED} strokeWidth={2.5} />
              {draft.map((p, i) => {
                const [x, y] = toScreen(p);
                return <circle key={i} cx={x} cy={y} r={i === 0 ? 7 : 5} fill={i === 0 ? "#fff" : RED} stroke={RED} strokeWidth={2} />;
              })}
            </>
          )}
        </svg>
      )}

      {!editing && areas.length > 0 && scale > 0 && (
        <span
          className="absolute flex items-center gap-1 rounded bg-red-600/85 px-1.5 py-0.5 text-[11px] font-semibold text-white"
          style={{ left: ox + Math.min(...areas[0].map((p) => toScreen(p)[0])), top: oy + Math.min(...areas[0].map((p) => toScreen(p)[1])) }}
        >
          <ShieldBan className="size-3" /> Хориотой бүс
        </span>
      )}

      {editing && (
        <div className="pointer-events-auto absolute inset-x-0 top-3 mx-auto flex w-fit max-w-[calc(100%-1.5rem)] flex-wrap items-center justify-center gap-1.5 rounded-xl bg-black/75 p-2 text-xs text-white backdrop-blur">
          <span className="px-1.5">
            {draft.length < 3 ? `Видео дээр дарж цэг нэмнэ (${draft.length}/3+)` : `${draft.length} цэг · хүний хөл энэ бүсэд орвол зөрчил`}
          </span>
          <button type="button" disabled={!draft.length || saving} onClick={() => setDraft((d) => d.slice(0, -1))}
            className="flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1.5 hover:bg-white/20 disabled:opacity-40">
            <Undo2 className="size-3.5" /> Буцаах
          </button>
          <button type="button" disabled={draft.length < 3 || saving} onClick={() => save([draft])}
            className="flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1.5 font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40">
            <Check className="size-3.5" /> Хадгалах
          </button>
          {areas.length > 0 && (
            <button type="button" disabled={saving} onClick={() => save([])}
              className="flex items-center gap-1 rounded-lg bg-red-600/80 px-2.5 py-1.5 hover:bg-red-600 disabled:opacity-40">
              <Trash2 className="size-3.5" /> Бүсийг устгах
            </button>
          )}
          <button type="button" disabled={saving} onClick={finish}
            className="flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1.5 hover:bg-white/20 disabled:opacity-40">
            <X className="size-3.5" /> Болих
          </button>
        </div>
      )}
    </div>
  );
}
