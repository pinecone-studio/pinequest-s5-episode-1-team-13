"use client";

import { useEffect, useRef, useState } from "react";

import { useRealtimeEvents, useRealtimeStatus } from "@/components/providers/realtime-provider";
import type { DetectionsData, PPEState } from "@/types";

const GLIDE_MS = 90; // боксыг AI-ийн шинэ байрлал руу зөөлөн гулсуулна (үсрэхгүй, хүнийг дагана)
const STALE_MS = 1500; // AI-аас шинэ илрүүлэлт ирэхгүй бол боксыг арилгана
const RED = "#e5202e";
const GREEN = "#1fb25a";
const GREY = "#8b95a5"; // AI хүнийг олсон ч каск/хувцсыг дүгнэж чадаагүй

function ppeLabel(helmet: PPEState, uniform: PPEState, helmetRequired: boolean): string {
  const parts: string[] = [];
  if (helmet === "NO") { if (helmetRequired) parts.push("Каскгүй"); } // оффист каск заавал биш
  else if (helmet === "YES") parts.push("Каскатай");
  if (uniform === "NO") parts.push("Ажлын хувцасгүй");
  else if (uniform === "YES") parts.push("Ажлын хувцастай");
  return parts.join(" · ");
}

/** Видеоны дээр AI-ийн боксыг зурна: «#1 Каскгүй · Ажлын хувцасгүй» (зөрчил = улаан, хэвийн = ногоон). */
export function DetectionOverlay({ cameraId, video, mirror, rotation = 0, onActivity }: { cameraId: string; video: HTMLVideoElement | null; mirror: boolean; rotation?: number; onActivity?: (state: "waiting" | "processing" | "error") => void }) {
  const connected = useRealtimeStatus();
  const [peopleCount, setPeopleCount] = useState<number | null>(null);
  const mirrorRef = useRef(mirror);
  const rotationRef = useRef(rotation);
  useEffect(() => { mirrorRef.current = mirror; rotationRef.current = rotation; });
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const latest = useRef<{ data: DetectionsData; at: number } | null>(null);
  const lastFrame = useRef(0);
  const shown = useRef(new Map<string, [number, number, number, number]>()); // дэлгэц дээр одоо зурж буй бокс, хүн бүрээр

  useRealtimeEvents((event) => {
    if (event.type === "DETECTIONS" && event.data.camera_id === cameraId) {
      latest.current = { data: event.data, at: performance.now() };
      setPeopleCount((prev) => (prev === event.data.people.length ? prev : event.data.people.length));
    }
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !video) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;

    const draw = () => {
      raf = requestAnimationFrame(draw);
      const dpr = window.devicePixelRatio || 1;
      const cw = canvas.clientWidth, ch = canvas.clientHeight;
      if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
        canvas.width = Math.round(cw * dpr);
        canvas.height = Math.round(ch * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cw, ch);

      const cur = latest.current;
      const sideways = rotationRef.current === 90 || rotationRef.current === 270; // AI хүрээ эргүүлсэн зураг дээр: өргөн, өндөр солигдоно
      const vw = (sideways ? video.videoHeight : video.videoWidth) || (sideways ? 9 : 16), vh = (sideways ? video.videoWidth : video.videoHeight) || (sideways ? 16 : 9); // metadata хоцорвол 16:9 гэж үзнэ
      if (!cur || performance.now() - cur.at > STALE_MS) return;

      // object-contain: видеоны харагдаж буй талбай
      const scale = Math.min(cw / vw, ch / vh);
      const dw = vw * scale, dh = vh * scale;
      const ox = (cw - dw) / 2, oy = (ch - dh) / 2;
      const font = Math.max(11, Math.round(dw / 75)); // жижиг шошго: нүүрийг халхлахгүй
      ctx.font = `700 ${font}px Inter, system-ui, sans-serif`;
      ctx.textBaseline = "middle";

      const tNow = performance.now();
      const k = 1 - Math.exp(-(tNow - (lastFrame.current || tNow)) / GLIDE_MS);
      lastFrame.current = tNow;
      const seen = new Set<string>();
      cur.data.people.forEach((raw, i) => {
        // Хүн бүрийн бокс шинэ байрлал руу гулсана; каскны боксыг ч мөн адил зөөнө
        const key = raw.id != null ? `id${raw.id}` : `i${i}`;
        seen.add(key);
        const prev = shown.current.get(key) ?? raw.box;
        const box = prev.map((v, j) => v + (raw.box[j] - v) * k) as [number, number, number, number];
        shown.current.set(key, box);
        const dx = box[0] - raw.box[0], dy = box[1] - raw.box[1];
        const p = { ...raw, box, helmet_box: raw.helmet_box ? [raw.helmet_box[0] + dx, raw.helmet_box[1] + dy, raw.helmet_box[2] + dx, raw.helmet_box[3] + dy] as [number, number, number, number] : raw.helmet_box };
        const helmetRequired = p.helmet_required !== false;
        const color = p.violation ? RED : p.helmet === "UNKNOWN" && p.uniform === "UNKNOWN" ? GREY : GREEN;
        const bx1 = mirrorRef.current ? 1 - p.box[2] : p.box[0];  // толин тусгал: зөвхөн x тэнхлэг эргэнэ, текст эргэхгүй
        const bx2 = mirrorRef.current ? 1 - p.box[0] : p.box[2];
        const x1 = ox + bx1 * dw, y1 = oy + p.box[1] * dh;
        const x2 = ox + bx2 * dw, y2 = oy + p.box[3] * dh;
        ctx.lineWidth = Math.max(1.5, font / 8); // нарийн шугам
        ctx.strokeStyle = color;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

        // Танигдсан каск (ногоон) / каскгүй толгой (улаан)-ыг тусад нь хүрээлнэ
        if (p.helmet_box) {
          const hx1 = ox + (mirrorRef.current ? 1 - p.helmet_box[2] : p.helmet_box[0]) * dw;
          const hx2 = ox + (mirrorRef.current ? 1 - p.helmet_box[0] : p.helmet_box[2]) * dw;
          const hy1 = oy + p.helmet_box[1] * dh, hy2 = oy + p.helmet_box[3] * dh;
          const hcolor = p.helmet === "YES" ? GREEN : helmetRequired ? RED : GREY;
          ctx.lineWidth = Math.max(1.5, font / 9);
          ctx.strokeStyle = hcolor;
          ctx.strokeRect(hx1, hy1, hx2 - hx1, hy2 - hy1);
          if (p.helmet === "YES") {
            const tag = "Каск";
            const tw = ctx.measureText(tag).width + font * 0.7, th = font * 1.4;
            ctx.fillStyle = hcolor;
            ctx.fillRect(hx1, hy1 - th > oy ? hy1 - th : hy2, tw, th);
            ctx.fillStyle = "#fff";
            ctx.fillText(tag, hx1 + font * 0.35, (hy1 - th > oy ? hy1 - th : hy2) + th / 2);
          }
        }

        const detail = [p.restricted ? "Хориотой бүс" : "", ppeLabel(p.helmet, p.uniform, helmetRequired)].filter(Boolean).join(" · ");
        const text = `#${p.id ?? "?"}${detail ? " " + detail : " Хүн"}`;
        const padX = font * 0.5, chipH = font * 1.5;
        const chipW = ctx.measureText(text).width + padX * 2;
        const cy = Math.max(oy, y1 - chipH);  // шошго боксын дээд ирмэг дээр
        ctx.fillStyle = color;
        ctx.fillRect(x1 - ctx.lineWidth / 2, cy, chipW, chipH);
        ctx.fillStyle = "#fff";
        ctx.fillText(text, x1 - ctx.lineWidth / 2 + padX, cy + chipH / 2);
      });
      for (const key of [...shown.current.keys()]) if (!seen.has(key)) shown.current.delete(key); // гарсан хүмүүсийг мартана
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [video]);

  // AI-ийн дохио ирж байгаа эсэхийг харуулна (хайрцаг харагдахгүй үед оношилгоонд хэрэгтэй)
  useEffect(() => {
    const timer = setInterval(() => {
      if (!latest.current || performance.now() - latest.current.at > 3000) setPeopleCount(null);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    onActivity?.(!connected ? "error" : peopleCount === null ? "waiting" : "processing");
  }, [connected, peopleCount, onActivity]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 size-full" />;
}
