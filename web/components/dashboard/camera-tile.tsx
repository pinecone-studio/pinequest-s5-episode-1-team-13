"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleAlert, Loader2, Power, RefreshCw, RotateCw, ShieldBan, Video, VideoOff } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";

import { DetectionOverlay } from "@/components/dashboard/detection-overlay";
import { RestrictedAreaLayer } from "@/components/dashboard/restricted-area-layer";
import { CameraStatusBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { IN_APP_HINT, isInAppBrowser } from "@/lib/in-app-browser";
import { CAMERA_STATUS_LABEL, cameraTone, TONE_CLASS, zoneLabel } from "@/lib/format";
import { useElementSize } from "@/lib/use-element-size";
import { cn } from "@/lib/utils";
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
  const [playbackAttempt, setPlaybackAttempt] = useState(0);

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
  }, [live, video, camera.id, playbackAttempt]);

  function reloadPlayback() {
    setPlaying(false);
    setVideoProblem(null);
    setPlaybackAttempt((n) => n + 1);
  }

  const stageText = !camera.enabled
    ? "Камер унтраалттай"
    : videoProblem
      ? videoProblem
      : camera.status === "ONLINE" || camera.status === "STREAMING"
        ? "Видео хүлээж байна…"
        : CAMERA_STATUS_LABEL[camera.status];
  const showToolbar = canManageCameras || (camera.enabled && live);

  return (
    <article className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="relative aspect-video bg-black">
        <div ref={stageRef} className={cn("absolute inset-0 overflow-hidden bg-black", mirror && "-scale-x-100")}>
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

        {!playing && (
          <div className="absolute inset-0 grid place-items-center bg-muted text-muted-foreground">
            <div className="flex max-w-[85%] flex-col items-center gap-2 px-4 text-center">
              {!camera.enabled || camera.status === "OFFLINE" ? (
                <VideoOff className="size-4" />
              ) : videoProblem || camera.status === "ERROR" ? (
                <CircleAlert className="size-4" />
              ) : (
                <Loader2 className="size-4 animate-spin" />
              )}
              <p className="text-sm text-foreground">{stageText}</p>
            </div>
          </div>
        )}

        {playing && (
          <span className="pointer-events-none absolute left-2 top-2 flex items-center gap-1.5 rounded-lg bg-black/70 px-2 py-1 text-[11px] font-medium text-white">
            <span className="size-1.5 animate-pulse rounded-full bg-danger" />
            Шууд
          </span>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4">
        <div className="flex flex-col gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-foreground">{camera.name}</div>
            <div className="truncate text-xs text-muted-foreground">{camera.zone ? zoneLabel(camera.zone) : "Бүсгүй"}</div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <CameraStatusBadge status={camera.status} />
            <Badge variant="outline" className={cn("gap-1.5", camera.ai_enabled && playing ? TONE_CLASS.good : TONE_CLASS.idle)}>
              <span className="size-1.5 rounded-full bg-current" />
              {!camera.ai_enabled ? "AI унтраалттай" : playing ? "AI ажиллаж байна" : "AI хүлээгдэж байна"}
            </Badge>
          </div>
        </div>

        {showToolbar && (
          <div className="flex flex-wrap items-center gap-1 border-t border-border pt-3">
            {canManageCameras && (
              <Button
                type="button"
                variant="outline"
                size={camera.enabled ? "icon" : "default"}
                disabled={powering}
                onClick={togglePower}
                aria-label={camera.enabled ? "Камерыг унтраах" : "Камер асаах"}
                title={camera.enabled ? "Камерыг унтраах" : "Камер асаах"}
              >
                <Power className="size-4" />
                {!camera.enabled && "Асаах"}
              </Button>
            )}
            {canManageCameras && browserCam && camera.enabled && (
              <Button
                type="button"
                variant="outline"
                size="default"
                onClick={publishing === "off" ? startPublish : stopPublish}
                aria-label={publishing === "off" ? "Энэ төхөөрөмжөөс дамжуулах" : "Дамжуулалт зогсоох"}
                title={publishing === "off" ? "Энэ төхөөрөмжөөс дамжуулах" : "Дамжуулалт зогсоох"}
              >
                {publishing === "starting" ? <Loader2 className="size-4 animate-spin" /> : <Video className="size-4" />}
                {publishing === "off" ? "Дамжуулах" : publishing === "starting" ? "Холбогдож байна" : "Зогсоох"}
              </Button>
            )}
            {camera.enabled && live && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={reloadPlayback}
                aria-label="Видеог дахин ачаалах"
                title="Видеог дахин ачаалах"
              >
                <RefreshCw className="size-4" />
              </Button>
            )}
            {canManageCameras && <span className="mx-0.5 h-4 w-px bg-border" />}
            {canManageCameras && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={rotate}
                title={`Эргүүлэх (дарах бүрт 90°, одоо ${rotation}°)`}
                aria-label="Камерын харааг эргүүлэх"
              >
                <RotateCw className="size-4" style={{ transform: `rotate(${rotation}deg)` }} />
              </Button>
            )}
            {canManageCameras && playing && !editingArea && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setEditingArea(true)}
                title="Хориотой бүс зурах"
                aria-label="Хориотой бүс зурах"
              >
                <ShieldBan className="size-4" />
              </Button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
