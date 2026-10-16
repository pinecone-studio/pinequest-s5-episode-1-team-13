"use client";

import Link from "next/link";
import { VideoOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CameraWorkspace } from "@/components/dashboard/camera-workspace";
import { StatCards } from "@/components/dashboard/stat-cards";
import { useRealtimeEvents } from "@/components/providers/realtime-provider";
import { ViolationDetailDialog } from "@/components/violations/violation-detail-dialog";
import { ViolationTable } from "@/components/violations/violation-table";
import { api } from "@/lib/api";
import type { Camera, DashboardStats, Violation } from "@/types";

const RECENT = 8;

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [recent, setRecent] = useState<Violation[]>([]);
  const [selected, setSelected] = useState<Violation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const statsTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const refreshStats = useCallback(() => {
    clearTimeout(statsTimer.current);
    statsTimer.current = setTimeout(() => api.stats().then(setStats).catch(() => undefined), 300);
  }, []);

  useEffect(() => {
    Promise.all([api.stats(), api.cameras(), api.violations({ page_size: RECENT })])
      .then(([s, c, v]) => {
        setStats(s);
        setCameras(c);
        setRecent(v.items);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Ачаалж чадсангүй"));
    const poll = setInterval(() => api.stats().then(setStats).catch(() => undefined), 15_000); // AI heartbeat
    return () => {
      clearInterval(poll);
      clearTimeout(statsTimer.current);
    };
  }, []);

  useRealtimeEvents((event) => {
    switch (event.type) {
      case "VIOLATION_CREATED":
        setRecent((prev) =>
          [{ ...event.data, zone_id: null, resolved_at: null, resolved_by: null, created_at: event.data.detected_at }, ...prev.filter((v) => v.id !== event.data.id)].slice(0, RECENT),
        );
        refreshStats();
        break;
      case "VIOLATION_UPDATED":
        setRecent((prev) => prev.map((v) => (v.id === event.data.id ? event.data : v)));
        setSelected((cur) => (cur?.id === event.data.id ? event.data : cur));
        refreshStats();
        break;
      case "CAMERA_UPDATED":
        setCameras((prev) => (prev.some((c) => c.id === event.data.id) ? prev.map((c) => (c.id === event.data.id ? event.data : c)) : [...prev, event.data]));
        refreshStats();
        break;
      case "VIOLATION_DELETED":
        setRecent((prev) => prev.filter((v) => v.id !== event.data.id));
        setSelected((cur) => (cur?.id === event.data.id ? null : cur));
        refreshStats();
        break;
      case "CAMERA_DELETED":
        setCameras((prev) => prev.filter((c) => c.id !== event.data.id));
        refreshStats();
        break;
    }
  });

  return (
    <div className="min-w-0 space-y-8">
      {error && <p role="alert" className="text-[15px] text-danger">{error}</p>}
      <StatCards stats={stats} />

      <section>
        <h2 className="mb-5 text-[22px] font-semibold leading-tight tracking-tight text-foreground">Камерын шууд хяналт</h2>
        {cameras.length === 0 ? (
          <div className="rounded-3xl border border-border bg-card px-6 py-10 text-center">
            <VideoOff className="mx-auto size-4 text-muted-foreground" />
            <p className="mt-2 text-[15px] text-muted-foreground">
              Камер байхгүй байна. Хяналт эхлэхийн тулд <Link href="/cameras" className="text-foreground underline">камер нэмнэ үү</Link>.
            </p>
          </div>
        ) : (
          <CameraWorkspace cameras={cameras} />
        )}
      </section>

      <section>
        <div className="mb-5 flex items-baseline justify-between gap-3">
          <h2 className="text-[22px] font-semibold leading-tight tracking-tight text-foreground">Сүүлийн зөрчлүүд</h2>
          <Link href="/violations" className="text-[15px] text-muted-foreground hover:text-foreground">Бүгдийг харах</Link>
        </div>
        <ViolationTable items={recent} onOpen={setSelected} empty="Зөрчил илрээгүй байна" />
      </section>

      <ViolationDetailDialog
        violation={selected}
        onClose={() => setSelected(null)}
        onChanged={(v) => { setSelected(v); setRecent((prev) => prev.map((x) => (x.id === v.id ? v : x))); refreshStats(); }}
        onDeleted={(id) => { setSelected(null); setRecent((prev) => prev.filter((x) => x.id !== id)); refreshStats(); }}
      />
    </div>
  );
}
