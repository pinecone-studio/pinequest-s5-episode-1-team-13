"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Power, RotateCw, ShieldBan, Video, VideoOff } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";

import { DetectionOverlay } from "@/components/dashboard/detection-overlay";
import { RestrictedAreaLayer } from "@/components/dashboard/restricted-area-layer";
import { CameraStatusBadge } from "@/components/status-badges";
import { api, ApiError } from "@/lib/api";
import { IN_APP_HINT, isInAppBrowser } from "@/lib/in-app-browser";
import { CAMERA_STATUS_LABEL, cameraTone, zoneLabel } from "@/lib/format";
import { useElementSize } from "@/lib/use-element-size";
import { startWhep, startWhip } from "@/lib/webrtc";
import type { Camera } from "@/types";

const RETRY_MS = 2000;
const OFFLINE_RETRY_MS = 5000; // edge унтраастай (503): асахыг хүлээж байх зуур backend-ийг ачаалахгүй
const PUBLISH_RETRY_MS = 3000;

/** Видеог цагийн зүүнд `rotation`° эргүүлж талбайд багтаана (90/270°-д өргөн, өндөр солигдоно). */
function videoStyle(size: { w: number; h: number }, rotation: number): React.CSSProperties {
  const { w, h } = size;
  if (!w || !h) return { left: 0, top: 0, width: "100%", height: "100%" };
  const sideways = rotation === 90 || rotation === 270;
  const vw = sideways ? h : w;
  const vh = sideways ? w : h;
  return { width: vw, height: vh, left: (w - vw) / 2, top: (h - vh) / 2, transform: `rotate(${rotation}deg)` };
}

/**
 * Шууд харагдац: MediaMTX-ээс WebRTC (WHEP)-ээр жинхэнэ видео (25-30 fps) + AI боксын давхарга.
 * Нэвтрэлт: backend-ийн 2 минутын токен. Raw RTSP URL browser-д огт очихгүй.
 */
export function CameraTile({ camera }: { camera: Camera }) {
  const browserCam = camera.camera_type === "BROWSER";
  const mirror = (camera.camera_type === "LOCAL_WEBCAM" || browserCam) && camera.mirror; // IP камер үргэлж анхдагч (эргүүлэхгүй)
  const live = cameraTone(camera.status) !== "idle" && camera.enabled;
  const rotation = camera.rotation ?? 0;
  const stageRef = useRef<HTMLDivElement>(null);
  const stageSize = useElementSize(stageRef);
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [videoProblem, setVideoProblem] = useState<string | null>(null); // жишээ: edge унтраастай
  const { canManageCameras } = useAuth();
  const [editingArea, setEditingArea] = useState(false);

  async function rotate() {
    try {
      await api.updateCamera(camera.id, { rotation: (rotation + 90) % 360 }); // CAMERA_UPDATED event-ээр шууд шинэчлэгдэнэ; AI 10 сек дотор мөн эргүүлнэ
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Амжилтгүй боллоо");
    }
  }

  // BROWSER камер: энэ browser-ийн камерыг WHIP-ээр MediaMTX руу дамжуулна (tile unmount болоход зогсоно).
  // Тасарвал (сүлжээ, backend redeploy) зогсоох хүртэл автоматаар дахин холбогдоно.
  const [publishing, setPublishing] = useState<"off" | "starting" | "on">("off");
  const pub = useRef<{ wanted: boolean; stream: MediaStream | null; pc: RTCPeerConnection | null; timer?: ReturnType<typeof setTimeout> }>(
    { wanted: false, stream: null, pc: null },
  );

  const stopPublish = useCallback(() => {
    const p = pub.current;
    p.wanted = false;
    clearTimeout(p.timer);
    p.pc?.close();
    p.pc = null;
    p.stream?.getTracks().forEach((t) => t.stop());
    p.stream = null;
    setPublishing("off");
  }, []);

  useEffect(() => stopPublish, [stopPublish]);

  async function connectPublisher(first: boolean) {
    const p = pub.current;
    if (!p.wanted || !p.stream) return;
    const retry = () => {
      if (!p.wanted) return;
      setPublishing("starting");
      clearTimeout(p.timer);
      p.timer = setTimeout(() => void connectPublisher(false), PUBLISH_RETRY_MS);
    };
    try {
      const access = await api.publish(camera.id);
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
      setPublishing("on");
      if (first) toast.success("Энэ төхөөрөмжийн камерыг дамжуулж байна");
    } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) { // эрхгүй/олдсонгүй — дахин оролдох утгагүй
        stopPublish();
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

  async function startPublish() {
    const p = pub.current;
    if (p.wanted) return; // давхар дарахаас хамгаална
    p.wanted = true;
    setPublishing("starting");
    if (isInAppBrowser(navigator.userAgent)) toast.warning("Энэ browser камер дамжуулахгүй байж магадгүй", { description: IN_APP_HINT });
    try {
      p.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    } catch (err) {
      stopPublish();
      const denied = err instanceof DOMException && err.name === "NotAllowedError";
      toast.error(denied ? "Камерын зөвшөөрөл олгогдсонгүй (browser-ийн хаягийн мөрөнд зөвшөөрнө үү)" : "Камерыг нээж чадсангүй");
      return;
    }
    await connectPublisher(true);
  }

  const [powering, setPowering] = useState(false);
  async function togglePower() {
    setPowering(true);
    try {
      if (camera.enabled) await api.disconnectCamera(camera.id);
      else await api.connectCamera(camera.id);
      toast.success(camera.enabled ? "Камерыг унтраалаа" : "Камерыг асааж байна…"); // төлөв CAMERA_UPDATED event-ээр шинэчлэгдэнэ
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Амжилтгүй боллоо");
    } finally {
      setPowering(false);
    }
  }

  useEffect(() => {
    if (!live || !video) return;
    let cancelled = false;
    let pc: RTCPeerConnection | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const retry = (wait = RETRY_MS) => {
      pc?.close();
      pc = null;
      setPlaying(false);
      if (!cancelled) timer = setTimeout(connect, wait);
    };
    const connect = async () => {
      try {
        const access = await api.webrtc(camera.id);
        if (cancelled) return;
        setVideoProblem(null);
        pc = await startWhep(access.whep_url, access.token, (stream) => { video.srcObject = stream; }, () => retry(), access.ice_servers);
        if (cancelled) pc.close();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return; // камер устгагдсан — дахин асуухгүй
        if (err instanceof ApiError && err.status === 503) {
          setVideoProblem(err.message); // edge унтраастай: шалтгааныг харуулаад асахыг хүлээнэ
          return retry(OFFLINE_RETRY_MS);
        }
        retry(); // MediaMTX-д видео хараахан бэлэн биш / түр тасарсан
      }
    };
    connect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      pc?.close();
      video.srcObject = null;
    };
  }, [live, video, camera.id]);

  return (
    <div className="group relative overflow-hidden rounded-2xl border bg-black shadow-lg shadow-black/30">
      <div className="relative aspect-video">
        <div ref={stageRef} className={`absolute inset-0 overflow-hidden bg-black ${mirror ? "-scale-x-100" : ""}`}>
          <video
            ref={setVideo}
            autoPlay muted playsInline
            onPlaying={() => setPlaying(true)}
            onEmptied={() => setPlaying(false)}
            style={videoStyle(stageSize, rotation)}
            className="absolute bg-black object-contain"
          />
        </div>
        {playing && (
          <RestrictedAreaLayer cameraId={camera.id} video={video} mirror={mirror} rotation={rotation}
            editing={editingArea && canManageCameras} onDone={() => setEditingArea(false)} />
        )}
        {playing && camera.ai_enabled && <DetectionOverlay cameraId={camera.id} video={video} mirror={mirror} rotation={rotation} />}
        {playing && !camera.ai_enabled && (
          <span className="pointer-events-none absolute right-4 top-4 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-xs font-medium text-white backdrop-blur">
            <span className="size-2 rounded-full bg-zinc-500" /> AI салгасан · зөвхөн видео
          </span>
        )}

        {!playing && (
          <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-zinc-900 to-zinc-950 text-muted-foreground">
            <div className="flex max-w-[85%] flex-col items-center gap-3 text-center text-sm">
              <VideoOff className="size-10" />
              {camera.enabled ? (live ? (videoProblem ?? "Видео хүлээж байна…") : CAMERA_STATUS_LABEL[camera.status]) : "Камер унтраалттай"}
              {!camera.enabled && canManageCameras && (
                <button type="button" disabled={powering} onClick={togglePower}
                  className="mt-1 flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-60">
                  <Power className="size-4" /> Камер асаах
                </button>
              )}
            </div>
          </div>
        )}

        {playing && (
          <span className="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-xs font-semibold tracking-wider text-red-400 backdrop-blur">
            <span className="size-2 animate-pulse rounded-full bg-red-500" /> ШУУД
          </span>
        )}

        {canManageCameras && camera.enabled && (
          <button
            type="button" onClick={togglePower} disabled={powering} title="Камерыг унтраах" aria-label="Камерыг унтраах"
            className="absolute right-4 top-14 grid size-9 place-items-center rounded-full bg-black/60 text-white backdrop-blur transition hover:bg-red-600 disabled:opacity-60"
          >
            <Power className="size-4" />
          </button>
        )}

        {canManageCameras && browserCam && camera.enabled && (
          <button
            type="button" onClick={publishing === "off" ? startPublish : stopPublish}
            className={`absolute left-4 top-14 flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold backdrop-blur transition ${publishing === "off" ? "bg-primary text-primary-foreground hover:opacity-90" : "bg-red-600/80 text-white hover:bg-red-600"}`}
          >
            <Video className="size-4" />
            {publishing === "off" ? "Энэ төхөөрөмжөөс дамжуулах" : publishing === "starting" ? "Холбогдож байна… (зогсоох)" : "Дамжуулалт зогсоох"}
          </button>
        )}

        {canManageCameras && playing && !editingArea && (
          <button
            type="button" onClick={() => setEditingArea(true)} title="Хориотой бүс зурах" aria-label="Хориотой бүс зурах"
            className="absolute bottom-16 right-16 grid size-10 place-items-center rounded-full bg-black/60 text-white backdrop-blur transition hover:bg-red-600"
          >
            <ShieldBan className="size-5" />
          </button>
        )}

        {canManageCameras && (
          <button
            type="button" onClick={rotate} title={`Эргүүлэх (дарах бүрт 90°, одоо ${rotation}°)`} aria-label="Камерын харааг эргүүлэх"
            className="absolute bottom-16 right-4 grid size-10 place-items-center rounded-full bg-black/60 text-white backdrop-blur transition hover:bg-primary hover:text-primary-foreground"
          >
            <RotateCw className="size-5 transition-transform duration-300" style={{ transform: `rotate(${rotation}deg)` }} />
          </button>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-5 pb-4 pt-12">
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold text-white">{camera.name}</div>
            <div className="text-sm text-white/70">{camera.zone ? zoneLabel(camera.zone) : "Бүсгүй"}</div>
          </div>
          <CameraStatusBadge status={camera.status} />
        </div>
      </div>
    </div>
  );
}
